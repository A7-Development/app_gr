"""Controladoria · Cota Sub — service de Variacoes do Dia.

Decompoe o Δ do PL Sub Jr entre D-1 e D0 em 3 fluxos auditaveis:

    1. APROPRIACOES (regime competencia)
       ΔCPR positivos D-1→D0: provisoes que cresceram no dia
       (Consultoria/Cobranca +R$ 2.500/dia, taxas Adm/Cust/Gestao apropriadas, etc.)

    2. PAGAMENTOS EFETIVADOS (regime caixa)
       Saidas de wh_movimento_caixa em D0 — quando o dinheiro saiu da CC.

    3. ANOMALIAS
       Pagamentos efetivados em D0 cujo descricao/historico NAO casa com nenhuma
       provisao do CPR de D-1 — indica gasto sem provisao previa (possivel fraude,
       erro operacional, ou despesa emergencial nao planejada).

CRUZAMENTO de auditoria: ΔPassivo Contabil deve = Σ apropriacoes (regime competencia
consistente). Se nao bater, ha movimentacao atipica que precisa de revisao manual.

Origem dos dados — apenas silver canonico (CLAUDE.md §13.2.1):
  - wh_cpr_movimento  → apropriacoes (Δ entre D-1 e D0)
  - wh_movimento_caixa → pagamentos (saidas em D0)
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub import (
    ConferenciaVariacao,
    VariacaoItem,
    VariacoesDiaResponse,
)
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.movimento_caixa import MovimentoCaixa

ZERO = Decimal("0")


# Classificacao de movimentos do CPR em contas COSIF analiticas. Relocado de
# `services/balanco.py` em 2026-05-28 ao remover o balanco antigo / engine COSIF
# — este matcher por palavra-chave do historico_traduzido (NAO usa o classifier
# COSIF DB-backed, ja removido) alimenta a conciliacao pagamento->provisao da
# pagina Pagamento Diario (/variacoes-dia), unico consumidor vivo. Migrar pra
# vocabulario neutro e followup (a pagina ainda fala "COSIF" no detalhamento).
CPR_COSIF_META: dict[str, tuple[str, str]] = {
    # cosif: (label, natureza_atual_no_balanco — 'A'=Ativo, 'P'=Passivo)
    "1.8.4.30.00": ("DEVEDORES - CONTA LIQUIDAÇÕES PENDENTES", "A"),
    "1.9.9.10":    ("DESPESAS ANTECIPADAS",                    "A"),
    "4.9.1.10":    ("IOF A RECOLHER",                          "P"),
    "4.9.9.30":    ("PROVISÃO PARA PAGAMENTOS A EFETUAR",      "P"),
    "4.9.9.83":    ("VALORES A PAGAR À SOCIEDADE ADMINISTRADORA", "P"),
}


def _classify_cpr_cosif(historico: str, valor: Decimal) -> str:
    """Mapeia item do CPR para conta COSIF analitica baseada em historico_traduzido.

    Retorna 1 das 5 contas:
      ATIVO:
        '1.8.4.30.00'  Devedores - Conta Liquidacoes Pendentes
        '1.9.9.10'     Despesas antecipadas (diferimentos)
      PASSIVO:
        '4.9.1.10'     IOF a Recolher
        '4.9.9.30'     Provisao para pagamentos a efetuar
        '4.9.9.83'     Valores a Pagar Sociedade Administradora

    PRECEDENCIA importa: alguns padroes sao substring uns dos outros.
    Ex.: 'BANCO LIQUIDANTE' contem 'LIQUIDA' — checar 'BANCO LIQ' antes.
    """
    h = (historico or "").upper()

    # 1) Banco Liquidante (despesa adm) — checar ANTES de qualquer pattern de "LIQUID*"
    if "BANCO LIQ" in h:
        return "4.9.9.30"

    # 2) Diferimentos (Ativo - Despesas Antecipadas)
    if "DIFER" in h:
        return "1.9.9.10"

    # 3) IOF / tributos
    if "IOF" in h:
        return "4.9.1.10"

    # 4) Liquidacoes em transito / TED / Baixa / Compensacao / Aquisicao
    #    (Ativo - 1.8.4.30.00). Use 'LIQUIDADO' (não 'LIQUIDA') para evitar
    #    falso match em 'LIQUIDANTE'.
    if any(k in h for k in (
        "LIQUIDADO", "LIQUIDAÇÃO", "LIQUIDACAO",  # snapshots de operações já liquidadas
        "TED",                                     # transferencias em transito
        "BAIXA",                                   # baixas operacionais
        "AQUISIC",                                 # TED para aquisicao de ativos
        "COMPENSAÇÃO", "COMPENSACAO",              # ajuste de compensacao de cotas
        "DEVOLUÇÃO", "DEVOLUCAO",                  # devolucao de pagamento em duplicidade
    )):
        return "1.8.4.30.00"

    # 5) Taxas correntes apropriadas (4.9.9.83)
    if "TAXA" in h and any(k in h for k in ("ADMINISTRA", "CUSTODIA", "CUSTÓDIA", "GESTAO", "GESTÃO")):
        return "4.9.9.83"

    # 6) Despesas administrativas pontuais (4.9.9.30)
    if any(k in h for k in ("AUDITOR", "CONSULTOR", "COBRAN", "SELIC", "ANBIMA", "CVM")):
        return "4.9.9.30"

    # Defaults pelo sinal — conservadores
    return "4.9.9.30" if valor < 0 else "1.8.4.30.00"


# Keywords de match: pagamento → provisao (palavras canonicas em UPPER).
# Ex.: pagamento com descricao "Agente de Cobranca" deve casar com provisao
# cuja historico_traduzido contem "COBRAN".
_PAGTO_KEYWORDS = (
    "AUDITOR", "CONSULTOR", "COBRAN", "TAXA",
    "CUSTODIA", "CUSTÓDIA", "GESTAO", "GESTÃO",
    "ADMINISTRA", "BANCO LIQ", "SELIC", "ANBIMA", "CVM", "IOF",
    "DIFER",
)


def _extract_keyword(texto: str | None) -> str | None:
    """Devolve a primeira keyword canonica encontrada no texto (UPPER)."""
    t = (texto or "").upper()
    for k in _PAGTO_KEYWORDS:
        if k in t:
            return k
    return None


async def compute_variacoes_dia(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id:     UUID,
    data_d0:   date,
    data_d1:   date | None = None,
) -> VariacoesDiaResponse:
    """Monta o painel de Variacoes do Dia para D-1 → D0.

    Lanca ValueError se a UA nao for encontrada.
    """
    ua = await db.get(UnidadeAdministrativa, ua_id)
    if ua is None or ua.tenant_id != tenant_id:
        raise ValueError(f"Unidade administrativa {ua_id} nao encontrada para o tenant.")

    # D-1 via fonte de verdade (wh_dia_util_qitech) — mesma do Calendar.
    d_d1 = data_d1 or await dia_util_anterior_qitech(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 1. APROPRIACOES — Δ CPR positivos (provisao cresceu) entre D-1 e D0.
    #    Importante: na nossa convencao Passivo (4.9.x) tem valores ABS,
    #    Ativo (1.8.x, 1.9.x) tem valores com sinal. Apropriacao (provisao
    #    crescendo no Passivo) eh positiva. No Ativo, queremos Δ positivo
    #    tambem (ex.: deferimento aumentou).
    # ─────────────────────────────────────────────────────────────────────────
    stmt_cpr = (
        select(
            CprMovimento.data_posicao,
            CprMovimento.historico_traduzido,
            CprMovimento.descricao,
            CprMovimento.valor,
        )
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao.in_([d_d1, data_d0]))
    )
    # Estrutura: {historico_lower: {date: valor (com sinal de display)}}
    cpr_by_hist: dict[str, dict[date, Decimal]] = {}
    cpr_metadata: dict[str, dict[str, str]] = {}  # {historico_lower: {descricao, cosif, label}}

    for d, historico, descricao, raw_valor in (await db.execute(stmt_cpr)).all():
        v = Decimal(raw_valor or 0)
        cosif = _classify_cpr_cosif(historico, v)
        is_passivo = CPR_COSIF_META.get(cosif, ("", "A"))[1] == "P"
        v_display = abs(v) if is_passivo else v

        key = (historico or "").strip().lower()
        if key not in cpr_by_hist:
            cpr_by_hist[key] = {d_d1: ZERO, data_d0: ZERO}
            cpr_metadata[key] = {
                "historico":  historico or "",
                "descricao":  descricao or "",
                "cosif":      cosif,
                "label":      historico or "(sem histórico)",
            }
        cpr_by_hist[key][d] = Decimal(cpr_by_hist[key].get(d, ZERO) or 0) + v_display

    apropriacoes: list[VariacaoItem] = []
    apropriacoes_total = ZERO
    for hist_key, vals in cpr_by_hist.items():
        delta = (vals.get(data_d0, ZERO) or ZERO) - (vals.get(d_d1, ZERO) or ZERO)
        if delta <= 0:
            continue  # Apenas variacao positiva = provisao cresceu (apropriacao)
        meta = cpr_metadata[hist_key]
        apropriacoes.append(VariacaoItem(
            cosif     = meta["cosif"] or None,
            label     = meta["label"],
            historico = meta["historico"] or None,
            descricao = meta["descricao"] or None,
            valor     = delta,
        ))
        apropriacoes_total += delta

    apropriacoes.sort(key=lambda i: float(i.valor), reverse=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. PAGAMENTOS EFETIVADOS — saidas em wh_movimento_caixa em D0.
    # ─────────────────────────────────────────────────────────────────────────
    stmt_pagto = (
        select(
            MovimentoCaixa.data_liquidacao,
            MovimentoCaixa.descricao,
            MovimentoCaixa.historico_traduzido,
            MovimentoCaixa.saidas,
        )
        .where(MovimentoCaixa.tenant_id == tenant_id)
        .where(MovimentoCaixa.unidade_administrativa_id == ua_id)
        .where(MovimentoCaixa.data_liquidacao == data_d0)
        .where(MovimentoCaixa.saidas < 0)  # apenas saidas (negativas)
    )
    pagamentos:        list[VariacaoItem] = []
    anomalias:         list[VariacaoItem] = []
    pagamentos_total = ZERO

    # Set de keywords vistas no CPR nos ULTIMOS 30 DIAS (cobre ciclo mensal
    # completo). Permite matchar pagamento mesmo quando a provisao foi zerada
    # dias antes de D-1 (ex.: provisao de Consultoria em 28/03 pago em 31/03,
    # com CPR ja vazio em 30/03).
    janela_inicio = data_d0 - timedelta(days=30)
    stmt_cpr_janela = (
        select(distinct(CprMovimento.historico_traduzido))
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao.between(janela_inicio, data_d0))
        .where(CprMovimento.valor != 0)
    )
    cpr_seen_keywords: set[str] = set()
    for (hist,) in (await db.execute(stmt_cpr_janela)).all():
        kw = _extract_keyword(hist)
        if kw:
            cpr_seen_keywords.add(kw)

    # Filtrar movimento_caixa: APENAS saidas com keyword de despesa.
    # Movimentos operacionais (Aplicacao no Fundo, Compra de Titulo, etc.)
    # NAO entram aqui — sao do fluxo de portfolio, nao do fluxo de despesas.
    for _data_liq, descricao, hist_trad, raw_saida in (await db.execute(stmt_pagto)).all():
        v_abs = abs(Decimal(raw_saida or 0))
        if v_abs == ZERO:
            continue
        kw_pagto = _extract_keyword(descricao) or _extract_keyword(hist_trad)
        if kw_pagto is None:
            # Saida nao casa com nenhuma despesa conhecida — pula (provavelmente
            # eh aplicacao/compra/resgate de portfolio, nao pagamento de despesa).
            continue
        item = VariacaoItem(
            cosif     = None,
            label     = (hist_trad or descricao or "(sem descrição)").strip(),
            historico = hist_trad,
            descricao = descricao,
            valor     = v_abs,
        )
        # Cruzamento: pagamento tem provisao previa?
        if kw_pagto in cpr_seen_keywords:
            pagamentos.append(item)
            pagamentos_total += v_abs
        else:
            anomalias.append(item)

    pagamentos.sort(key=lambda i: float(i.valor), reverse=True)
    anomalias.sort(key=lambda i: float(i.valor), reverse=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. CONFERENCIA — sanity check do regime de competencia.
    #
    # Regra: o ΔPassivo Contabil de D-1 → D0 deve ser explicavel pelas
    # apropriacoes do dia. Pagamentos efetivados em D0 podem ter baixado o
    # CPR em datas ANTERIORES (ciclo mensal nao zera no dia do pagamento,
    # zera quando a contabilidade reconhece a baixa) — entao na pratica:
    #
    #   ΔPassivo > Σ apropriacoes  ⇒ algo entrou no Passivo SEM apropriacao
    #                                    correspondente (ANOMALIA)
    #   ΔPassivo ≤ Σ apropriacoes  ⇒ apropriacoes cobrem o crescimento do
    #                                    passivo (diferenca = baixas que
    #                                    aconteceram em algum momento do mes)
    #
    # divergencia = max(0, ΔPassivo - Σ apropriacoes_passivo)
    # ok = divergencia ~ 0
    # ─────────────────────────────────────────────────────────────────────────
    delta_passivo_contabil = ZERO
    for hist_key, vals in cpr_by_hist.items():
        cosif = cpr_metadata[hist_key]["cosif"]
        if CPR_COSIF_META.get(cosif, ("", "A"))[1] != "P":
            continue
        delta_passivo_contabil += (vals.get(data_d0, ZERO) or ZERO) - (vals.get(d_d1, ZERO) or ZERO)

    # Soma apropriacoes apenas das que sao Passivo (Ativo nao impacta Passivo)
    soma_apropriacoes_passivo = Decimal(sum(
        (i.valor for i in apropriacoes if i.cosif and CPR_COSIF_META.get(i.cosif, ("", "A"))[1] == "P"),
        start=ZERO,
    ))

    excedente = delta_passivo_contabil - soma_apropriacoes_passivo
    divergencia = excedente if excedente > Decimal("0.01") else ZERO
    ok = divergencia < Decimal("0.01")

    return VariacoesDiaResponse(
        fundo_id          = str(ua_id),
        data              = data_d0,
        data_anterior     = d_d1,
        apropriacoes      = apropriacoes,
        apropriacoes_total= apropriacoes_total,
        pagamentos        = pagamentos,
        pagamentos_total  = pagamentos_total,
        anomalias         = anomalias,
        conferencia       = ConferenciaVariacao(
            delta_passivo_contabil = delta_passivo_contabil,
            soma_apropriacoes      = soma_apropriacoes_passivo,
            divergencia            = divergencia,
            ok                     = ok,
        ),
    )
