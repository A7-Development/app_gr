"""Receitas — service de leitura dos 3 metodos sobre o catalogo (silver-only).

Fontes (CLAUDE.md §13.2.1):
    wh_receita_operacional  -> COMPETENCIA (tudo) + bloco EVENTO dos 3 metodos
    wh_receita_caixa        -> bloco operacao do CAIXA (desagio na saida)
    wh_receita_acruo_dia    -> bloco operacao do ACRUO (curva diaria)

Disciplina §7.2: TODA query passa por `_apply_filters` (tenant + janela de
competencia + UA). Zero WHERE montado a mao fora do helper.

Vocabulario do shape unificado: cada linha agregada vira
(familia, stream, natureza, valor[, qtd]) — no caixa/acruo o "stream" do
bloco operacao e o EVENTO (liquidacao/recompra/.../acruo/acruo_antecipacao);
na competencia sao os streams reais do catalogo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, String, and_, case, cast, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.controladoria.schemas.receitas import (
    ComposicaoNatureza,
    DescontoMoraCedente,
    Metodo,
    PonteMetodos,
    ReceitaCedenteLinha,
    ReceitaDetalheLinha,
    ReceitasCedentesResponse,
    ReceitasConferenciasResponse,
    ReceitasDetalheResponse,
    ReceitasKpis,
    ReceitasResumoResponse,
    ReceitasTitulosResponse,
    ReceitaTituloLinha,
    SerieMensalPonto,
)
from app.warehouse.bitfin_receita_stream import WhBitfinReceitaStream
from app.warehouse.dim import DimProduto
from app.warehouse.operacao import Operacao
from app.warehouse.receita_acruo_dia import ReceitaAcruoDia
from app.warehouse.receita_caixa import ReceitaCaixa
from app.warehouse.receita_operacional import ReceitaOperacional

ZERO = Decimal("0")

_FAMILIA_OPERACAO = "operacao"
# Componentes do bloco operacao nas derivadas caixa/acruo -> natureza.
_COMPONENTES = (
    ("valor_desagio", "DESAGIO"),
    ("valor_adval", "AD_VALOREM"),
    ("valor_tarifas", "TARIFA"),
)
_NATUREZAS_MORA = ("JUROS_MORA", "MULTA_MORA", "ENCARGO_NEGOCIADO")


def _apply_filters(
    stmt: Any,
    model: Any,
    *,
    tenant_id: UUID,
    competencia_de: date | None = None,
    competencia_ate: date | None = None,
    fundo_id: int | None = None,
    produto_sigla: list[str] | None = None,
) -> Any:
    """Escopo canonico (§7.2) para qualquer SELECT dos fatos de receita."""
    conditions = [model.tenant_id == tenant_id]
    if competencia_de is not None:
        conditions.append(model.competencia >= competencia_de)
    if competencia_ate is not None:
        conditions.append(model.competencia <= competencia_ate)
    if fundo_id is not None:
        conditions.append(model.unidade_administrativa_id == fundo_id)
    if produto_sigla:
        siglas = [s.upper() for s in produto_sigla]
        if model is ReceitaOperacional:
            dim_ids = (
                select(DimProduto.produto_id)
                .where(
                    DimProduto.tenant_id == tenant_id,
                    func.upper(DimProduto.sigla).in_(siglas),
                )
                .scalar_subquery()
            )
            # §14.6: rows WITHOUT a linked product (tarifa_servico, repasse,
            # financeira, moras sem operacao) are ALWAYS included — they do
            # not belong to any product and would silently vanish from the
            # totals otherwise.
            conditions.append(
                or_(model.produto_id.is_(None), model.produto_id.in_(dim_ids))
            )
        else:
            # caixa/acruo: product sigla via wh_operacao.modalidade
            # ('FAT-DM' -> 'FAT'), same rule as the BI module.
            op_ids = (
                select(Operacao.operacao_id)
                .where(
                    Operacao.tenant_id == tenant_id,
                    cast(
                        literal_column(
                            "split_part(wh_operacao.modalidade, '-', 1)"
                        ),
                        String,
                    ).in_(siglas),
                )
                .scalar_subquery()
            )
            conditions.append(
                or_(model.operacao_id.is_(None), model.operacao_id.in_(op_ids))
            )
    return stmt.where(and_(*conditions))


async def _grupo_por_stream(db: AsyncSession, tenant_id: UUID) -> dict[str, str]:
    """stream_key -> grupo ('operacional'|'pos_operacional'), catalogo ativo
    (override do tenant vence a global)."""
    stmt = (
        select(
            WhBitfinReceitaStream.stream_key,
            WhBitfinReceitaStream.grupo,
        )
        .where(
            WhBitfinReceitaStream.valid_until.is_(None),
            or_(
                WhBitfinReceitaStream.tenant_id == tenant_id,
                WhBitfinReceitaStream.tenant_id.is_(None),
            ),
        )
        .order_by(WhBitfinReceitaStream.tenant_id.is_not(None))
    )
    rows = (await db.execute(stmt)).all()
    return {k: g for k, g in rows}


def _grupo_da_linha(
    grupo_map: dict[str, str], familia: str, stream: str
) -> str:
    """Bloco operacao derivado (caixa/acruo: stream=evento, sem entrada no
    catalogo) e operacional por construcao; resto resolve pelo catalogo."""
    if familia == _FAMILIA_OPERACAO and stream not in grupo_map:
        return "operacional"
    return grupo_map.get(stream, "pos_operacional")


async def _agg_eventos(
    db: AsyncSession, *, tenant_id: UUID, de: date, ate: date,
    fundo_id: int | None, produto_sigla: list[str] | None, incluir_operacao: bool,
) -> list[tuple]:
    """(competencia, familia, stream, natureza, qtd, valor) do fato evento.

    `incluir_operacao=True` = metodo competencia (bloco operacao vem do
    proprio wh_receita_operacional).
    """
    stmt = select(
        ReceitaOperacional.competencia,
        ReceitaOperacional.familia,
        func.coalesce(ReceitaOperacional.stream_key, "(sem stream)").label("stream"),
        func.coalesce(ReceitaOperacional.natureza, "NAO_CLASSIFICADO").label("natureza"),
        func.count().label("qtd"),
        func.coalesce(func.sum(ReceitaOperacional.valor), ZERO).label("valor"),
    ).group_by(
        ReceitaOperacional.competencia,
        ReceitaOperacional.familia,
        "stream",
        "natureza",
    )
    if not incluir_operacao:
        stmt = stmt.where(ReceitaOperacional.familia != _FAMILIA_OPERACAO)
    stmt = _apply_filters(
        stmt, ReceitaOperacional, tenant_id=tenant_id,
        competencia_de=de, competencia_ate=ate, fundo_id=fundo_id, produto_sigla=produto_sigla,
    )
    return list((await db.execute(stmt)).all())


async def _agg_operacao_derivada(
    db: AsyncSession, model: Any, *, tenant_id: UUID, de: date, ate: date,
    fundo_id: int | None, produto_sigla: list[str] | None,
) -> list[tuple]:
    """(competencia, familia='operacao', stream=evento, natureza, qtd, valor)
    a partir de wh_receita_caixa ou wh_receita_acruo_dia (componentes)."""
    stmt = select(
        model.competencia,
        model.evento,
        func.count().label("qtd"),
        func.coalesce(func.sum(model.valor_desagio), ZERO),
        func.coalesce(func.sum(model.valor_adval), ZERO),
        func.coalesce(func.sum(model.valor_tarifas), ZERO),
    ).group_by(model.competencia, model.evento)
    stmt = _apply_filters(
        stmt, model, tenant_id=tenant_id,
        competencia_de=de, competencia_ate=ate, fundo_id=fundo_id, produto_sigla=produto_sigla,
    )
    rows = (await db.execute(stmt)).all()
    out: list[tuple] = []
    for comp, evento, qtd, v_des, v_adv, v_tar in rows:
        for (col, natureza), valor in zip(
            _COMPONENTES, (v_des, v_adv, v_tar), strict=True
        ):
            del col
            if Decimal(valor or 0) == ZERO:
                continue
            out.append((comp, _FAMILIA_OPERACAO, evento, natureza, int(qtd), Decimal(valor)))
    return out


async def _linhas_metodo(
    db: AsyncSession, *, tenant_id: UUID, metodo: Metodo, de: date, ate: date,
    fundo_id: int | None, produto_sigla: list[str] | None,
) -> list[tuple]:
    """Shape unificado (competencia, familia, stream, natureza, qtd, valor)."""
    if metodo == "competencia":
        return await _agg_eventos(
            db, tenant_id=tenant_id, de=de, ate=ate, fundo_id=fundo_id, produto_sigla=produto_sigla,
            incluir_operacao=True,
        )
    eventos = await _agg_eventos(
        db, tenant_id=tenant_id, de=de, ate=ate, fundo_id=fundo_id, produto_sigla=produto_sigla,
        incluir_operacao=False,
    )
    model = ReceitaCaixa if metodo == "caixa" else ReceitaAcruoDia
    operacao = await _agg_operacao_derivada(
        db, model, tenant_id=tenant_id, de=de, ate=ate, fundo_id=fundo_id, produto_sigla=produto_sigla,
    )
    return eventos + operacao


async def _total_metodo(
    db: AsyncSession, *, tenant_id: UUID, metodo: Metodo, de: date, ate: date,
    fundo_id: int | None, produto_sigla: list[str] | None,
) -> Decimal:
    linhas = await _linhas_metodo(
        db, tenant_id=tenant_id, metodo=metodo, de=de, ate=ate, fundo_id=fundo_id, produto_sigla=produto_sigla,
    )
    return sum((Decimal(r[5]) for r in linhas), start=ZERO)


async def compute_resumo(
    db: AsyncSession, *, tenant_id: UUID, metodo: Metodo,
    competencia_de: date, competencia_ate: date, fundo_id: int | None = None,
    produto_sigla: list[str] | None = None,
) -> ReceitasResumoResponse:
    linhas = await _linhas_metodo(
        db, tenant_id=tenant_id, metodo=metodo,
        de=competencia_de, ate=competencia_ate, fundo_id=fundo_id, produto_sigla=produto_sigla,
    )

    grupo_map = await _grupo_por_stream(db, tenant_id)

    kpis = ReceitasKpis(total=ZERO, operacionais=ZERO, pos_operacionais=ZERO,
                        desagio=ZERO, mora=ZERO, tarifas=ZERO,
                        recompra_encargos=ZERO)
    serie: dict[date, dict[str, Decimal]] = {}
    composicao: dict[str, Decimal] = {}
    for comp, familia, _stream, natureza, _qtd, valor in linhas:
        v = Decimal(valor)
        kpis.total += v
        if _grupo_da_linha(grupo_map, familia, _stream) == "operacional":
            kpis.operacionais += v
        else:
            kpis.pos_operacionais += v
        if natureza == "DESAGIO" and familia == _FAMILIA_OPERACAO:
            kpis.desagio += v
        if natureza in _NATUREZAS_MORA:
            kpis.mora += v
        if natureza == "TARIFA":
            kpis.tarifas += v
        if familia == "recompra":
            kpis.recompra_encargos += v
        serie.setdefault(comp, {})
        serie[comp][familia] = serie[comp].get(familia, ZERO) + v
        composicao[natureza] = composicao.get(natureza, ZERO) + v

    serie_mensal = [
        SerieMensalPonto(
            competencia=c,
            por_familia=fam,
            total=sum(fam.values(), start=ZERO),
        )
        for c, fam in sorted(serie.items())
    ]
    composicao_natureza = sorted(
        (ComposicaoNatureza(natureza=n, valor=v) for n, v in composicao.items()),
        key=lambda x: x.valor, reverse=True,
    )

    # Ponte: os 3 totais do MESMO periodo (§14.6 — deltas explicados).
    totais: dict[Metodo, Decimal] = {}
    for m in ("caixa", "competencia", "acruo"):
        totais[m] = (
            kpis.total if m == metodo
            else await _total_metodo(
                db, tenant_id=tenant_id, metodo=m,
                de=competencia_de, ate=competencia_ate, fundo_id=fundo_id, produto_sigla=produto_sigla,
            )
        )
    ponte = PonteMetodos(
        caixa=totais["caixa"],
        competencia=totais["competencia"],
        acruo=totais["acruo"],
        delta_competencia_caixa=totais["competencia"] - totais["caixa"],
        delta_competencia_acruo=totais["competencia"] - totais["acruo"],
    )

    return ReceitasResumoResponse(
        metodo=metodo, kpis=kpis, serie_mensal=serie_mensal,
        composicao_natureza=composicao_natureza, ponte=ponte,
    )


async def compute_detalhe(
    db: AsyncSession, *, tenant_id: UUID, metodo: Metodo,
    competencia_de: date, competencia_ate: date, fundo_id: int | None = None,
    produto_sigla: list[str] | None = None,
) -> ReceitasDetalheResponse:
    linhas_raw = await _linhas_metodo(
        db, tenant_id=tenant_id, metodo=metodo,
        de=competencia_de, ate=competencia_ate, fundo_id=fundo_id, produto_sigla=produto_sigla,
    )
    grupo_map = await _grupo_por_stream(db, tenant_id)
    agg: dict[tuple[str, str, str], tuple[int, Decimal]] = {}
    for _comp, familia, stream, natureza, qtd, valor in linhas_raw:
        k = (familia, stream, natureza)
        q0, v0 = agg.get(k, (0, ZERO))
        agg[k] = (q0 + int(qtd), v0 + Decimal(valor))
    linhas = sorted(
        (
            ReceitaDetalheLinha(
                grupo=_grupo_da_linha(grupo_map, f, s),
                familia=f, stream=s, natureza=n, qtd=q, valor=v,
            )
            for (f, s, n), (q, v) in agg.items()
        ),
        key=lambda x: (x.grupo != "operacional", -x.valor),
    )
    return ReceitasDetalheResponse(
        metodo=metodo, linhas=linhas,
        total=sum((x.valor for x in linhas), start=ZERO),
    )


async def compute_cedentes(
    db: AsyncSession, *, tenant_id: UUID, metodo: Metodo,
    competencia_de: date, competencia_ate: date, fundo_id: int | None = None,
    produto_sigla: list[str] | None = None,
) -> ReceitasCedentesResponse:
    """Receita por cedente. Bloco operacao do metodo + eventos, agregados
    por cedente_nome/documento (denormalizados nos fatos)."""
    acc: dict[tuple[str, str | None], dict[str, Any]] = {}

    def _add(nome, doc, natureza, familia, qtd, valor):
        nome = nome or "(sem cedente)"
        k = (nome, doc)
        a = acc.setdefault(k, {"desagio": ZERO, "mora": ZERO, "tarifas": ZERO,
                               "demais": ZERO, "total": ZERO, "qtd": 0})
        v = Decimal(valor)
        a["total"] += v
        a["qtd"] += int(qtd)
        if natureza == "DESAGIO" and familia == _FAMILIA_OPERACAO:
            a["desagio"] += v
        elif natureza in _NATUREZAS_MORA:
            a["mora"] += v
        elif natureza == "TARIFA":
            a["tarifas"] += v
        else:
            a["demais"] += v

    # Eventos (e, na competencia, tambem o bloco operacao).
    stmt = select(
        ReceitaOperacional.cedente_nome,
        ReceitaOperacional.cedente_documento,
        func.coalesce(ReceitaOperacional.natureza, "NAO_CLASSIFICADO"),
        ReceitaOperacional.familia,
        func.count(),
        func.coalesce(func.sum(ReceitaOperacional.valor), ZERO),
    ).group_by(
        ReceitaOperacional.cedente_nome,
        ReceitaOperacional.cedente_documento,
        ReceitaOperacional.natureza,
        ReceitaOperacional.familia,
    )
    if metodo != "competencia":
        stmt = stmt.where(ReceitaOperacional.familia != _FAMILIA_OPERACAO)
    stmt = _apply_filters(
        stmt, ReceitaOperacional, tenant_id=tenant_id,
        competencia_de=competencia_de, competencia_ate=competencia_ate,
        fundo_id=fundo_id, produto_sigla=produto_sigla,
    )
    for nome, doc, nat, fam, qtd, valor in (await db.execute(stmt)).all():
        _add(nome, doc, nat, fam, qtd, valor)

    if metodo != "competencia":
        model = ReceitaCaixa if metodo == "caixa" else ReceitaAcruoDia
        stmt = select(
            model.cedente_nome,
            model.cedente_documento,
            func.count(),
            func.coalesce(func.sum(model.valor_desagio), ZERO),
            func.coalesce(func.sum(model.valor_adval), ZERO),
            func.coalesce(func.sum(model.valor_tarifas), ZERO),
        ).group_by(model.cedente_nome, model.cedente_documento)
        stmt = _apply_filters(
            stmt, model, tenant_id=tenant_id,
            competencia_de=competencia_de, competencia_ate=competencia_ate,
            fundo_id=fundo_id, produto_sigla=produto_sigla,
        )
        for nome, doc, qtd, v_des, v_adv, v_tar in (await db.execute(stmt)).all():
            _add(nome, doc, "DESAGIO", _FAMILIA_OPERACAO, qtd, v_des)
            if Decimal(v_adv or 0) != ZERO:
                _add(nome, doc, "AD_VALOREM", _FAMILIA_OPERACAO, 0, v_adv)
            if Decimal(v_tar or 0) != ZERO:
                _add(nome, doc, "TARIFA", _FAMILIA_OPERACAO, 0, v_tar)

    linhas = sorted(
        (
            ReceitaCedenteLinha(
                cedente_nome=nome, cedente_documento=doc,
                desagio=a["desagio"], mora=a["mora"], tarifas=a["tarifas"],
                demais=a["demais"], total=a["total"], qtd=a["qtd"],
            )
            for (nome, doc), a in acc.items()
        ),
        key=lambda x: x.total, reverse=True,
    )
    return ReceitasCedentesResponse(
        metodo=metodo, linhas=linhas,
        total=sum((x.total for x in linhas), start=ZERO),
    )


async def compute_titulos(
    db: AsyncSession, *, tenant_id: UUID, metodo: Metodo, familia: str,
    stream: str, competencia_de: date, competencia_ate: date,
    fundo_id: int | None = None,
    produto_sigla: list[str] | None = None,
) -> ReceitasTitulosResponse:
    """Drill: linhas-titulo de um (familia, stream) no periodo. SEM corte
    (§14.6): retorna tudo; frontend virtualiza."""
    linhas: list[ReceitaTituloLinha] = []

    if familia == _FAMILIA_OPERACAO and metodo != "competencia":
        model = ReceitaCaixa if metodo == "caixa" else ReceitaAcruoDia
        stmt = select(
            model.data, model.titulo_id, model.documento, model.cedente_nome,
            model.valor_desagio, model.valor_adval, model.valor_tarifas,
        ).where(model.evento == stream).order_by(model.data.desc())
        stmt = _apply_filters(
            stmt, model, tenant_id=tenant_id,
            competencia_de=competencia_de, competencia_ate=competencia_ate,
            fundo_id=fundo_id, produto_sigla=produto_sigla,
        )
        for data_, tid, doc, ced, v_des, v_adv, v_tar in (await db.execute(stmt)).all():
            for natureza, v in (("DESAGIO", v_des), ("AD_VALOREM", v_adv),
                                ("TARIFA", v_tar)):
                if Decimal(v or 0) == ZERO:
                    continue
                linhas.append(ReceitaTituloLinha(
                    data=data_, titulo_id=tid, documento=doc, cedente_nome=ced,
                    natureza=natureza, valor=Decimal(v),
                ))
    else:
        stmt = select(
            ReceitaOperacional.data, ReceitaOperacional.titulo_id,
            ReceitaOperacional.documento, ReceitaOperacional.cedente_nome,
            func.coalesce(ReceitaOperacional.natureza, "NAO_CLASSIFICADO"),
            ReceitaOperacional.valor, ReceitaOperacional.valor_referencia_regua,
        ).where(
            ReceitaOperacional.familia == familia,
            func.coalesce(ReceitaOperacional.stream_key, "(sem stream)") == stream,
        ).order_by(ReceitaOperacional.data.desc())
        stmt = _apply_filters(
            stmt, ReceitaOperacional, tenant_id=tenant_id,
            competencia_de=competencia_de, competencia_ate=competencia_ate,
            fundo_id=fundo_id, produto_sigla=produto_sigla,
        )
        for data_, tid, doc, ced, nat, valor, ref in (await db.execute(stmt)).all():
            linhas.append(ReceitaTituloLinha(
                data=data_, titulo_id=tid, documento=doc, cedente_nome=ced,
                natureza=nat, valor=Decimal(valor),
                valor_referencia_regua=(None if ref is None else Decimal(ref)),
            ))

    return ReceitasTitulosResponse(
        metodo=metodo, familia=familia, stream=stream, linhas=linhas,
        total=sum((x.valor for x in linhas), start=ZERO), qtd=len(linhas),
    )


async def compute_conferencias(
    db: AsyncSession, *, tenant_id: UUID,
    competencia_de: date, competencia_ate: date, fundo_id: int | None = None,
    produto_sigla: list[str] | None = None,
) -> ReceitasConferenciasResponse:
    """Desconto de mora concedido = regua contratual - cobrado, por cedente.

    Base: linhas com `valor_referencia_regua` (recompra juros/multa +
    mora_liquidacao_negociado). Linha com cobrado=0 e regua>0 = perdao
    total. Independe de metodo (evento e igual nos 3).
    """
    stmt = select(
        ReceitaOperacional.cedente_nome,
        ReceitaOperacional.cedente_documento,
        func.count(),
        func.coalesce(func.sum(ReceitaOperacional.valor_referencia_regua), ZERO),
        func.coalesce(func.sum(ReceitaOperacional.valor), ZERO),
        func.coalesce(
            func.sum(
                cast(
                    case(
                        (
                            and_(
                                ReceitaOperacional.valor == 0,
                                ReceitaOperacional.valor_referencia_regua > 0,
                            ),
                            1,
                        ),
                        else_=0,
                    ),
                    Integer,
                )
            ),
            0,
        ),
    ).where(
        ReceitaOperacional.valor_referencia_regua.isnot(None),
    ).group_by(
        ReceitaOperacional.cedente_nome,
        ReceitaOperacional.cedente_documento,
    )
    stmt = _apply_filters(
        stmt, ReceitaOperacional, tenant_id=tenant_id,
        competencia_de=competencia_de, competencia_ate=competencia_ate,
        fundo_id=fundo_id, produto_sigla=produto_sigla,
    )
    rows = (await db.execute(stmt)).all()

    linhas = sorted(
        (
            DescontoMoraCedente(
                cedente_nome=nome or "(sem cedente)",
                cedente_documento=doc,
                regua=Decimal(regua), cobrado=Decimal(cobrado),
                desconto=Decimal(regua) - Decimal(cobrado),
                perdoes_totais=int(perdoes), qtd=int(qtd),
            )
            for nome, doc, qtd, regua, cobrado, perdoes in rows
        ),
        key=lambda x: x.desconto, reverse=True,
    )
    return ReceitasConferenciasResponse(
        competencia_de=competencia_de, competencia_ate=competencia_ate,
        desconto_mora=linhas,
        total_regua=sum((x.regua for x in linhas), start=ZERO),
        total_cobrado=sum((x.cobrado for x in linhas), start=ZERO),
        total_desconto=sum((x.desconto for x in linhas), start=ZERO),
        total_perdoes=sum(x.perdoes_totais for x in linhas),
    )
