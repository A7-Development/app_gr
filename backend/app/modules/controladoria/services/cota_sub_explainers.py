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
- Threshold filtra por `|delta_valor_pdd| > threshold_brl`. Default R$ 100 —
  calibrado em 2026-05-13 apos identificar que dias de constituicao rotineira
  (reclassificacao de faixa A→B em multiplos papeis pequenos) ficavam invisiveis
  com threshold R$ 1.000. Caso pratico: 12/05 REALINVEST teve 13 papeis acima
  de R$ 100 (1 cedente LANNA com 10 deles) e zero acima de R$ 1.000.
- Top N (default 20) evidencias mostradas, ordenadas por `|delta|` DESC.
  Restante agregado em `outros_delta_brl`.
- Frontend agrupa por `cedente_doc` em runtime quando >= 2 papeis do mesmo
  cedente — backend continua devolvendo lista plana de papeis.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub import (
    ApropriacaoExplanation,
    ClasseCotaKey,
    CosifOrigem,
    DiferimentoExplanation,
    EventoOperacionalEvidencia,
    EvidenciaCprLinha,
    Explanation,
    ExplicacaoVariacaoResponse,
    FluxoCaixaEvidencia,
    FluxoCaixaExplanation,
    MovimentoCarteiraEvidencia,
    MovimentoCarteiraExplanation,
    MtmEvidencia,
    MtmExplanation,
    OutrosExplanation,
    PddEvidencia,
    PddExplanation,
    RemuneracaoSrMezEvidencia,
    RemuneracaoSrMezExplanation,
)
from app.modules.controladoria.services.balancete_diario import (
    compute_balancete_diario,
)
from app.modules.controladoria.services.cota_sub import (
    _is_mezanino,
    _is_senior,
    _is_sub_jr,
)
from app.modules.controladoria.services.cota_sub_buckets.cosif_to_bucket import (
    classify_cosif,
    is_cotas_emitidas,
    is_ignored_for_pl,
)
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa

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
# CPR — helpers compartilhados (Diferimento + Apropriacao)
# ─────────────────────────────────────────────────────────────────────────────


async def _cpr_diff_by_descricao(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date,
    descricao_filters: list,
    threshold_brl: Decimal,
) -> list[EvidenciaCprLinha]:
    """Diff CPR D-1 vs D0 agrupando por `descricao` (mesma linha de CPR).

    Sub absorve todo movimento de CPR — sinal exibido na evidencia e o
    `Δvalor` puro do CPR (sem inversao). Caller decide se inverte ou nao
    pra `delta_brl` da Explanation conforme natureza da rubrica.

    `descricao_filters` e uma lista de clauses SQLAlchemy (LIKE/ILIKE) que
    sao ORadas. A funcao garante que o filtro casa em D-1 OU D0 (FULL JOIN).
    """
    from sqlalchemy import or_

    descricao_clause = or_(*descricao_filters)

    d1q = (
        select(
            CprMovimento.descricao,
            CprMovimento.historico_traduzido,
            func.sum(CprMovimento.valor).label("valor"),
        )
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data_d1)
        .where(descricao_clause)
        .group_by(CprMovimento.descricao, CprMovimento.historico_traduzido)
        .subquery()
    )
    d0q = (
        select(
            CprMovimento.descricao,
            CprMovimento.historico_traduzido,
            func.sum(CprMovimento.valor).label("valor"),
        )
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data_d0)
        .where(descricao_clause)
        .group_by(CprMovimento.descricao, CprMovimento.historico_traduzido)
        .subquery()
    )

    valor_d1 = func.coalesce(d1q.c.valor, ZERO)
    valor_d0 = func.coalesce(d0q.c.valor, ZERO)
    delta = valor_d0 - valor_d1

    stmt = (
        select(
            func.coalesce(d0q.c.descricao, d1q.c.descricao).label("descricao"),
            func.coalesce(
                d0q.c.historico_traduzido, d1q.c.historico_traduzido
            ).label("historico_traduzido"),
            valor_d1.label("valor_d1"),
            valor_d0.label("valor_d0"),
            delta.label("delta_valor"),
        )
        .select_from(
            d0q.join(d1q, d0q.c.descricao == d1q.c.descricao, full=True)
        )
        .where(func.abs(delta) > threshold_brl)
        .order_by(func.abs(delta).desc())
    )

    rows = (await db.execute(stmt)).all()
    return [
        EvidenciaCprLinha(
            descricao=r.descricao,
            historico_traduzido=r.historico_traduzido or r.descricao,
            valor_d1=Decimal(r.valor_d1 or 0),
            valor_d0=Decimal(r.valor_d0 or 0),
            delta_valor=Decimal(r.delta_valor or 0),
        )
        for r in rows
    ]


