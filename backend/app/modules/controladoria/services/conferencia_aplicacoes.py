"""Controladoria · Movimento de Aplicacoes (grupo Aplicacoes do balanco).

Deep em Fundos DI externo (capital vs valorizacao, cruzado com o demonstrativo
de caixa); light nas linhas menores (TPF/Compromissada/Outros, so ΔSaldo).
Op. Estruturadas (NC) fica fora — tem auditor proprio. Ver schema pro racional.

Silver-only (§13.2.1): wh_posicao_cota_fundo + wh_movimento_caixa + os _sum_*
canonicos (TPF/Compromissada/Outros) de cota_sub.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.conferencia_aplicacoes import (
    ConferenciaAplicacoesResponse,
    LinhaAplicacaoMenor,
    MovimentoFundoDI,
)
from app.modules.controladoria.services.cota_sub import (
    ZERO,
    _is_fundo_externo,
    _sum_compromissada,
    _sum_outros_ativos_nao_tpf,
    _sum_titulos_publicos,
)
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.movimento_caixa import MovimentoCaixa
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo

_TOL = Decimal("1.0")
# Band do cross-ref de caixa (timing/IR/arredondamento).
_BANDA_CAIXA = Decimal("2000.0")
# Abaixo disso, a linha menor e imaterial.
_MATERIAL = Decimal("1000.0")


def _fmt(v: Decimal) -> str:
    return f"R$ {float(v):,.2f}"


async def compute_movimento_aplicacoes(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> ConferenciaAplicacoesResponse:
    """Movimento do grupo Aplicacoes do dia (Fundos DI deep + linhas menores)."""
    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada")

    d1 = data_d1 or await dia_util_anterior_qitech(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    # ── Fundos DI externos: posicao por fundo em D-1 e D0 ───────────────────
    async def _load_fundos(data: date) -> dict[str, dict]:
        stmt = (
            select(
                PosicaoCotaFundo.ativo_nome,
                PosicaoCotaFundo.quantidade,
                PosicaoCotaFundo.valor_cota,
                PosicaoCotaFundo.valor_liquido,
            )
            .where(PosicaoCotaFundo.tenant_id == tenant_id)
            .where(PosicaoCotaFundo.unidade_administrativa_id == ua_id)
            .where(PosicaoCotaFundo.data_posicao == data)
        )
        out: dict[str, dict] = {}
        for nome, qtd, cota, vliq in (await db.execute(stmt)).all():
            if not _is_fundo_externo(nome or "", ua.nome):
                continue
            out[nome] = {
                "qtd": Decimal(qtd or 0),
                "cota": Decimal(cota or 0),
                "valor": Decimal(vliq or 0),
            }
        return out

    f1 = await _load_fundos(d1)
    f0 = await _load_fundos(data_d0)

    # ── Cross-ref: aplicacao/resgate de fundo no demonstrativo de caixa (D0) ─
    caixa_por_fundo = await _caixa_fundos(db, tenant_id, ua_id, data_d0)

    fundos_di: list[MovimentoFundoDI] = []
    delta_fundos = tot_capital = tot_valoriz = ZERO
    for nome in sorted(set(f1) | set(f0)):
        r1, r0 = f1.get(nome), f0.get(nome)
        v1 = r1["valor"] if r1 else ZERO
        v0 = r0["valor"] if r0 else ZERO
        qtd1 = r1["qtd"] if r1 else ZERO
        qtd0 = r0["qtd"] if r0 else ZERO
        cota0 = r0["cota"] if r0 else (r1["cota"] if r1 else ZERO)
        delta_valor = v0 - v1
        capital = (qtd0 - qtd1) * cota0  # >0 aplicou, <0 resgatou
        valoriz = delta_valor - capital
        delta_fundos += delta_valor
        tot_capital += capital
        tot_valoriz += valoriz

        if capital > _TOL:
            tipo = "aplicacao"
        elif capital < -_TOL:
            tipo = "resgate"
        else:
            tipo = "so_valorizacao"

        cx = caixa_por_fundo.get(nome, {"aplic": ZERO, "resg": ZERO})
        net_caixa = cx["aplic"] + cx["resg"]  # aplic<=0, resg>=0
        # posicao subiu (capital>0) <-> caixa saiu (net<0): net ~ -capital
        confirma = (
            (abs(capital) > _TOL or abs(net_caixa) > _TOL)
            and abs(net_caixa + capital) < _BANDA_CAIXA
        )

        if tipo == "so_valorizacao":
            bullet = f"{nome}: so rendimento DI de {_fmt(valoriz)} (sem aplicacao/resgate)."
        else:
            verbo = "aplicou" if tipo == "aplicacao" else "resgatou"
            bullet = (
                f"{nome}: {verbo} {_fmt(abs(capital))} de capital (liquido) + "
                f"{_fmt(valoriz)} de rendimento DI. "
                + ("Caixa confirma no demonstrativo." if confirma else "Sem casamento exato no caixa.")
            )

        fundos_di.append(
            MovimentoFundoDI(
                fundo_nome=nome, valor_d1=v1, valor_d0=v0, delta_valor=delta_valor,
                aplicacao_resgate=capital, valorizacao=valoriz, tipo=tipo,
                caixa_aplicacao=cx["aplic"], caixa_resgate=cx["resg"],
                caixa_confirma=confirma, bullet=bullet,
            )
        )
    fundos_di.sort(key=lambda m: -abs(m.delta_valor))

    # ── Linhas menores (TPF / Compromissada / Outros): so ΔSaldo ────────────
    outras: list[LinhaAplicacaoMenor] = []
    for key, label, fn in (
        ("titulos_publicos", "Títulos Públicos", _sum_titulos_publicos),
        ("compromissada", "Compromissada", _sum_compromissada),
        ("outros_ativos", "Outros Ativos", _sum_outros_ativos_nao_tpf),
    ):
        s1 = await fn(db, tenant_id, ua_id, d1)
        s0 = await fn(db, tenant_id, ua_id, data_d0)
        delta = s0 - s1
        if abs(s0) < _MATERIAL and abs(delta) < _MATERIAL:
            nota = "imaterial/vazia"
        elif abs(delta) >= _MATERIAL:
            nota = "movimento relevante — investigar"
        else:
            nota = "saldo presente, sem movimento no dia"
        outras.append(
            LinhaAplicacaoMenor(
                linha=key, label=label, valor_d1=s1, valor_d0=s0, delta=delta, nota=nota,
            )
        )

    delta_total = delta_fundos + sum((o.delta for o in outras), ZERO)

    return ConferenciaAplicacoesResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        fundos_di=fundos_di,
        delta_fundos_di=delta_fundos,
        total_capital_liquido=tot_capital,
        total_valorizacao=tot_valoriz,
        outras_linhas=outras,
        delta_aplicacoes_total=delta_total,
    )


async def _caixa_fundos(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data_d0: date,
) -> dict[str, dict[str, Decimal]]:
    """Aplicacao/resgate de fundo no demonstrativo de caixa (D0), por nome de fundo.

    Linhas: 'Aplicacao no Fundo <X> ...' (saidas <=0) e 'Resgate do Fundo <X> ...'
    (entradas >=0). Agrega por nome do fundo (substring da descricao).
    """
    stmt = (
        select(
            MovimentoCaixa.descricao,
            MovimentoCaixa.entradas,
            MovimentoCaixa.saidas,
        )
        .where(MovimentoCaixa.tenant_id == tenant_id)
        .where(func.date(MovimentoCaixa.data_liquidacao) == data_d0)
        .where(
            (MovimentoCaixa.unidade_administrativa_id == ua_id)
            | (MovimentoCaixa.unidade_administrativa_id.is_(None))
        )
        .where(
            or_(
                MovimentoCaixa.descricao.ilike("Aplica%Fundo%"),
                MovimentoCaixa.descricao.ilike("Resgate%Fundo%"),
            )
        )
    )
    rows = (await db.execute(stmt)).all()
    return _agrega_caixa_por_fundo(rows)


def _agrega_caixa_por_fundo(rows) -> dict[str, dict[str, Decimal]]:
    """Soma entradas (resgate) / saidas (aplicacao) por nome de fundo extraido."""
    out: dict[str, dict[str, Decimal]] = {}
    for descricao, entradas, saidas in rows:
        nome = _nome_fundo_da_descricao(descricao or "")
        if not nome:
            continue
        acc = out.setdefault(nome, {"aplic": ZERO, "resg": ZERO})
        acc["aplic"] += Decimal(saidas or 0)   # saidas vem <=0
        acc["resg"] += Decimal(entradas or 0)
    return out


def _nome_fundo_da_descricao(descricao: str) -> str | None:
    """Extrai o nome do fundo entre 'Fundo ' e ' [' na descricao do demonstrativo.

    Ex.: 'Aplicacao no Fundo ITAU SOBERANO REF SI [739704] a pagar...' -> 'ITAU SOBERANO REF SI'.
    """
    low = descricao
    idx = low.lower().find("fundo ")
    if idx < 0:
        return None
    resto = descricao[idx + len("fundo "):]
    corte = resto.find(" [")
    if corte < 0:
        corte = resto.find(" a ")
    return resto[:corte].strip() if corte > 0 else resto.strip() or None
