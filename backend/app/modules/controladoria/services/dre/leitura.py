"""DRE -- service de leitura agregada (silver -> contrato API).

Le APENAS de `wh_dre_mensal` (silver canonico, CLAUDE.md §13.2.1). A
gravacao em silver e feita pelo ETL Bitfin via classifier (bronze
`wh_bitfin_raw_dre` -> silver, ver `services/dre/classifier.py` e
`adapters/erp/bitfin/etl.py`).

Disciplina §7.2: TODA query passa por `_apply_filters` -- zero WHERE
montado a mao. Helpers que tocam DreMensal sem o filtro sao bug
estrutural (mesmo padrao validado no BI/Operacoes).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.controladoria.schemas.dre import (
    DreBreakdownResponse,
    DreBreakdownRow,
    DreCelula,
    DreDescricao,
    DreDimensao,
    DreFornecedor,
    DreFornecedoresResponse,
    DreFornecedorRow,
    DreGrupo,
    DreLinhaTotais,
    DrePivotResponse,
    DreReceitaCelula,
    DreReceitaNatureza,
    DreReceitaNaturezaResponse,
    DreReceitaTipo,
    DreSubgrupo,
)
from app.warehouse.bitfin_entidade import WhBitfinEntidade
from app.warehouse.dim import DimProduto
from app.warehouse.dre import DreMensal

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────────────
# Filtro canonico (CLAUDE.md §7.2)
# ─────────────────────────────────────────────────────────────────────────────


def _apply_filters(
    stmt: Any,
    *,
    tenant_id: UUID,
    competencia_de: date | None = None,
    competencia_ate: date | None = None,
    fundo_id: int | None = None,
    produto_id: int | None = None,
    fonte: str | None = None,
) -> Any:
    """Aplica escopo de tenant + filtros globais a qualquer SELECT de DreMensal.

    Toda funcao publica deste service consome este helper. Em PR, query de
    agregado em wh_dre_mensal sem passar por aqui e bloqueador.
    """
    conditions: list[ColumnElement[bool]] = [DreMensal.tenant_id == tenant_id]
    if competencia_de is not None:
        conditions.append(DreMensal.competencia >= competencia_de)
    if competencia_ate is not None:
        conditions.append(DreMensal.competencia <= competencia_ate)
    if fundo_id is not None:
        conditions.append(DreMensal.unidade_administrativa_id == fundo_id)
    if produto_id is not None:
        conditions.append(DreMensal.produto_id == produto_id)
    if fonte:
        conditions.append(DreMensal.fonte == fonte)
    return stmt.where(and_(*conditions))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _months_between(de: date, ate: date) -> list[date]:
    """Lista os primeiros-de-mes entre `de` e `ate` (inclusive)."""
    if ate < de:
        return []
    months: list[date] = []
    cur = _first_of_month(de)
    end = _first_of_month(ate)
    while cur <= end:
        months.append(cur)
        cur = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
    return months


def _zero_celula(c: date) -> DreCelula:
    return DreCelula(competencia=c, receita=ZERO, custo=ZERO, resultado=ZERO, quantidade=0)


def _sum_celulas(a: DreCelula, b: DreCelula) -> DreCelula:
    return DreCelula(
        competencia=a.competencia,
        receita=a.receita + b.receita,
        custo=a.custo + b.custo,
        resultado=a.resultado + b.resultado,
        quantidade=a.quantidade + b.quantidade,
    )


def _totais_from_valores(valores: list[DreCelula]) -> DreLinhaTotais:
    return DreLinhaTotais(
        receita=sum((v.receita for v in valores), start=ZERO),
        custo=sum((v.custo for v in valores), start=ZERO),
        resultado=sum((v.resultado for v in valores), start=ZERO),
        quantidade=sum(v.quantidade for v in valores),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


async def listar_competencias(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_id: int | None = None,
    produto_id: int | None = None,
    fonte: str | None = None,
) -> list[date]:
    """Lista de competencias com dado em wh_dre_mensal -- ordenada."""
    stmt = select(DreMensal.competencia).distinct().order_by(DreMensal.competencia)
    stmt = _apply_filters(
        stmt,
        tenant_id=tenant_id,
        fundo_id=fundo_id,
        produto_id=produto_id,
        fonte=fonte,
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def compute_pivot(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    competencia_de: date,
    competencia_ate: date,
    fundo_id: int | None = None,
    produto_id: int | None = None,
    fonte: str | None = None,
) -> DrePivotResponse:
    """DRE pivotada hierarquicamente (grupo > subgrupo > descricao) x competencia.

    Cada nivel carrega:
      - `valores[]`: serie por competencia (zero quando vazio, todos os meses
        do periodo estao presentes)
      - `totais`: agregado no periodo inteiro

    Ordenacao: `ordem_grupo` (definida na regra de classificacao), depois
    alfabetica em subgrupo/descricao.
    """
    stmt = (
        select(
            DreMensal.ordem_grupo,
            DreMensal.grupo_dre,
            DreMensal.subgrupo,
            DreMensal.descricao,
            DreMensal.fornecedor,
            DreMensal.fornecedor_documento,
            DreMensal.competencia,
            func.sum(DreMensal.receita).label("receita"),
            func.sum(DreMensal.custo).label("custo"),
            func.sum(DreMensal.resultado).label("resultado"),
            func.sum(DreMensal.quantidade).label("quantidade"),
        )
        .group_by(
            DreMensal.ordem_grupo,
            DreMensal.grupo_dre,
            DreMensal.subgrupo,
            DreMensal.descricao,
            DreMensal.fornecedor,
            DreMensal.fornecedor_documento,
            DreMensal.competencia,
        )
        .order_by(
            DreMensal.ordem_grupo,
            DreMensal.grupo_dre,
            DreMensal.subgrupo,
            DreMensal.descricao,
            DreMensal.fornecedor_documento,
            DreMensal.fornecedor,
            DreMensal.competencia,
        )
    )
    stmt = _apply_filters(
        stmt,
        tenant_id=tenant_id,
        competencia_de=competencia_de,
        competencia_ate=competencia_ate,
        fundo_id=fundo_id,
        produto_id=produto_id,
        fonte=fonte,
    )
    rows = (await db.execute(stmt)).all()

    competencias = _months_between(competencia_de, competencia_ate)

    # Indice 4 niveis:
    #   grupo_dre -> (ordem, subgrupo) -> descricao -> (fornecedor, doc) -> {comp -> Celula}
    # Chave do fornecedor: tupla (nome, documento). Quando ambos sao None,
    # representa rows sem fornecedor identificado (vide CLAUDE: RECEITA/PDD/
    # COMISSAO sao 100% sem doc).
    grupos_idx: dict[
        str,
        dict[
            tuple[int, str],
            dict[
                str,
                dict[tuple[str | None, str | None], dict[date, DreCelula]],
            ],
        ],
    ] = {}
    for r in rows:
        subgrupos = grupos_idx.setdefault(r.grupo_dre, {})
        descricoes = subgrupos.setdefault((r.ordem_grupo, r.subgrupo), {})
        fornecedores = descricoes.setdefault(r.descricao, {})
        cells = fornecedores.setdefault((r.fornecedor, r.fornecedor_documento), {})
        cells[r.competencia] = DreCelula(
            competencia=r.competencia,
            receita=r.receita or ZERO,
            custo=r.custo or ZERO,
            resultado=r.resultado or ZERO,
            quantidade=int(r.quantidade or 0),
        )

    grupos_out: list[DreGrupo] = []
    total_geral_por_comp: dict[date, DreCelula] = {c: _zero_celula(c) for c in competencias}

    for grupo, subgrupos_map in grupos_idx.items():
        subgrupos_out: list[DreSubgrupo] = []
        grupo_por_comp: dict[date, DreCelula] = {c: _zero_celula(c) for c in competencias}

        for (ordem_sub, subgrupo), descricoes_map in sorted(subgrupos_map.items()):
            descricoes_out: list[DreDescricao] = []
            sub_por_comp: dict[date, DreCelula] = {c: _zero_celula(c) for c in competencias}

            for descricao, fornecedores_map in sorted(descricoes_map.items()):
                fornecedores_out: list[DreFornecedor] = []
                desc_por_comp: dict[date, DreCelula] = {
                    c: _zero_celula(c) for c in competencias
                }

                # Ordena fornecedores: identificados (por documento, alfabetico)
                # primeiro; "Sem identificacao" (doc None) por ultimo.
                def _forn_sort_key(
                    k: tuple[str | None, str | None],
                ) -> tuple[int, str, str]:
                    nome, doc = k
                    if doc is None and nome is None:
                        return (1, "", "")
                    return (0, doc or "", nome or "")

                for (forn_nome, forn_doc), cells_por_comp in sorted(
                    fornecedores_map.items(), key=lambda kv: _forn_sort_key(kv[0])
                ):
                    valores_forn = [
                        cells_por_comp.get(c) or _zero_celula(c) for c in competencias
                    ]
                    fornecedores_out.append(
                        DreFornecedor(
                            fornecedor=forn_nome,
                            fornecedor_documento=forn_doc,
                            valores=valores_forn,
                            totais=_totais_from_valores(valores_forn),
                        )
                    )
                    for v in valores_forn:
                        desc_por_comp[v.competencia] = _sum_celulas(
                            desc_por_comp[v.competencia], v
                        )

                valores_desc = [desc_por_comp[c] for c in competencias]
                descricoes_out.append(
                    DreDescricao(
                        descricao=descricao,
                        fornecedores=fornecedores_out,
                        valores=valores_desc,
                        totais=_totais_from_valores(valores_desc),
                    )
                )
                for v in valores_desc:
                    sub_por_comp[v.competencia] = _sum_celulas(sub_por_comp[v.competencia], v)

            valores_sub = [sub_por_comp[c] for c in competencias]
            subgrupos_out.append(
                DreSubgrupo(
                    ordem_grupo=ordem_sub,
                    subgrupo=subgrupo,
                    descricoes=descricoes_out,
                    valores=valores_sub,
                    totais=_totais_from_valores(valores_sub),
                )
            )
            for v in valores_sub:
                grupo_por_comp[v.competencia] = _sum_celulas(grupo_por_comp[v.competencia], v)

        valores_grupo = [grupo_por_comp[c] for c in competencias]
        grupos_out.append(
            DreGrupo(
                grupo_dre=grupo,
                subgrupos=subgrupos_out,
                valores=valores_grupo,
                totais=_totais_from_valores(valores_grupo),
            )
        )
        for v in valores_grupo:
            total_geral_por_comp[v.competencia] = _sum_celulas(
                total_geral_por_comp[v.competencia], v
            )

    # Grupos ordenados por menor ordem_grupo entre seus subgrupos
    # (RECEITA_OPERACIONAL min=1 antes de PROVISAO_PDD min=6, etc).
    grupos_out.sort(
        key=lambda g: (min(s.ordem_grupo for s in g.subgrupos), g.grupo_dre)
    )

    valores_total = [total_geral_por_comp[c] for c in competencias]
    return DrePivotResponse(
        competencias=competencias,
        grupos=grupos_out,
        valores_total=valores_total,
        totais=_totais_from_valores(valores_total),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Receita por NATUREZA
# ─────────────────────────────────────────────────────────────────────────────

# Ordem canonica de exibicao das naturezas (codigo cru; frontend rotula).
_NATUREZA_ORDER = ["DESAGIO", "TARIFA", "MULTA", "JUROS", "AD_VALOREM", "IMPOSTO"]


def _natureza_sort_key(natureza: str) -> tuple[int, str]:
    try:
        return (_NATUREZA_ORDER.index(natureza), "")
    except ValueError:
        # Naturezas fora da ordem canonica (ex.: NAO_CLASSIFICADO) por ultimo.
        return (len(_NATUREZA_ORDER), natureza)


async def compute_receita_por_natureza(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    competencia_de: date,
    competencia_ate: date,
    fundo_id: int | None = None,
    produto_id: int | None = None,
) -> DreReceitaNaturezaResponse:
    """Receita operacional agrupada por NATUREZA x competencia.

    Hierarquia: natureza -> tipo (descricao do catalogo) -> serie por
    competencia. Receita = SO `receita` (total_apurado) de linhas
    `grupo_dre='RECEITA_OPERACIONAL'`. Custos descem para outras secoes.

    `natureza` NULL (linha de receita sem regra de classificacao) cai no
    bucket `NAO_CLASSIFICADO` -- flag de governanca, exibido por ultimo.
    """
    natureza_col = func.coalesce(DreMensal.natureza, "NAO_CLASSIFICADO")
    stmt = (
        select(
            natureza_col.label("natureza"),
            DreMensal.descricao,
            DreMensal.subgrupo,
            DreMensal.competencia,
            func.sum(DreMensal.receita).label("receita"),
            func.sum(DreMensal.quantidade).label("quantidade"),
        )
        .where(
            DreMensal.grupo_dre == "RECEITA_OPERACIONAL",
            DreMensal.receita != 0,
        )
        .group_by(
            natureza_col,
            DreMensal.descricao,
            DreMensal.subgrupo,
            DreMensal.competencia,
        )
    )
    stmt = _apply_filters(
        stmt,
        tenant_id=tenant_id,
        competencia_de=competencia_de,
        competencia_ate=competencia_ate,
        fundo_id=fundo_id,
        produto_id=produto_id,
    )
    rows = (await db.execute(stmt)).all()

    competencias = _months_between(competencia_de, competencia_ate)

    # natureza -> descricao -> {competencia: (receita, quantidade)}
    nat_idx: dict[str, dict[str, dict[date, tuple[Decimal, int]]]] = {}
    # (natureza, descricao) -> conjunto de subgrupos (produtos onde aparece)
    produtos_idx: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        descr_map = nat_idx.setdefault(r.natureza, {})
        cells = descr_map.setdefault(r.descricao, {})
        # ACUMULA: a mesma descricao (ex.: "Deságio", "Por Operação") pode vir
        # de >1 subgrupo (Operação + Crédito Estruturado) na mesma competencia.
        # Somar, nunca sobrescrever.
        prev_rec, prev_qt = cells.get(r.competencia, (ZERO, 0))
        cells[r.competencia] = (
            prev_rec + (r.receita or ZERO),
            prev_qt + int(r.quantidade or 0),
        )
        produtos_idx.setdefault((r.natureza, r.descricao), set()).add(r.subgrupo)

    naturezas_out: list[DreReceitaNatureza] = []
    total_por_comp: dict[date, tuple[Decimal, int]] = dict.fromkeys(competencias, (ZERO, 0))

    for natureza in sorted(nat_idx.keys(), key=_natureza_sort_key):
        descr_map = nat_idx[natureza]
        tipos_out: list[DreReceitaTipo] = []
        nat_por_comp: dict[date, tuple[Decimal, int]] = dict.fromkeys(competencias, (ZERO, 0))

        for descricao, cells in descr_map.items():
            valores_tipo = [
                DreReceitaCelula(
                    competencia=c,
                    receita=cells.get(c, (ZERO, 0))[0],
                    quantidade=cells.get(c, (ZERO, 0))[1],
                )
                for c in competencias
            ]
            total_tipo = sum((v.receita for v in valores_tipo), start=ZERO)
            tipos_out.append(
                DreReceitaTipo(
                    descricao=descricao,
                    produtos=sorted(produtos_idx[(natureza, descricao)]),
                    valores=valores_tipo,
                    total=total_tipo,
                )
            )
            for v in valores_tipo:
                rec, qt = nat_por_comp[v.competencia]
                nat_por_comp[v.competencia] = (rec + v.receita, qt + v.quantidade)

        # Tipos ordenados por receita desc.
        tipos_out.sort(key=lambda t: t.total, reverse=True)

        valores_nat = [
            DreReceitaCelula(competencia=c, receita=nat_por_comp[c][0], quantidade=nat_por_comp[c][1])
            for c in competencias
        ]
        naturezas_out.append(
            DreReceitaNatureza(
                natureza=natureza,
                tipos=tipos_out,
                valores=valores_nat,
                total=sum((v.receita for v in valores_nat), start=ZERO),
            )
        )
        for v in valores_nat:
            rec, qt = total_por_comp[v.competencia]
            total_por_comp[v.competencia] = (rec + v.receita, qt + v.quantidade)

    valores_total = [
        DreReceitaCelula(competencia=c, receita=total_por_comp[c][0], quantidade=total_por_comp[c][1])
        for c in competencias
    ]
    return DreReceitaNaturezaResponse(
        competencias=competencias,
        naturezas=naturezas_out,
        valores_total=valores_total,
        total=sum((v.receita for v in valores_total), start=ZERO),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Breakdown generico da receita por dimensao (abas da DRE profunda do mes)
# ─────────────────────────────────────────────────────────────────────────────

_NATUREZA_LABEL = {
    "DESAGIO": "Deságio",
    "TARIFA": "Tarifa",
    "MULTA": "Multa",
    "JUROS": "Juros",
    "AD_VALOREM": "Ad Valorem",
    "IMPOSTO": "Imposto",
    "NAO_CLASSIFICADO": "Não classificado",
}


async def compute_breakdown(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    competencia: date,
    dim: DreDimensao,
    fundo_id: int | None = None,
    produto_id: int | None = None,
    entidade_id: int | None = None,
    natureza: str | None = None,
    subgrupo: str | None = None,
) -> DreBreakdownResponse:
    """Receita operacional de UM mes agregada por uma dimensao.

    `dim` ∈ {natureza, cedente, produto, subgrupo}. Os filtros opcionais
    `entidade_id`/`natureza`/`subgrupo` servem o DRILL (ex.: dim=natureza
    + entidade_id=X = naturezas daquele cedente). Receita = SO linhas de
    RECEITA_OPERACIONAL; custo/resultado vem junto p/ analise de margem.
    """
    dim_col = {
        "natureza": DreMensal.natureza,
        "cedente": DreMensal.entidade_id,
        "produto": DreMensal.produto_id,
        "subgrupo": DreMensal.subgrupo,
    }[dim]

    stmt = (
        select(
            dim_col.label("chave"),
            func.sum(DreMensal.receita).label("receita"),
            func.sum(DreMensal.custo).label("custo"),
            func.sum(DreMensal.resultado).label("resultado"),
        )
        .where(
            DreMensal.grupo_dre == "RECEITA_OPERACIONAL",
            DreMensal.receita != 0,
        )
        .group_by(dim_col)
    )
    stmt = _apply_filters(
        stmt,
        tenant_id=tenant_id,
        competencia_de=competencia,
        competencia_ate=competencia,
        fundo_id=fundo_id,
        produto_id=produto_id,
    )
    # Filtros de DRILL (cortes dentro da dimensao, nao filtros globais).
    if entidade_id is not None:
        stmt = stmt.where(DreMensal.entidade_id == entidade_id)
    if natureza is not None:
        stmt = stmt.where(DreMensal.natureza == natureza)
    if subgrupo is not None:
        stmt = stmt.where(DreMensal.subgrupo == subgrupo)

    rows = (await db.execute(stmt)).all()

    # Resolucao de rotulos por dimensao.
    labels: dict[int, str] = {}
    if dim in ("cedente", "produto"):
        ids = [r.chave for r in rows if r.chave is not None]
        if ids and dim == "cedente":
            ent = (
                await db.execute(
                    select(WhBitfinEntidade.entidade_id, WhBitfinEntidade.nome).where(
                        WhBitfinEntidade.tenant_id == tenant_id,
                        WhBitfinEntidade.entidade_id.in_(ids),
                    )
                )
            ).all()
            labels = {e.entidade_id: e.nome for e in ent}
        elif ids and dim == "produto":
            prod = (
                await db.execute(
                    select(DimProduto.produto_id, DimProduto.nome).where(
                        DimProduto.tenant_id == tenant_id,
                        DimProduto.produto_id.in_(ids),
                    )
                )
            ).all()
            labels = {p.produto_id: p.nome for p in prod}

    def _label(chave: object) -> str:
        if dim == "natureza":
            return _NATUREZA_LABEL.get(chave or "NAO_CLASSIFICADO", str(chave))
        if dim == "subgrupo":
            return str(chave) if chave else "(sem subgrupo)"
        # cedente / produto
        if chave is None:
            return "(sem cedente)" if dim == "cedente" else "(sem produto)"
        return labels.get(chave, f"#{chave}")

    linhas = [
        DreBreakdownRow(
            chave="" if r.chave is None else str(r.chave),
            label=_label(r.chave),
            receita=r.receita or ZERO,
            custo=r.custo or ZERO,
            resultado=r.resultado or ZERO,
        )
        for r in rows
    ]
    linhas.sort(key=lambda x: x.receita, reverse=True)

    return DreBreakdownResponse(
        competencia=competencia,
        dim=dim,
        linhas=linhas,
        total_receita=sum((x.receita for x in linhas), start=ZERO),
        total_custo=sum((x.custo for x in linhas), start=ZERO),
        total_resultado=sum((x.resultado for x in linhas), start=ZERO),
    )


async def compute_drill_fornecedores(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    grupo_dre: str,
    subgrupo: str | None,
    descricao: str | None,
    competencia_de: date,
    competencia_ate: date,
    fundo_id: int | None = None,
    produto_id: int | None = None,
    fonte: str | None = None,
    top: int = 20,
) -> DreFornecedoresResponse:
    """Top N fornecedores dentro de um corte (grupo + opcional subgrupo + descricao).

    Ordenado por `abs(resultado)` desc -- captura fornecedores grandes
    independentemente do sinal (receita/custo).
    """
    corte: list[ColumnElement[bool]] = [DreMensal.grupo_dre == grupo_dre]
    if subgrupo is not None:
        corte.append(DreMensal.subgrupo == subgrupo)
    if descricao is not None:
        corte.append(DreMensal.descricao == descricao)

    # Conta total de fornecedores distintos no corte (antes do limit). Usado
    # pelo frontend pra sinalizar "exibindo top 20 de 150" quando truncar.
    count_stmt = select(
        func.count(func.distinct(DreMensal.fornecedor_documento))
    ).where(and_(*corte))
    count_stmt = _apply_filters(
        count_stmt,
        tenant_id=tenant_id,
        competencia_de=competencia_de,
        competencia_ate=competencia_ate,
        fundo_id=fundo_id,
        produto_id=produto_id,
        fonte=fonte,
    )
    total_fornecedores = (await db.execute(count_stmt)).scalar_one() or 0

    stmt = (
        select(
            DreMensal.fornecedor,
            DreMensal.fornecedor_documento,
            func.sum(DreMensal.receita).label("receita"),
            func.sum(DreMensal.custo).label("custo"),
            func.sum(DreMensal.resultado).label("resultado"),
            func.sum(DreMensal.quantidade).label("quantidade"),
        )
        .where(and_(*corte))
        .group_by(DreMensal.fornecedor, DreMensal.fornecedor_documento)
        .order_by(func.sum(func.abs(DreMensal.resultado)).desc())
        .limit(top)
    )
    stmt = _apply_filters(
        stmt,
        tenant_id=tenant_id,
        competencia_de=competencia_de,
        competencia_ate=competencia_ate,
        fundo_id=fundo_id,
        produto_id=produto_id,
        fonte=fonte,
    )
    rows = (await db.execute(stmt)).all()

    fornecedores = [
        DreFornecedorRow(
            fornecedor=r.fornecedor,
            fornecedor_documento=r.fornecedor_documento,
            receita=r.receita or ZERO,
            custo=r.custo or ZERO,
            resultado=r.resultado or ZERO,
            quantidade=int(r.quantidade or 0),
        )
        for r in rows
    ]

    return DreFornecedoresResponse(
        grupo_dre=grupo_dre,
        subgrupo=subgrupo,
        descricao=descricao,
        competencia_de=competencia_de,
        competencia_ate=competencia_ate,
        fornecedores=fornecedores,
        total_fornecedores=int(total_fornecedores),
    )