def _build_cpr_narrative(
    evidencias: list[EvidenciaCprLinha], delta_brl: Decimal, label: str
) -> str:
    """Texto curto pt-BR para narrative do card."""
    if not evidencias:
        return f"{label} nao teve variacao relevante no periodo."
    n = len(evidencias)
    sufixo = "rubrica" if n == 1 else "rubricas"
    top = evidencias[0]
    return (
        f"{label} em {n} {sufixo}, impacto liquido de R$ {_fmt_brl(delta_brl)} "
        f"no PL Sub. Maior movimento: {top.historico_traduzido} "
        f"(Δ R$ {_fmt_brl(top.delta_valor)})."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Diferimento (categoria 3.3.a)
# ─────────────────────────────────────────────────────────────────────────────


async def compute_diferimento_explanation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
    top_n: int,
) -> DiferimentoExplanation | None:
    """Detecta apropriacao mensal de despesas diferidas (CVM, Rating, ANBIMA).

    Filtro: `descricao LIKE 'Diferimento de despesa%'`. Rubricas diferidas
    sao positivas no CPR (saldo a apropriar); a cada dia diminuem em
    modulo a medida que sao amortizadas — esse `Δ` (negativo) flui pro PL
    Sub como despesa absorvida. `delta_brl` reflete diretamente o ΔCPR
    (Sub absorve sem inversao de sinal).
    """
    evidencias_all = await _cpr_diff_by_descricao(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        data_d0=data_d0,
        data_d1=data_d1,
        descricao_filters=[CprMovimento.descricao.like("Diferimento de despesa%")],
        threshold_brl=threshold_brl,
    )
    if not evidencias_all:
        return None

    delta_brl_total = sum((e.delta_valor for e in evidencias_all), ZERO)
    mostradas = evidencias_all[:top_n]
    fora_top = evidencias_all[top_n:]
    outros = sum((e.delta_valor for e in fora_top), ZERO)

    return DiferimentoExplanation(
        narrative=_build_cpr_narrative(
            evidencias_all, delta_brl_total, "Despesas diferidas apropriadas"
        ),
        delta_brl=delta_brl_total,
        evidencias_total=len(evidencias_all),
        evidencias_mostradas=len(mostradas),
        outros_delta_brl=outros,
        evidencias=mostradas,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Apropriacao de despesas/taxas (categoria 3.3.b)
# ─────────────────────────────────────────────────────────────────────────────


async def compute_apropriacao_explanation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
    top_n: int,
) -> ApropriacaoExplanation | None:
    """Detecta apropriacao de despesas/taxas operacionais (Adm, Custodia,
    Gestao, Auditoria, Consultoria, Cobranca, IOF, IR, SELIC, Banco
    Liquidante, REGISTRADORA).

    Cobre o leque mapeado no dicionario do CPR (CLAUDE.md / doc dos
    explainers). Sub absorve todos — `delta_brl` = ΔCPR puro.
    """
    filters = [
        CprMovimento.descricao.ilike("Taxa de % Apropriada"),
        CprMovimento.descricao.ilike("Despesa de %"),
        CprMovimento.descricao.ilike("Despesas com %"),
        CprMovimento.descricao.ilike("% a Pagar em %"),
        CprMovimento.descricao.ilike("IOF a Recolher%"),
        CprMovimento.descricao.ilike("IR a Recolher%"),
        CprMovimento.descricao.ilike("REGISTRADORA%"),
    ]
    evidencias_all = await _cpr_diff_by_descricao(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        data_d0=data_d0,
        data_d1=data_d1,
        descricao_filters=filters,
        threshold_brl=threshold_brl,
    )
    if not evidencias_all:
        return None

    delta_brl_total = sum((e.delta_valor for e in evidencias_all), ZERO)
    mostradas = evidencias_all[:top_n]
    fora_top = evidencias_all[top_n:]
    outros = sum((e.delta_valor for e in fora_top), ZERO)

    return ApropriacaoExplanation(
        narrative=_build_cpr_narrative(
            evidencias_all, delta_brl_total, "Apropriacao de despesas/taxas"
        ),
        delta_brl=delta_brl_total,
        evidencias_total=len(evidencias_all),
        evidencias_mostradas=len(mostradas),
        outros_delta_brl=outros,
        evidencias=mostradas,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fluxo de caixa do cotista (categorias 1.1 + 1.2)
# ─────────────────────────────────────────────────────────────────────────────


# Label amigavel da classe — usado nas evidencias.
_CLASSE_LABEL: dict[ClasseCotaKey, str] = {
    "sub_jr":   "Subordinada Jr",
    "mezanino": "Mezanino",
    "senior":   "Senior",
}


async def _mec_rows_por_classe(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    data: date,
) -> dict[ClasseCotaKey, MecEvolucaoCotas]:
    """Devolve {classe: row} com o MEC completo (aporte, retirada, qtd, cota).

    Diferente do `_mec_classes` (que ja agrega so o patrimonio), este precisa
    do row inteiro pra detectar fluxo de cotistas (aporte, retirada, Δqtd).
    """
    stmt = (
        select(MecEvolucaoCotas)
        .where(MecEvolucaoCotas.tenant_id == tenant_id)
        .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
        .where(MecEvolucaoCotas.data_posicao == data)
    )
    rows = (await db.execute(stmt)).scalars().all()
    out: dict[ClasseCotaKey, MecEvolucaoCotas] = {}
    for row in rows:
        nome = row.carteira_cliente_nome
        if _is_sub_jr(nome, ua_nome):
            out["sub_jr"] = row
        elif _is_mezanino(nome):
            out["mezanino"] = row
        elif _is_senior(nome):
            out["senior"] = row
    return out


async def _cpr_aporte_diff(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
) -> list[EvidenciaCprLinha]:
    """Linhas do CPR cuja descricao matcha 'Aporte%' e mexeram entre D-1 e D0.

    Reusa `_cpr_diff_by_descricao` mas com filtro especifico de Aporte.
    """
    return await _cpr_diff_by_descricao(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        data_d0=data_d0,
        data_d1=data_d1,
        descricao_filters=[CprMovimento.descricao.ilike("Aporte%")],
        threshold_brl=threshold_brl,
    )


def _build_fluxo_caixa_narrative(
    evidencias: list[FluxoCaixaEvidencia],
    eventos: list[EventoOperacionalEvidencia],
    delta_brl: Decimal,
) -> str:
    """Texto curto pt-BR descrevendo o fluxo do dia."""
    if not evidencias and not eventos:
        return "Nao houve fluxo de cotistas relevante no periodo."

    partes: list[str] = []

    if evidencias:
        n = len(evidencias)
        sufixo = "movimento" if n == 1 else "movimentos"
        # Maior movimento (em modulo do impacto)
        top = max(evidencias, key=lambda e: abs(e.impacto_pl_sub))
        acao = "aporte" if top.tipo == "aporte" else "resgate"
        partes.append(
            f"Fluxo de cotistas em {n} {sufixo}, impacto liquido de "
            f"R$ {_fmt_brl(delta_brl)} no PL Sub. Maior: {acao} de "
            f"R$ {_fmt_brl(top.valor_brl)} na classe {top.classe_label}."
        )

    if eventos:
        n_eng = sum(1 for e in eventos if e.tipo == "aporte_engaiolado")
        n_dev = sum(1 for e in eventos if e.tipo == "devolucao_engaiolado")
        if n_eng:
            partes.append(
                f"{n_eng} aporte(s) recebido(s) sem integralizacao em nenhuma classe "
                f"(provisao de devolucao criada — sem impacto no PL)."
            )
        if n_dev:
            partes.append(
                f"{n_dev} devolucao(oes) de aporte(s) anteriormente nao integralizado(s) "
                f"efetivada(s) no dia."
            )

    return " ".join(partes)


async def compute_fluxo_caixa_explanation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
) -> FluxoCaixaExplanation | None:
    """Detecta aporte/resgate por classe (Sub Jr, Mez, Sr) via MEC.

    Equacao Sub = Ativo - Passivo Contabil - Equity (Mez + Sr):
      - Aporte Sub      -> +Δ Sub
      - Resgate Sub     -> -Δ Sub
      - Aporte Mez/Sr   -> -Δ Sub  (cresce equity, Sub residual cai)
      - Resgate Mez/Sr  -> +Δ Sub  (equity reduz, Sub residual sobe)

    Detecta tambem aporte engaiolado: CPR `Aporte%` com Δ != 0 quando
    NENHUMA classe do MEC teve aporte/retirada real no dia. Caso pratico:
    REALINVEST 07/05/2026 (R$ 124.500 entrou no caixa, virou provisao de
    devolucao, devolvido 13/05). Eventos operacionais nao somam em
    `delta_brl` mas sao listados no card pra controller auditar.

    Threshold filtra ruido — abaixo dele, movimentos sao ignorados (ex.:
    arredondamentos centavos).
    """
    mec_d0 = await _mec_rows_por_classe(db, tenant_id, ua_id, ua_nome, data_d0)
    mec_d1 = await _mec_rows_por_classe(db, tenant_id, ua_id, ua_nome, data_d1)

    # 1) Aporte / Resgate com impacto - uma evidencia por (classe x tipo).
    # Sinal vem de Δqtd (mais robusto que confiar so em entradas/saidas, que
    # incluem ruido de taxas). Valor R$ vem de `entradas` (aporte) ou `saidas`
    # (resgate) do MEC. Os campos `aporte`/`retirada` nunca sao populados pelo
    # adapter QiTech atual — sao `entradas` / `saidas` que carregam o fluxo.
    evidencias: list[FluxoCaixaEvidencia] = []
    fluxo_total_mec = ZERO

    for classe in ("sub_jr", "mezanino", "senior"):
        row_d0 = mec_d0.get(classe)
        if row_d0 is None:
            continue

        entradas = Decimal(row_d0.entradas or 0)
        saidas = Decimal(row_d0.saidas or 0)
        fluxo_total_mec += entradas + saidas

        qtd_d0 = Decimal(row_d0.quantidade or 0)
        row_d1 = mec_d1.get(classe)
        qtd_d1 = Decimal(row_d1.quantidade or 0) if row_d1 else ZERO
        delta_qtd = qtd_d0 - qtd_d1

        cota_d0 = Decimal(row_d0.valor_da_cota or 0)
        label = _CLASSE_LABEL[classe]

        # Aporte: Δqtd > 0 e entradas > threshold (filtra taxas/encargos).
        if delta_qtd > 0 and entradas > threshold_brl:
            # Sub absorve direto (+), Mez/Sr absorvem inverso (-).
            impacto = entradas if classe == "sub_jr" else -entradas
            evidencias.append(FluxoCaixaEvidencia(
                tipo="aporte",
                classe=classe,
                classe_label=label,
                valor_brl=entradas,
                delta_qtd=delta_qtd,
                valor_cota_d0=cota_d0,
                impacto_pl_sub=impacto,
            ))

        # Resgate: Δqtd < 0 e saidas > threshold.
        if delta_qtd < 0 and saidas > threshold_brl:
            impacto = -saidas if classe == "sub_jr" else saidas
            evidencias.append(FluxoCaixaEvidencia(
                tipo="resgate",
                classe=classe,
                classe_label=label,
                valor_brl=saidas,
                delta_qtd=delta_qtd,
                valor_cota_d0=cota_d0,
                impacto_pl_sub=impacto,
            ))

    # 2) Eventos operacionais — aporte engaiolado / devolucao.
    # So conta como engaiolado se NENHUMA classe teve aporte/resgate REAL
    # no dia (sem evidencia regular acima). Se houve evidencia regular, o
    # CPR Aporte e contrapartida normal — nao classifica como engaiolado.
    eventos: list[EventoOperacionalEvidencia] = []
    if not evidencias:
        cpr_aporte = await _cpr_aporte_diff(
            db,
            tenant_id=tenant_id,
            ua_id=ua_id,
            data_d0=data_d0,
            data_d1=data_d1,
            threshold_brl=threshold_brl,
        )
        for linha in cpr_aporte:
            # delta < 0 → passivo cresceu (provisao criada) → aporte engaiolado.
            # delta > 0 → passivo extinto → devolucao.
            tipo: Literal["aporte_engaiolado", "devolucao_engaiolado"] = (
                "aporte_engaiolado" if linha.delta_valor < 0 else "devolucao_engaiolado"
            )
            valor_abs = abs(linha.delta_valor)
            detalhe = (
                "Aporte recebido sem integralizacao em nenhuma classe."
                if tipo == "aporte_engaiolado"
                else "Devolucao efetivada de aporte anteriormente nao integralizado."
            )
            eventos.append(EventoOperacionalEvidencia(
                tipo=tipo,
                descricao=linha.historico_traduzido or linha.descricao,
                valor_brl=valor_abs,
                detalhe=detalhe,
            ))

    if not evidencias and not eventos:
        return None

    delta_brl = sum((e.impacto_pl_sub for e in evidencias), ZERO)

    return FluxoCaixaExplanation(
        narrative=_build_fluxo_caixa_narrative(evidencias, eventos, delta_brl),
        delta_brl=delta_brl,
        evidencias=evidencias,
        eventos_operacionais=eventos,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Movimento de carteira (categoria 2.1 + 2.2)
# ─────────────────────────────────────────────────────────────────────────────


async def _movimento_carteira_diff(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
) -> tuple[list[MovimentoCarteiraEvidencia], Decimal, Decimal, int, int]:
    """Diff `wh_estoque_recebivel` D-1 vs D0 por (seu_numero, numero_documento).

    Devolve (evidencias, total_liquidado, total_adquirido, qtd_liq, qtd_adq).

    Critério:
      - papel em D-1 e NAO em D0 -> liquidado (saiu da carteira)
      - papel em D0 e NAO em D-1 -> adquirido (entrou na carteira)
      - papel em ambos -> sem movimento (continua aging)
      - threshold filtra papeis com valor_presente < threshold_brl
    """
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

    # FULL OUTER JOIN por (seu_numero, numero_documento)
    stmt = (
        select(
            func.coalesce(d0q.c.seu_numero, d1q.c.seu_numero).label("seu_numero"),
            func.coalesce(d0q.c.numero_documento, d1q.c.numero_documento).label("numero_documento"),
            func.coalesce(d0q.c.cedente_doc, d1q.c.cedente_doc).label("cedente_doc"),
            func.coalesce(d0q.c.cedente_nome, d1q.c.cedente_nome).label("cedente_nome"),
            func.coalesce(d0q.c.sacado_doc, d1q.c.sacado_doc).label("sacado_doc"),
            func.coalesce(d0q.c.sacado_nome, d1q.c.sacado_nome).label("sacado_nome"),
            func.coalesce(d0q.c.tipo_recebivel, d1q.c.tipo_recebivel).label("tipo_recebivel"),
            func.coalesce(d0q.c.valor_presente, d1q.c.valor_presente).label("valor_presente"),
            func.coalesce(d0q.c.valor_nominal, d1q.c.valor_nominal).label("valor_nominal"),
            func.coalesce(d0q.c.data_vencimento_ajustada, d1q.c.data_vencimento_ajustada).label("data_vencimento_ajustada"),
            d1q.c.id.label("existia_d1"),
            d0q.c.id.label("existia_d0"),
        )
        .select_from(
            d0q.join(
                d1q,
                (d0q.c.seu_numero == d1q.c.seu_numero)
                & (d0q.c.numero_documento == d1q.c.numero_documento),
                full=True,
            )
        )
        .where(
            # Papel girou (so existe em um dos dois lados)
            (d0q.c.id.is_(None) & d1q.c.id.is_not(None))
            | (d0q.c.id.is_not(None) & d1q.c.id.is_(None))
        )
    )
    rows = (await db.execute(stmt)).all()

    evidencias: list[MovimentoCarteiraEvidencia] = []
    total_liquidado = ZERO
    total_adquirido = ZERO
    qtd_liquidados = 0
    qtd_adquiridos = 0

    for r in rows:
        valor_presente = Decimal(r.valor_presente or 0)
        if valor_presente < threshold_brl:
            continue

        tipo = "adquirido" if r.existia_d0 is not None else "liquidado"
        if tipo == "liquidado":
            total_liquidado += valor_presente
            qtd_liquidados += 1
        else:
            total_adquirido += valor_presente
            qtd_adquiridos += 1

        evidencias.append(MovimentoCarteiraEvidencia(
            tipo=tipo,
            cedente_doc=r.cedente_doc or "",
            cedente_nome=r.cedente_nome or "",
            sacado_doc=r.sacado_doc or "",
            sacado_nome=r.sacado_nome or "",
            seu_numero=r.seu_numero or "",
            numero_documento=r.numero_documento or "",
            tipo_recebivel=r.tipo_recebivel or "",
            valor_brl=valor_presente,
            valor_nominal=Decimal(r.valor_nominal or 0),
            data_vencimento_ajustada=r.data_vencimento_ajustada,
        ))

    # Ordena por |valor| DESC pra tops aparecerem primeiro
    evidencias.sort(key=lambda e: abs(e.valor_brl), reverse=True)

    return evidencias, total_liquidado, total_adquirido, qtd_liquidados, qtd_adquiridos


def _build_movimento_carteira_narrative(
    qtd_liquidados: int,
    qtd_adquiridos: int,
    total_liquidado: Decimal,
    total_adquirido: Decimal,
) -> str:
    """Texto curto pt-BR descrevendo o giro do dia. Sempre informacional."""
    if qtd_liquidados == 0 and qtd_adquiridos == 0:
        return "Sem giro de carteira no periodo."

    partes: list[str] = []
    if qtd_liquidados > 0:
        s = "papel liquidado" if qtd_liquidados == 1 else "papeis liquidados"
        partes.append(f"{qtd_liquidados} {s} (R$ {_fmt_brl(total_liquidado)})")
    if qtd_adquiridos > 0:
        s = "papel adquirido" if qtd_adquiridos == 1 else "papeis adquiridos"
        partes.append(f"{qtd_adquiridos} {s} (R$ {_fmt_brl(total_adquirido)})")

    return (
        "Giro de carteira do dia: " + " - ".join(partes) + ". "
        "Movimento patrimonial neutro no PL Sub (caixa cresce/cai e DC cai/cresce "
        "no mesmo valor); diferencas residuais aparecem em PDD ou Apropriacao."
    )


async def compute_movimento_carteira_explanation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
    top_n: int,
) -> MovimentoCarteiraExplanation | None:
    """Detecta giro da carteira de DC entre D-1 e D0.

    Bucket informacional: `delta_brl = 0` sempre (movimento patrimonial
    neutro). Devolve None se nao houve papel girado acima do threshold.
    """
    evidencias_all, total_liq, total_adq, qtd_liq, qtd_adq = await _movimento_carteira_diff(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_d0=data_d0,
        data_d1=data_d1,
        threshold_brl=threshold_brl,
    )

    if not evidencias_all:
        return None

    mostradas = evidencias_all[:top_n]

    return MovimentoCarteiraExplanation(
        narrative=_build_movimento_carteira_narrative(
            qtd_liq, qtd_adq, total_liq, total_adq,
        ),
        delta_brl=ZERO,
        total_liquidado_brl=total_liq,
        total_adquirido_brl=total_adq,
        papeis_liquidados=qtd_liq,
        papeis_adquiridos=qtd_adq,
        evidencias_mostradas=len(mostradas),
        evidencias=mostradas,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Marcacao a mercado (categoria 4.1)
# ─────────────────────────────────────────────────────────────────────────────


async def _mtm_diff(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
) -> list[MtmEvidencia]:
    """Diff `wh_posicao_renda_fixa` D-1 vs D0 agregando por `codigo_lastro`.

    Por que agregar por lastro: o FIDC contabiliza varias "operacoes pegadas"
    internas onde o mesmo instrumento aparece como ativo (qtd +N) e passivo
    (qtd -N) em codigos distintos mas mesmo `codigo_lastro`. Isoladamente,
    cada lado tem MtM diario; juntos somam zero (operacao patrimonial neutra).
    Agregando por lastro, pares espelhados se cancelam naturalmente — sobram
    so os papeis com posicao liquida real (NTN-B Tesouro, NCs, debentures de
    terceiros).

    Devolve lastros com `Δqtd_agregada = 0` E `|Δvalor_agregado| > threshold`.
    Metadados (nome, emitente, codigo) vem do lado ativo (qtd > 0).
    """
    # 1) Carrega TODAS as posicoes dos 2 dias (sem agregar SQL) e agrupa
    #    em Python por codigo_lastro. Volumetria pequena (~50 papeis/dia
    #    pra REALINVEST) — agregar em Python e mais simples que SQL filter.
    stmt = (
        select(PosicaoRendaFixa)
        .where(PosicaoRendaFixa.tenant_id == tenant_id)
        .where(PosicaoRendaFixa.unidade_administrativa_id == ua_id)
        .where(PosicaoRendaFixa.data_posicao.in_([data_d1, data_d0]))
    )
    rows = (await db.execute(stmt)).scalars().all()

    # Agrupa por (data, codigo_lastro): acumula qtd, valor, e guarda lado ativo
    by_lastro: dict[date, dict[str, dict[str, object]]] = {data_d1: {}, data_d0: {}}
    for r in rows:
        agg = by_lastro[r.data_posicao].setdefault(
            r.codigo_lastro,
            {
                "qtd_total":    ZERO,
                "valor_total":  ZERO,
                # Lado ativo (qtd > 0): metadata exibida
                "codigo_ativo":      None,
                "nome_do_papel":     None,
                "emitente":          None,
                "indexador":         None,
                "data_vencimento":   None,
                "pu_ativo":          ZERO,
                "qtd_ativo":         ZERO,
            },
        )
        agg["qtd_total"] = (agg["qtd_total"] or ZERO) + Decimal(r.quantidade or 0)  # type: ignore[operator]
        agg["valor_total"] = (agg["valor_total"] or ZERO) + Decimal(r.valor_bruto or 0)  # type: ignore[operator]
        if r.quantidade > 0 and agg["codigo_ativo"] is None:
            agg["codigo_ativo"] = r.codigo
            agg["nome_do_papel"] = r.nome_do_papel
            agg["emitente"] = r.emitente
            agg["indexador"] = r.indexador
            agg["data_vencimento"] = r.data_vencimento
            agg["pu_ativo"] = Decimal(r.pu_mercado or 0)
            agg["qtd_ativo"] = Decimal(r.quantidade or 0)

    # 2) Diff por lastro: para cada lastro presente em D-1 OU D0, calcula
    #    delta agregado. Pares pegados tem soma ~0 dos 2 lados; ficam filtrados.
    all_lastros = set(by_lastro[data_d1].keys()) | set(by_lastro[data_d0].keys())
    out: list[MtmEvidencia] = []
    for lastro in all_lastros:
        d1 = by_lastro[data_d1].get(lastro)
        d0 = by_lastro[data_d0].get(lastro)
        if d1 is None or d0 is None:
            # Papel entrou ou saiu da carteira — NAO e MtM (e movimento de carteira)
            continue

        qtd_d1_total = d1["qtd_total"]
        qtd_d0_total = d0["qtd_total"]
        valor_d1_total = d1["valor_total"]
        valor_d0_total = d0["valor_total"]

        # Qtd liquida estavel (MtM puro)?
        if qtd_d1_total != qtd_d0_total:
            continue

        delta_valor = Decimal(valor_d0_total) - Decimal(valor_d1_total)  # type: ignore[arg-type]
        if abs(delta_valor) <= threshold_brl:
            continue

        # Metadados do lado ativo (preferencia D0; fallback D-1)
        meta_source = d0 if d0["codigo_ativo"] is not None else d1
        out.append(MtmEvidencia(
            codigo=str(meta_source["codigo_ativo"] or lastro),
            nome_do_papel=str(meta_source["nome_do_papel"] or ""),
            emitente=str(meta_source["emitente"] or ""),
            indexador=str(meta_source["indexador"] or ""),
            data_vencimento=meta_source["data_vencimento"],  # type: ignore[arg-type]
            quantidade=Decimal(meta_source["qtd_ativo"] or 0),  # type: ignore[arg-type]
            valor_d1=Decimal(valor_d1_total),  # type: ignore[arg-type]
            valor_d0=Decimal(valor_d0_total),  # type: ignore[arg-type]
            delta_valor=delta_valor,
            pu_d1=Decimal(d1["pu_ativo"] or 0),  # type: ignore[arg-type]
            pu_d0=Decimal(d0["pu_ativo"] or 0),  # type: ignore[arg-type]
        ))

    out.sort(key=lambda e: abs(e.delta_valor), reverse=True)
    return out


def _build_mtm_narrative(evidencias: list[MtmEvidencia], delta_brl: Decimal) -> str:
    """Texto curto pt-BR para narrative do card."""
    if not evidencias:
        return "Marcacao a mercado nao teve variacao relevante no periodo."
    n = len(evidencias)
    sufixo = "papel" if n == 1 else "papeis"
    top = max(evidencias, key=lambda e: abs(e.delta_valor))
    sinal_top = "subiu" if top.delta_valor > 0 else "caiu"
    return (
        f"Marcacao a mercado em {n} {sufixo}, impacto liquido de R$ "
        f"{_fmt_brl(delta_brl)} no PL Sub. Maior: {top.codigo} ({top.indexador}) "
        f"{sinal_top} R$ {_fmt_brl(abs(top.delta_valor))}."
    )


async def compute_mtm_explanation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
    top_n: int,
) -> MtmExplanation | None:
    """Detecta variacao de valor de papeis de renda fixa com qtd estavel.

    Sub absorve direto: papel sobe → Ativo cresce → PL Sub cresce. `delta_brl`
    = Σ Δvalor_bruto dos papeis com Δqtd=0 (sem inversao de sinal).
    """
    evidencias_all = await _mtm_diff(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        data_d0=data_d0,
        data_d1=data_d1,
        threshold_brl=threshold_brl,
    )
    if not evidencias_all:
        return None

    delta_brl_total = sum((e.delta_valor for e in evidencias_all), ZERO)
    mostradas = evidencias_all[:top_n]
    fora_top = evidencias_all[top_n:]
    outros = sum((e.delta_valor for e in fora_top), ZERO)

    return MtmExplanation(
        narrative=_build_mtm_narrative(evidencias_all, delta_brl_total),
        delta_brl=delta_brl_total,
        evidencias_total=len(evidencias_all),
        evidencias_mostradas=len(mostradas),
        outros_delta_brl=outros,
        evidencias=mostradas,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Remuneracao Sr/Mez (categoria 5.1)
# ─────────────────────────────────────────────────────────────────────────────


def _build_remuneracao_sr_mez_narrative(
    evidencias: list[RemuneracaoSrMezEvidencia],
    delta_brl: Decimal,
) -> str:
    if not evidencias:
        return "Cotas Senior e Mezanino sem variacao relevante de PL no periodo."
    partes: list[str] = []
    for ev in evidencias:
        sinal = "subiu" if ev.delta_pl > 0 else "caiu"
        partes.append(
            f"{ev.classe_label} {sinal} R$ {_fmt_brl(abs(ev.delta_pl))} "
            f"(+{(ev.delta_pct * 100):.4f}%)".replace(".", ",")
        )
    return (
        f"Sub absorveu R$ {_fmt_brl(abs(delta_brl))} de remuneracao das classes "
        f"mais senioes: {' e '.join(partes)}."
    )


async def compute_remuneracao_sr_mez_explanation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    data_d0: date,
    data_d1: date,
    threshold_brl: Decimal,
) -> RemuneracaoSrMezExplanation | None:
    """Detecta a remuneracao diaria das cotas Senior e Mezanino.

    Sub absorve com sinal invertido: ΔPL_Sr/Mez positivo -> -impacto no Sub
    (Sub paga subordinacao). Captura APENAS a parcela de valorizacao (exclui
    movimento de caixa: aporte/resgate ja entram em `fluxo_caixa`).

    Formula:
        delta_pl_classe_remuneracao = patrimonio_d0 - patrimonio_d1 - (entradas - saidas)
    """
    # Carrega todas as classes em D-1 e D0 num so SELECT
    stmt = (
        select(
            MecEvolucaoCotas.data_posicao,
            MecEvolucaoCotas.carteira_cliente_nome,
            MecEvolucaoCotas.patrimonio,
            MecEvolucaoCotas.valor_da_cota,
            MecEvolucaoCotas.entradas,
            MecEvolucaoCotas.saidas,
        )
        .where(MecEvolucaoCotas.tenant_id == tenant_id)
        .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
        .where(MecEvolucaoCotas.data_posicao.in_([data_d1, data_d0]))
    )
    rows = (await db.execute(stmt)).all()

    # Indexa por (data, classe_label) - so Sr/Mez interessam aqui
    by_day: dict[date, dict[str, dict[str, object]]] = {data_d1: {}, data_d0: {}}
    for data, carteira_nome, patrimonio, valor_cota, entradas, saidas in rows:
        if _is_senior(carteira_nome):
            key: Literal["senior", "mezanino"] = "senior"
        elif _is_mezanino(carteira_nome):
            key = "mezanino"
        else:
            continue  # Sub ou outra classe — pula
        by_day[data][key] = {
            "patrimonio":  Decimal(patrimonio or 0),
            "valor_cota":  Decimal(valor_cota or 0),
            "entradas":    Decimal(entradas or 0),
            "saidas":      Decimal(saidas or 0),
        }

    evidencias: list[RemuneracaoSrMezEvidencia] = []
    classes_meta: list[tuple[Literal["senior", "mezanino"], str]] = [
        ("senior",   "Senior"),
        ("mezanino", "Mezanino"),
    ]
    for classe_key, classe_label in classes_meta:
        d1_snap = by_day[data_d1].get(classe_key)
        d0_snap = by_day[data_d0].get(classe_key)
        if d1_snap is None or d0_snap is None:
            continue
        pl_d1 = Decimal(d1_snap["patrimonio"])  # type: ignore[arg-type]
        pl_d0 = Decimal(d0_snap["patrimonio"])  # type: ignore[arg-type]
        # Movimento de caixa do DIA D0 (aporte/resgate efetivado em D0 ja
        # esta refletido no patrimonio_d0). Subtrair pra isolar remuneracao.
        entradas_d0 = Decimal(d0_snap["entradas"])  # type: ignore[arg-type]
        saidas_d0 = Decimal(d0_snap["saidas"])  # type: ignore[arg-type]
        movimento_caixa = entradas_d0 - saidas_d0
        delta_pl_total = pl_d0 - pl_d1
        delta_pl_remuneracao = delta_pl_total - movimento_caixa
        if abs(delta_pl_remuneracao) <= threshold_brl:
            continue
        delta_pct = delta_pl_remuneracao / pl_d1 if pl_d1 != 0 else ZERO
        evidencias.append(RemuneracaoSrMezEvidencia(
            classe=classe_key,
            classe_label=classe_label,
            pl_d1=pl_d1,
            pl_d0=pl_d0,
            delta_pl=delta_pl_remuneracao,
            delta_pct=delta_pct,
            valor_cota_d1=Decimal(d1_snap["valor_cota"]),  # type: ignore[arg-type]
            valor_cota_d0=Decimal(d0_snap["valor_cota"]),  # type: ignore[arg-type]
            impacto_pl_sub=-delta_pl_remuneracao,
        ))

    if not evidencias:
        return None

    delta_brl_sub = sum((e.impacto_pl_sub for e in evidencias), ZERO)
    return RemuneracaoSrMezExplanation(
        narrative=_build_remuneracao_sr_mez_narrative(evidencias, delta_brl_sub),
        delta_brl=delta_brl_sub,
        evidencias=evidencias,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Particionamento COSIF (refactor 2026-05-17 — balancete = fonte de verdade)
# ─────────────────────────────────────────────────────────────────────────────


def _particionar_folhas_cosif(bal) -> tuple[dict[str, list[CosifOrigem]], list[CosifOrigem]]:
    """Particiona folhas COSIF do balancete em buckets.

    Cotas emitidas (6.1.1.70.*) sao quebradas por classe via
    `classe_breakdown_por_cosif`: parcela Sr+Mez vai pra `remuneracao_sr_mez`,
    parcela Sub vai pra `fluxo_caixa`.

    Retorna `(bucket_origins, unmapped)` onde:
        - bucket_origins[bucket_id] = lista de CosifOrigem do bucket
        - unmapped = lista de CosifOrigem sem mapping (vira bucket "outros")
    """
    # Detecta folhas analiticas: nodes sem filhos.
    codigos = {n.codigo for n in bal.nodes if n.codigo}
    folhas = [
        n for n in bal.nodes
        if n.codigo and not any(
            c != n.codigo and c.startswith(n.codigo + ".") for c in codigos if c
        )
    ]

    bucket_origins: dict[str, list[CosifOrigem]] = {
        "pdd": [], "ajustes_contabeis": [], "fluxo_caixa": [],
        "movimento_carteira": [], "mtm": [], "remuneracao_sr_mez": [],
    }
    unmapped: list[CosifOrigem] = []

    for n in folhas:
        if n.codigo is None or is_ignored_for_pl(n.codigo):
            continue

        if is_cotas_emitidas(n.codigo):
            # Quebra por classe: Sr+Mez -> remuneracao, Sub -> fluxo_caixa
            for b in bal.classe_breakdown_por_cosif.get(n.codigo, []):
                sub_origem = CosifOrigem(
                    codigo=n.codigo,
                    nome=f"{n.nome} ({b.classe})",
                    d_minus_1=b.d_minus_1,
                    d_zero=b.d_zero,
                    delta=b.delta,
                )
                if b.classe in ("senior", "mezanino"):
                    bucket_origins["remuneracao_sr_mez"].append(sub_origem)
                elif b.classe == "subordinado":
                    bucket_origins["fluxo_caixa"].append(sub_origem)
                # outras classes (compensacao, aporte) — ignoradas
            continue

        origem = CosifOrigem(
            codigo=n.codigo, nome=n.nome,
            d_minus_1=n.d_minus_1, d_zero=n.d_zero, delta=n.delta,
        )
        bucket = classify_cosif(n.codigo)
        if bucket is None:
            unmapped.append(origem)
            continue
        # Mapeia bucket id (cosif_to_bucket) -> categoria do schema:
        #   "renda_fixa" -> "mtm" (categoria schema permanece "mtm" pra evitar
        #    migration; nome de exibicao "Renda Fixa" muda no frontend).
        cat = "mtm" if bucket == "renda_fixa" else bucket
        bucket_origins[cat].append(origem)

    return bucket_origins, unmapped


def _delta_bucket(origens: list[CosifOrigem]) -> Decimal:
    return sum((o.delta for o in origens), ZERO)


# ─────────────────────────────────────────────────────────────────────────────
# Orquestrador (refactor 2026-05-17)
# ─────────────────────────────────────────────────────────────────────────────


async def compute_explicacao_variacao(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
    threshold_brl: Decimal = Decimal("100"),
    top_n: int = 20,
) -> ExplicacaoVariacaoResponse:
    """Decompoe ΔPL Sub em buckets a partir do balancete COSIF.

    Refactor 2026-05-17 — "balancete = fonte de verdade":
        1. Carrega balancete diario (COSIF particionado, fonte de verdade)
        2. Particiona folhas COSIF em buckets via `classify_cosif`
        3. delta_brl de cada bucket = Σ Δ folhas COSIF mapeadas
        4. Heuristicas existentes (MEC/CPR/RF) viram enriquecedoras de
           `evidencias[]` — narrativa rica, NUNCA mais calculam delta_brl
        5. Bucket "outros" so aparece com folhas COSIF sem mapping (raro)
        6. `divergencia_mec_contabil` = resíduo de reconciliacao MEC vs COSIF

    Σ explanations.delta_brl ≡ delta_pl_sub_contabil POR CONSTRUCAO.
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

    # 1. Balancete completo (compute_balancete_diario ja resolve d1 quando None)
    bal = await compute_balancete_diario(
        db, tenant_id=tenant_id, fundo_id=ua_id,
        data_d_zero=data_d0, data_d_minus_1=data_d1,
    )
    d1 = bal.data_d_minus_1

    # 2. Particiona folhas COSIF em buckets
    bucket_origins, unmapped_origins = _particionar_folhas_cosif(bal)

    # 3. Roda heuristicas (mantem evidencias enriquecidas). delta_brl de cada
    #    Explanation sera SOBRESCRITO pela soma do bucket COSIF.
    explanations: list[Explanation] = []

    pdd = await compute_pdd_explanation(
        db, tenant_id=tenant_id, fundo_doc=fundo_doc,
        data_d0=data_d0, data_d1=d1,
        threshold_brl=threshold_brl, top_n=top_n,
    )
    pdd_origins = bucket_origins.get("pdd", [])
    pdd_delta = _delta_bucket(pdd_origins)
    if pdd is not None:
        pdd.delta_brl = pdd_delta
        pdd.cosif_origin = pdd_origins
        explanations.append(pdd)
    elif pdd_delta != ZERO:
        # COSIF tem variacao, heuristica nao devolveu — gera explanation
        # so com origem contabil (sem evidencias enriquecidas).
        explanations.append(PddExplanation(
            narrative=f"Variacao de PDD de R$ {_fmt_brl(pdd_delta)} apurada no balancete COSIF.",
            delta_brl=pdd_delta,
            evidencias_total=0, evidencias_mostradas=0,
            outros_delta_brl=ZERO, evidencias=[],
            cosif_origin=pdd_origins,
        ))

    # Ajustes contabeis: heuristicas devolvem 2 (diferimento + apropriacao),
    # mas o bucket COSIF e UM so. Override delta_brl proporcionalmente OU
    # entregar agregado? Por enquanto: cada heuristica mantem suas
    # evidencias e o delta vem do COSIF total dividido proporcionalmente.
    # Solucao simples: ambas Explanations apontam pro mesmo conjunto de
    # COSIFs; UI agrega no DriversCard (buildDriverFromAjustesContabeis).
    diferimento = await compute_diferimento_explanation(
        db, tenant_id=tenant_id, ua_id=ua_id,
        data_d0=data_d0, data_d1=d1,
        threshold_brl=threshold_brl, top_n=top_n,
    )
    apropriacao = await compute_apropriacao_explanation(
        db, tenant_id=tenant_id, ua_id=ua_id,
        data_d0=data_d0, data_d1=d1,
        threshold_brl=threshold_brl, top_n=top_n,
    )
    ajustes_origins = bucket_origins.get("ajustes_contabeis", [])
    ajustes_delta_total = _delta_bucket(ajustes_origins)

    # Reparte o delta entre Diferimento e Apropriacao proporcionalmente ao
    # delta heuristico (mantem ratio); se ambos heuristicos sao 0, joga 100%
    # em apropriacao (categoria mais abrangente).
    if diferimento is not None or apropriacao is not None or ajustes_delta_total != ZERO:
        d_h = diferimento.delta_brl if diferimento else ZERO
        a_h = apropriacao.delta_brl if apropriacao else ZERO
        total_h = abs(d_h) + abs(a_h)
        if total_h == ZERO:
            # heuristicas vazias — tudo cai em apropriacao
            d_share = ZERO
            a_share = ajustes_delta_total
        else:
            d_share = ajustes_delta_total * (abs(d_h) / total_h)
            a_share = ajustes_delta_total - d_share
        if diferimento is not None:
            diferimento.delta_brl = d_share
            diferimento.cosif_origin = ajustes_origins  # ambas apontam pro mesmo set
            explanations.append(diferimento)
        if apropriacao is not None:
            apropriacao.delta_brl = a_share
            apropriacao.cosif_origin = ajustes_origins
            explanations.append(apropriacao)
        elif a_share != ZERO:
            explanations.append(ApropriacaoExplanation(
                narrative=f"Apropriacao contabil de R$ {_fmt_brl(a_share)} apurada no balancete COSIF.",
                delta_brl=a_share,
                evidencias_total=0, evidencias_mostradas=0,
                outros_delta_brl=ZERO, evidencias=[],
                cosif_origin=ajustes_origins,
            ))

    fluxo_caixa = await compute_fluxo_caixa_explanation(
        db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome,
        data_d0=data_d0, data_d1=d1, threshold_brl=threshold_brl,
    )
    fluxo_origins = bucket_origins.get("fluxo_caixa", [])
    fluxo_delta = _delta_bucket(fluxo_origins)
    if fluxo_caixa is not None:
        fluxo_caixa.delta_brl = fluxo_delta
        fluxo_caixa.cosif_origin = fluxo_origins
        explanations.append(fluxo_caixa)
    elif fluxo_delta != ZERO:
        explanations.append(FluxoCaixaExplanation(
            narrative=f"Aporte/resgate Sub apurado no balancete COSIF: R$ {_fmt_brl(fluxo_delta)}.",
            delta_brl=fluxo_delta,
            evidencias=[], eventos_operacionais=[],
            cosif_origin=fluxo_origins,
        ))

    movimento_carteira = await compute_movimento_carteira_explanation(
        db, tenant_id=tenant_id, fundo_doc=fundo_doc,
        data_d0=data_d0, data_d1=d1,
        threshold_brl=threshold_brl, top_n=top_n,
    )
    mov_origins = bucket_origins.get("movimento_carteira", [])
    mov_delta = _delta_bucket(mov_origins)
    if movimento_carteira is not None:
        movimento_carteira.delta_brl = mov_delta
        movimento_carteira.cosif_origin = mov_origins
        explanations.append(movimento_carteira)
    elif mov_delta != ZERO:
        explanations.append(MovimentoCarteiraExplanation(
            narrative=f"Movimento de carteira apurado no balancete COSIF: R$ {_fmt_brl(mov_delta)}.",
            delta_brl=mov_delta,
            total_liquidado_brl=ZERO, total_adquirido_brl=ZERO,
            papeis_liquidados=0, papeis_adquiridos=0,
            evidencias_mostradas=0, evidencias=[],
            cosif_origin=mov_origins,
        ))

    mtm = await compute_mtm_explanation(
        db, tenant_id=tenant_id, ua_id=ua_id,
        data_d0=data_d0, data_d1=d1,
        threshold_brl=threshold_brl, top_n=top_n,
    )
    mtm_origins = bucket_origins.get("mtm", [])
    mtm_delta = _delta_bucket(mtm_origins)
    if mtm is not None:
        mtm.delta_brl = mtm_delta
        mtm.cosif_origin = mtm_origins
        explanations.append(mtm)
    elif mtm_delta != ZERO:
        explanations.append(MtmExplanation(
            narrative=f"Variacao de Renda Fixa apurada no balancete COSIF: R$ {_fmt_brl(mtm_delta)}.",
            delta_brl=mtm_delta,
            evidencias_total=0, evidencias_mostradas=0,
            outros_delta_brl=ZERO, evidencias=[],
            cosif_origin=mtm_origins,
        ))

    remuneracao_sr_mez = await compute_remuneracao_sr_mez_explanation(
        db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome,
        data_d0=data_d0, data_d1=d1, threshold_brl=threshold_brl,
    )
    rem_origins = bucket_origins.get("remuneracao_sr_mez", [])
    rem_delta = _delta_bucket(rem_origins)
    if remuneracao_sr_mez is not None:
        remuneracao_sr_mez.delta_brl = rem_delta
        remuneracao_sr_mez.cosif_origin = rem_origins
        explanations.append(remuneracao_sr_mez)
    elif rem_delta != ZERO:
        explanations.append(RemuneracaoSrMezExplanation(
            narrative=f"Remuneracao Sr/Mez apurada no balancete COSIF: R$ {_fmt_brl(rem_delta)}.",
            delta_brl=rem_delta,
            evidencias=[],
            cosif_origin=rem_origins,
        ))

    # 4. Bucket "outros" - folhas COSIF sem mapping (deve ser zero em regime)
    indeterminado = _delta_bucket(unmapped_origins)
    if unmapped_origins:
        explanations.append(OutrosExplanation(
            narrative=(
                f"{len(unmapped_origins)} folha(s) COSIF sem mapping definido. "
                f"Adicionar em `cota_sub/cosif_to_bucket.py`. Em regime estavel "
                f"este bucket deve ser zero."
            ),
            delta_brl=indeterminado,
            cosif_origin=unmapped_origins,
        ))

    # 5. Reconciliacao MEC vs Contabil
    delta_pl_sub_mec = bal.reconciliacao.delta_pl_cota_sub_real
    delta_pl_sub_contabil = bal.reconciliacao.delta_pl_cota_sub_esperado
    divergencia = delta_pl_sub_mec - delta_pl_sub_contabil  # = bal.reconciliacao.residuo

    return ExplicacaoVariacaoResponse(
        fundo_id=str(ua_id),
        data=data_d0,
        data_anterior=d1,
        delta_pl_sub=delta_pl_sub_mec,
        delta_pl_sub_contabil=delta_pl_sub_contabil,
        divergencia_mec_contabil=divergencia,
        threshold_brl=threshold_brl,
        top_n=top_n,
        explanations=explanations,
        indeterminado_brl=indeterminado,
    )
