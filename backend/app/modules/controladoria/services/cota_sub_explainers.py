"""Controladoria · Cota Sub — explainers heuristicos da variacao do PL.

Cada heuristico responde "por que o PL Sub mexeu de D-1 pra D0?". Por ora
implementa apenas **PDD (categoria 3.2)**: cruza `wh_estoque_recebivel`
D-1 vs D0 por papel e materializa evidencias com cedente + sacado +
titulo + faixa antes/depois.

Plano completo + categorias futuras (MTM, Aporte, Movimento de cotas Sr/Mez,
Diferimento, Liquidacao, Aquisicao) em
`backend/docs/cota-sub-explainers-heuristicos.md`.

Convencoes:
- Sub absorve PDD: PDD sobe → PL Sub cai. `delta_brl = -Σ Δ valor_pdd`.
- Threshold filtra por `|delta_valor_pdd| > threshold_brl`. Default R$ 1.000.
- Top N (default 20) evidencias mostradas, ordenadas por `|delta|` DESC.
  Restante agregado em `outros_delta_brl`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub import (
    ExplicacaoVariacaoResponse,
    PddEvidencia,
    PddExplanation,
)
from app.modules.controladoria.services.cota_sub import _mec_classes
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.estoque_recebivel import EstoqueRecebivel

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────────────
# PDD (categoria 3.2)
# ─────────────────────────────────────────────────────────────────────────────


async def _pdd_diff(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
) -> list[PddEvidencia]:
    """Cruza estoque D-1 vs D0 por papel; devolve so onde |Δ valor_pdd| > threshold.

    FULL OUTER JOIN porque papel pode:
      - existir nos dois dias → diff direto
      - existir so em D-1 → liquidou/baixou (Δ = -valor_pdd_d1, reversao)
      - existir so em D0 → novo papel (Δ = +valor_pdd_d0, constituicao)
    """
    # Subqueries por dia
    d1q = (
        select(EstoqueRecebivel)
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data_d1)
        .subquery()
    )
    d0q = (
        select(EstoqueRecebivel)
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data_d0)
        .subquery()
    )

    # Chave do papel = (seu_numero, numero_documento). FULL OUTER JOIN.
    pdd_d1 = func.coalesce(d1q.c.valor_pdd, ZERO)
    pdd_d0 = func.coalesce(d0q.c.valor_pdd, ZERO)
    delta = pdd_d0 - pdd_d1

    stmt = (
        select(
            func.coalesce(d0q.c.seu_numero, d1q.c.seu_numero).label("seu_numero"),
            func.coalesce(d0q.c.numero_documento, d1q.c.numero_documento).label("numero_documento"),
            func.coalesce(d0q.c.tipo_recebivel, d1q.c.tipo_recebivel).label("tipo_recebivel"),
            func.coalesce(d0q.c.cedente_doc, d1q.c.cedente_doc).label("cedente_doc"),
            func.coalesce(d0q.c.cedente_nome, d1q.c.cedente_nome).label("cedente_nome"),
            func.coalesce(d0q.c.sacado_doc, d1q.c.sacado_doc).label("sacado_doc"),
            func.coalesce(d0q.c.sacado_nome, d1q.c.sacado_nome).label("sacado_nome"),
            func.coalesce(d0q.c.data_vencimento_ajustada, d1q.c.data_vencimento_ajustada).label(
                "data_vencimento_ajustada"
            ),
            func.coalesce(d0q.c.valor_nominal, d1q.c.valor_nominal).label("valor_nominal"),
            pdd_d1.label("valor_pdd_d1"),
            pdd_d0.label("valor_pdd_d0"),
            delta.label("delta_valor_pdd"),
            d1q.c.faixa_pdd.label("faixa_pdd_d1"),
            d0q.c.faixa_pdd.label("faixa_pdd_d0"),
        )
        .select_from(
            d0q.join(
                d1q,
                (d0q.c.seu_numero == d1q.c.seu_numero)
                & (d0q.c.numero_documento == d1q.c.numero_documento),
                full=True,
            )
        )
        .where(func.abs(delta) > threshold_brl)
        .order_by(func.abs(delta).desc())
    )

    rows = (await db.execute(stmt)).all()
    return [
        PddEvidencia(
            cedente_doc=r.cedente_doc,
            cedente_nome=r.cedente_nome,
            sacado_doc=r.sacado_doc,
            sacado_nome=r.sacado_nome,
            seu_numero=r.seu_numero,
            numero_documento=r.numero_documento,
            tipo_recebivel=r.tipo_recebivel,
            data_vencimento_ajustada=r.data_vencimento_ajustada,
            valor_nominal=Decimal(r.valor_nominal or 0),
            valor_pdd_d1=Decimal(r.valor_pdd_d1 or 0),
            valor_pdd_d0=Decimal(r.valor_pdd_d0 or 0),
            delta_valor_pdd=Decimal(r.delta_valor_pdd or 0),
            faixa_pdd_d1=r.faixa_pdd_d1,
            faixa_pdd_d0=r.faixa_pdd_d0,
        )
        for r in rows
    ]


def _fmt_brl(valor: Decimal) -> str:
    """Format Decimal as 'X.XXX,XX' (pt-BR thousand sep + decimal comma)."""
    raw = f"{valor:,.2f}"  # US format: '28,450.33'
    return raw.replace(",", "_").replace(".", ",").replace("_", ".")


def _build_pdd_narrative(evidencias: list[PddEvidencia], delta_brl: Decimal) -> str:
    """Texto pt-BR pronto pro card."""
    if not evidencias:
        return "PDD nao teve variacao relevante no periodo."

    aumentos = [e for e in evidencias if e.delta_valor_pdd > 0]
    reversoes = [e for e in evidencias if e.delta_valor_pdd < 0]
    top = evidencias[0]  # ordenado por |delta| DESC

    partes: list[str] = []
    if aumentos:
        partes.append(
            f"PDD aumentou em {len(aumentos)} {'papel' if len(aumentos) == 1 else 'papeis'}"
        )
    if reversoes:
        partes.append(
            f"foi revertida em {len(reversoes)} {'papel' if len(reversoes) == 1 else 'papeis'}"
        )

    base = " e ".join(partes) if partes else "PDD teve variacao"

    faixa_change = ""
    if top.faixa_pdd_d1 and top.faixa_pdd_d0 and top.faixa_pdd_d1 != top.faixa_pdd_d0:
        faixa_change = f", {top.faixa_pdd_d1}→{top.faixa_pdd_d0}"

    return (
        f"{base}, impacto liquido de R$ {_fmt_brl(delta_brl)} no PL Sub. "
        f"Maior movimento: {top.cedente_nome} / {top.sacado_nome} "
        f"(titulo {top.seu_numero}{faixa_change})."
    )


async def compute_pdd_explanation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
    top_n: int,
) -> PddExplanation | None:
    """Constroi a explanation de PDD. Devolve None se Δ total < threshold."""
    evidencias_all = await _pdd_diff(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_d0=data_d0,
        data_d1=data_d1,
        threshold_brl=threshold_brl,
    )

    if not evidencias_all:
        return None

    # Sub absorve: PDD sobe → PL cai. Sinal invertido.
    delta_brl_total = -sum((e.delta_valor_pdd for e in evidencias_all), ZERO)

    # Top N + agregado dos demais
    mostradas = evidencias_all[:top_n]
    fora_top = evidencias_all[top_n:]
    outros_delta = -sum((e.delta_valor_pdd for e in fora_top), ZERO)

    return PddExplanation(
        categoria="pdd",
        narrative=_build_pdd_narrative(evidencias_all, delta_brl_total),
        delta_brl=delta_brl_total,
        evidencias_total=len(evidencias_all),
        evidencias_mostradas=len(mostradas),
        outros_delta_brl=outros_delta,
        evidencias=mostradas,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Orquestrador
# ─────────────────────────────────────────────────────────────────────────────


async def compute_explicacao_variacao(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
    threshold_brl: Decimal = Decimal("1000"),
    top_n: int = 20,
) -> ExplicacaoVariacaoResponse:
    """Roda todos os explainers disponiveis e devolve a resposta consolidada.

    Por ora so PDD. Demais categorias entrarao em PRs incrementais
    appendando suas explanations a lista `explanations`.
    """
    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada no tenant")

    fundo_doc = ua.cnpj or ""
    d1 = data_d1 or await dia_util_anterior_qitech(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    # Δ PL Sub do dia (mesma logica de cota_sub.py — PL Sub = MEC patrimonio Sub Jr)
    classes_d1 = await _mec_classes(db, tenant_id, ua_id, ua.nome, d1)
    classes_d0 = await _mec_classes(db, tenant_id, ua_id, ua.nome, data_d0)
    delta_pl_sub = classes_d0["sub_jr"] - classes_d1["sub_jr"]

    explanations: list[PddExplanation] = []

    pdd = await compute_pdd_explanation(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_d0=data_d0,
        data_d1=d1,
        threshold_brl=threshold_brl,
        top_n=top_n,
    )
    if pdd is not None:
        explanations.append(pdd)

    soma_explicada = sum((e.delta_brl for e in explanations), ZERO)
    indeterminado = delta_pl_sub - soma_explicada

    return ExplicacaoVariacaoResponse(
        fundo_id=str(ua_id),
        data=data_d0,
        data_anterior=d1,
        delta_pl_sub=delta_pl_sub,
        threshold_brl=threshold_brl,
        top_n=top_n,
        explanations=explanations,
        indeterminado_brl=indeterminado,
    )
