"""Controladoria · Cota Sub · drill DC (F2 do redesign, 2026-05-23 → 2026-05-24).

Decompoe a categoria DC (Direitos Creditorios) do Balance hero em:

  1. **Decomposicao do ΔDC (F2 redesign 2026-05-24)** — 5 buckets calculados
     diretamente pelo granular `wh_estoque_recebivel`:
         saldo_d0 = saldo_d1
                  + aquisicoes (papeis em D0 \\ D-1)
                  - liquidacoes (papeis em D-1 \\ D0, pelo VP_d1)
                  - migracao_wop (papeis que viraram WOP, pelo VP_d1)
                  + apropriacao (Σ ΔVP da populacao constante sem mudanca de parametro)
                  + mutacao (Σ ΔVP da populacao constante COM mudanca de parametro)
                  + residuo (deve ser ~0)
     Identidade contabil fecha por construcao — mutacao silenciosa (F5)
     vira resultado natural, sem necessidade de varredura paralela.

  2. Aquisicoes do dia      — linhas de `wh_aquisicao_recebivel` em D0
                              (cross-check com o bucket Aquisicoes acima)
  3. Liquidacoes por tipo   — `wh_liquidacao_recebivel` em D0, agrupado por
                              `tipo_movimento` (LIQUIDAÇÃO NORMAL, BAIXA,
                              RECOMPRA, etc.)
  4. Apropriacao derivada (LEGACY) — formula residual antiga:
                              apropriacao = ΔEstoque + Liquidacoes - Aquisicoes
                              Mantida na response para compat com UI antiga.
                              ΔEstoque agora vem do granular ex-WOP (via _sum_dc
                              refatorado em F1, 2026-05-24).

Decisao 2026-05-24: o `_sum_dc` voltou a ler granular ex-WOP (Fase 1A).
O drill DC agora reconcilia naturalmente — o saldo do balanco e o saldo
do drill sao calculados da mesma fonte.

Liquidacoes saem do estoque ao `valor_aquisicao` (custo no FIDC). O
`ganho_liquido` (valor_pago - valor_aquisicao - ajuste) NAO entra na
apropriacao — vai pra Tesouraria como caixa recebido alem do custo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub_drill import (
    DrillDcAbatimentoPapel,
    DrillDcApropriacao,
    DrillDcAquisicao,
    DrillDcDecomposicao,
    DrillDcLiquidacaoLinha,
    DrillDcLiquidacaoParcialPapel,
    DrillDcLiquidacaoPorTipo,
    DrillDcMigracaoWopPapel,
    DrillDcMutacaoPapel,
    DrillDcResponse,
    DrillDcResultadoDoDia,
)
from app.modules.controladoria.services.cota_sub import _sum_dc
from app.modules.controladoria.services.liquidacao_natureza import (
    classify_liquidacao_nature,
)
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel

ZERO = Decimal("0")

# Top N liquidacoes individuais retornadas (ordenadas por |valor_pago| DESC).
# 30 cobre dia tipico em REALINVEST (~10-20 liquidacoes); UI corta visual.
_TOP_LIQUIDACOES_N = 30

# Top N papeis de mutacao silenciosa retornados. Dia tipico = 0 papeis;
# quando o caso DID99746 acontece, sao 1-5 papeis com salto material.
_TOP_MUTACAO_N = 30

# Limite minimo |delta_vp| pra entrar em mutacao (filtra ruido de
# arredondamento da QiTech — diferencas menores que centavos).
_MUTACAO_MIN_DELTA_BRL = Decimal("0.01")

# Tolerancia pra casar a queda de valor_nominal do estoque com a soma de
# valor_pago dos eventos de liquidacao do dia (mesma business key). Quando
# `|ΔVN + Σvalor_pago| <= tol`, a queda do papel e uma LIQUIDACAO PARCIAL
# (papel ficou, parcela paga) — nao mutacao silenciosa. R$ 1 alinha com o
# residuo aceitavel da decomposicao.
_LIQ_PARCIAL_MATCH_TOL_BRL = Decimal("1.0")


async def _aquisicoes_do_dia(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    fundo_doc: str,
    data: date,
) -> tuple[list[DrillDcAquisicao], int, Decimal]:
    """Aquisicoes (linha do `wh_aquisicao_recebivel` com data_aquisicao = D0).

    Filtra por `unidade_administrativa_id` quando presente; cai pra `fundo_doc`
    em linhas legacy (pre Phase F multi-UA). Mesmo padrao do
    `cota_sub_explainers._movimento_carteira_evidencias`.
    """
    stmt = (
        select(AquisicaoRecebivel)
        .where(AquisicaoRecebivel.tenant_id == tenant_id)
        .where(AquisicaoRecebivel.data_aquisicao == data)
        .where(
            (AquisicaoRecebivel.unidade_administrativa_id == ua_id)
            | (
                (AquisicaoRecebivel.unidade_administrativa_id.is_(None))
                & (AquisicaoRecebivel.fundo_doc == fundo_doc)
            )
        )
        .order_by(AquisicaoRecebivel.valor_compra.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    aquisicoes = [
        DrillDcAquisicao(
            cedente_doc=row.cedente_doc,
            cedente_nome=row.cedente_nome,
            sacado_doc=row.sacado_doc,
            sacado_nome=row.sacado_nome,
            seu_numero=row.seu_numero,
            numero_documento=row.numero_documento,
            tipo_recebivel=row.tipo_recebivel,
            data_vencimento=row.data_vencimento,
            valor_compra=row.valor_compra,
            valor_vencimento=row.valor_vencimento,
            taxa_aquisicao=row.taxa_aquisicao,
            prazo_recebivel=row.prazo_recebivel,
        )
        for row in rows
    ]
    total = sum((a.valor_compra for a in aquisicoes), ZERO)
    return aquisicoes, len(aquisicoes), total


async def _liquidacoes_do_dia(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    fundo_doc: str,
    data: date,
) -> tuple[
    list[DrillDcLiquidacaoPorTipo], list[DrillDcLiquidacaoLinha], int,
    Decimal, Decimal, Decimal,
]:
    """Liquidacoes do dia + agrupamento por `tipo_movimento` + top N individuais.

    Retorna (por_tipo, top_individuais, qtd_total, total_valor_aquisicao,
    apropriacao_antecipada, juros_mora, desconto_concedido).

    Convencao de sinal (ajuste): `ajuste<0` AUMENTA o ativo (renda, bom pra
    nos); `ajuste>0` e perda/abatimento. O `ajuste<0` e desmembrado por TIMING
    do pagamento (data_posicao vs data_vencimento), porque sao naturezas
    DIFERENTES:

    - `apropriacao_antecipada` = -Σ(ajuste<0 com data_posicao <= vencimento):
      titulo quitado ANTES do vencimento. NAO e receita extra — e o carrego
      futuro (juros ja contratado na curva) apropriado de uma vez. Mesma
      natureza do carrego diario, so realizado antes. Sempre >= 0.
    - `juros_mora` = -Σ(ajuste<0 com data_posicao > vencimento, ou venc nulo):
      sacado pagou em ATRASO. Renda EXTRA (penalidade). Sempre >= 0.
    - `desconto_concedido` = Σ(ajuste>0): abatimento/perda. Magnitude >= 0.

    Split feito em SQL (case por linha), entao tipos com ajuste misto contam
    corretamente. `total_valor_aquisicao` = custo que sai do estoque.
    """
    base = (
        select(LiquidacaoRecebivel)
        .where(LiquidacaoRecebivel.tenant_id == tenant_id)
        .where(LiquidacaoRecebivel.data_posicao == data)
        .where(
            (LiquidacaoRecebivel.unidade_administrativa_id == ua_id)
            | (
                (LiquidacaoRecebivel.unidade_administrativa_id.is_(None))
                & (LiquidacaoRecebivel.fundo_doc == fundo_doc)
            )
        )
    )

    # Aggregate por tipo_movimento numa unica passada.
    agg_stmt = (
        select(
            LiquidacaoRecebivel.tipo_movimento,
            func.count().label("qtd"),
            func.coalesce(func.sum(LiquidacaoRecebivel.valor_pago), ZERO).label("sum_pago"),
            func.coalesce(func.sum(LiquidacaoRecebivel.valor_aquisicao), ZERO).label("sum_aq"),
            func.coalesce(func.sum(LiquidacaoRecebivel.valor_vencimento), ZERO).label("sum_venc"),
            func.coalesce(func.sum(LiquidacaoRecebivel.ajuste), ZERO).label("sum_aj"),
            # ajuste<0 quitado ANTES do vencimento -> apropriacao antecipada.
            func.coalesce(
                func.sum(case(
                    (
                        and_(
                            LiquidacaoRecebivel.ajuste < 0,
                            LiquidacaoRecebivel.data_vencimento.isnot(None),
                            LiquidacaoRecebivel.data_posicao <= LiquidacaoRecebivel.data_vencimento,
                        ),
                        LiquidacaoRecebivel.ajuste,
                    ),
                    else_=ZERO,
                )),
                ZERO,
            ).label("sum_aj_antecip"),
            # ajuste<0 pago em ATRASO (ou venc nulo) -> juros de mora.
            func.coalesce(
                func.sum(case(
                    (
                        and_(
                            LiquidacaoRecebivel.ajuste < 0,
                            or_(
                                LiquidacaoRecebivel.data_vencimento.is_(None),
                                LiquidacaoRecebivel.data_posicao > LiquidacaoRecebivel.data_vencimento,
                            ),
                        ),
                        LiquidacaoRecebivel.ajuste,
                    ),
                    else_=ZERO,
                )),
                ZERO,
            ).label("sum_aj_mora"),
            func.coalesce(
                func.sum(case((LiquidacaoRecebivel.ajuste > 0, LiquidacaoRecebivel.ajuste), else_=ZERO)),
                ZERO,
            ).label("sum_aj_pos"),
        )
        .where(LiquidacaoRecebivel.tenant_id == tenant_id)
        .where(LiquidacaoRecebivel.data_posicao == data)
        .where(
            (LiquidacaoRecebivel.unidade_administrativa_id == ua_id)
            | (
                (LiquidacaoRecebivel.unidade_administrativa_id.is_(None))
                & (LiquidacaoRecebivel.fundo_doc == fundo_doc)
            )
        )
        .group_by(LiquidacaoRecebivel.tipo_movimento)
        .order_by(func.sum(LiquidacaoRecebivel.valor_pago).desc())
    )
    agg_rows = (await db.execute(agg_stmt)).all()

    por_tipo: list[DrillDcLiquidacaoPorTipo] = []
    qtd_total = 0
    sum_aquisicao_total = ZERO
    apropriacao_antecipada = ZERO  # -Σ(ajuste<0, antes do venc): carrego antecipado
    juros_mora = ZERO              # -Σ(ajuste<0, em atraso): renda extra de mora
    desconto_concedido = ZERO      # Σ(ajuste>0): abatimento/perda
    for (
        tipo, qtd, sum_pago, sum_aq, sum_venc, sum_aj,
        sum_aj_antecip, sum_aj_mora, sum_aj_pos,
    ) in agg_rows:
        sum_pago_d = Decimal(sum_pago or 0)
        sum_aq_d = Decimal(sum_aq or 0)
        sum_aj_d = Decimal(sum_aj or 0)
        qtd_total += int(qtd or 0)
        sum_aquisicao_total += sum_aq_d
        apropriacao_antecipada += -Decimal(sum_aj_antecip or 0)  # ajuste<0 antes venc
        juros_mora += -Decimal(sum_aj_mora or 0)                 # ajuste<0 em atraso
        desconto_concedido += Decimal(sum_aj_pos or 0)           # ajuste>0 -> custo
        por_tipo.append(
            DrillDcLiquidacaoPorTipo(
                tipo_movimento=tipo or "—",
                qtd_papeis=int(qtd or 0),
                sum_valor_pago=sum_pago_d,
                sum_valor_aquisicao=sum_aq_d,
                sum_valor_vencimento=Decimal(sum_venc or 0),
                sum_ajuste=sum_aj_d,
                impacto_resultado_brl=-sum_aj_d,  # sinal de impacto ja corrigido
                ganho_liquido=sum_pago_d - sum_aq_d - sum_aj_d,
            )
        )

    # Top N individuais por valor_pago.
    top_stmt = base.order_by(LiquidacaoRecebivel.valor_pago.desc()).limit(_TOP_LIQUIDACOES_N)
    top_rows = (await db.execute(top_stmt)).scalars().all()

    top_individuais = [
        DrillDcLiquidacaoLinha(
            cedente_doc=r.cedente_doc,
            cedente_nome=r.cedente_nome,
            sacado_doc=r.sacado_doc,
            sacado_nome=r.sacado_nome,
            seu_numero=r.seu_numero,
            documento=r.documento,
            tipo_recebivel=r.tipo_recebivel,
            tipo_movimento=r.tipo_movimento,
            valor_pago=r.valor_pago,
            valor_aquisicao=r.valor_aquisicao,
            valor_vencimento=r.valor_vencimento,
            ajuste=r.ajuste,
            impacto_resultado_brl=-r.ajuste,  # sinal de impacto ja corrigido
            ganho_liquido=r.valor_pago - r.valor_aquisicao - r.ajuste,
        )
        for r in top_rows
    ]

    return (
        por_tipo, top_individuais, qtd_total, sum_aquisicao_total,
        apropriacao_antecipada, juros_mora, desconto_concedido,
    )


async def _decompor_delta_dc(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    fundo_doc: str,
    data_d1: date,
    data_d0: date,
    aquisicoes_evento_total: Decimal,
    liquidacoes_evento_total: Decimal,
) -> tuple[
    DrillDcDecomposicao,
    list[DrillDcMutacaoPapel],
    list[DrillDcLiquidacaoParcialPapel],
    list[DrillDcAbatimentoPapel],
    list[DrillDcMigracaoWopPapel],
]:
    """Decomposicao do ΔDC em 5 buckets a partir do granular `wh_estoque_recebivel`.

    Carrega TODOS os papeis das duas datas em memoria, classifica via
    business key `(cedente_doc, seu_numero, numero_documento)`, calcula os
    5 conjuntos:

      A = papeis em D0 \\ D-1                                 -> Aquisicoes
      L = papeis em D-1 \\ D0                                 -> Liquidacoes
      W = papeis em D-1 ∩ D0, WOP em D0 e nao-WOP em D-1     -> Migracao WOP
      C = papeis em D-1 ∩ D0, nao-WOP nos 2, params iguais    -> Apropriacao
      M = papeis em D-1 ∩ D0, nao-WOP nos 2, params != em ao
          menos 1 (valor_nominal / taxa_recebivel / data_venc)  -> Mutacao

    Parametros comparados para identificar mutacao silenciosa:
      - valor_nominal (caso canonico DID99746)
      - taxa_recebivel
      - data_vencimento_ajustada

    Performance: 2 queries (uma por dia). ~3000 papeis tipicos por dia em
    REALINVEST. Classificacao Python eh O(N), trivial.

    Cross-check evento (informativo, nao usado no calculo):
      diff_aq = bucket_aquisicoes - Σ wh_aquisicao_recebivel.valor_compra do dia
      diff_li = bucket_liquidacoes - Σ wh_liquidacao_recebivel.valor_aquisicao
    Esperado ~0; quando diverge, sinaliza desalinhamento snapshot vs evento.
    """
    # Carrega snapshot D-1 e D0 do granular (todos os campos necessarios pra
    # classificar + calcular delta + detectar mutacao).
    def _snapshot_stmt(data: date):
        return (
            select(
                EstoqueRecebivel.cedente_doc,
                EstoqueRecebivel.cedente_nome,
                EstoqueRecebivel.sacado_doc,
                EstoqueRecebivel.sacado_nome,
                EstoqueRecebivel.seu_numero,
                EstoqueRecebivel.numero_documento,
                EstoqueRecebivel.tipo_recebivel,
                EstoqueRecebivel.valor_presente,
                EstoqueRecebivel.valor_nominal,
                EstoqueRecebivel.valor_aquisicao,
                EstoqueRecebivel.valor_pdd,
                EstoqueRecebivel.taxa_recebivel,
                EstoqueRecebivel.data_vencimento_ajustada,
                EstoqueRecebivel.faixa_pdd,
            )
            .where(EstoqueRecebivel.tenant_id == tenant_id)
            .where(EstoqueRecebivel.fundo_doc == fundo_doc)
            .where(EstoqueRecebivel.data_referencia == data)
        )

    rows_d1 = (await db.execute(_snapshot_stmt(data_d1))).all()
    rows_d0 = (await db.execute(_snapshot_stmt(data_d0))).all()

    # Indexa por business key. UQ em wh_estoque_recebivel garante 1 papel
    # por (tenant, data_ref, fundo, cedente, seu_numero, numero_doc).
    d1_map = {(r.cedente_doc, r.seu_numero, r.numero_documento): r for r in rows_d1}
    d0_map = {(r.cedente_doc, r.seu_numero, r.numero_documento): r for r in rows_d0}

    keys_d1 = set(d1_map.keys())
    keys_d0 = set(d0_map.keys())

    # Saldos totais ex-WOP (alinhados com `_sum_dc` refatorado em F1).
    saldo_d1 = sum(
        (Decimal(r.valor_presente) for r in rows_d1 if r.faixa_pdd != "WOP"),
        ZERO,
    )
    saldo_d0 = sum(
        (Decimal(r.valor_presente) for r in rows_d0 if r.faixa_pdd != "WOP"),
        ZERO,
    )

    # ── Bucket A: Aquisicoes (D0 \ D-1) ─────────────────────────────────────
    # Sai do WOP do dia D0 — papel WOP nao entra como aquisicao (nao faz
    # sentido aparecer "comprando" um papel ja em write-off; mas defendemos
    # a edge no filtro pra ser consistente com a definicao de saldo ex-WOP).
    aquisicoes_keys = keys_d0 - keys_d1
    aquisicoes_n = 0
    aquisicoes_total = ZERO
    for k in aquisicoes_keys:
        r = d0_map[k]
        if r.faixa_pdd == "WOP":
            continue
        aquisicoes_n += 1
        aquisicoes_total += Decimal(r.valor_presente)

    # ── Bucket L: Liquidacoes (D-1 \ D0) ────────────────────────────────────
    # Mesma logica: descartamos papeis que ja estavam em WOP em D-1 (nao
    # contam como "liquidacao do estoque ex-WOP", saem por outro canal).
    liquidacoes_keys = keys_d1 - keys_d0
    liquidacoes_n = 0
    liquidacoes_total = ZERO
    for k in liquidacoes_keys:
        r = d1_map[k]
        if r.faixa_pdd == "WOP":
            continue
        liquidacoes_n += 1
        liquidacoes_total += Decimal(r.valor_presente)

    # ── Bucket W: Migracao WOP (D-1 ∩ D0, WOP em D0 e nao-WOP em D-1) ──────
    intersecao = keys_d1 & keys_d0
    migracao_wop_n = 0
    migracao_wop_total = ZERO
    migracao_wop_papeis: list[DrillDcMigracaoWopPapel] = []
    for k in intersecao:
        r1, r0 = d1_map[k], d0_map[k]
        if r0.faixa_pdd == "WOP" and r1.faixa_pdd != "WOP":
            migracao_wop_n += 1
            migracao_wop_total += Decimal(r1.valor_presente)
            migracao_wop_papeis.append(
                DrillDcMigracaoWopPapel(
                    cedente_doc=r1.cedente_doc,
                    cedente_nome=r1.cedente_nome,
                    sacado_doc=r1.sacado_doc,
                    sacado_nome=r1.sacado_nome,
                    seu_numero=r1.seu_numero,
                    numero_documento=r1.numero_documento,
                    tipo_recebivel=r1.tipo_recebivel,
                    data_vencimento=r1.data_vencimento_ajustada,
                    faixa_pdd_d1=r1.faixa_pdd,
                    vp_d1=Decimal(r1.valor_presente),
                    valor_pdd_d1=Decimal(r1.valor_pdd),
                )
            )

    # ── Eventos de liquidacao do D0 por business key ───────────────────────
    # Pra reconciliar papel que FICOU (mutacao aparente) com liquidacao PARCIAL
    # real: a queda de valor_nominal casa com a soma de valor_pago do(s)
    # evento(s). Estoque usa `numero_documento`; liquidacao usa `documento` —
    # mesmo valor, mesma business key (cedente_doc, seu_numero, doc).
    liq_stmt = (
        select(
            LiquidacaoRecebivel.cedente_doc,
            LiquidacaoRecebivel.seu_numero,
            LiquidacaoRecebivel.documento,
            func.coalesce(func.sum(LiquidacaoRecebivel.valor_pago), ZERO).label("sum_pago"),
            func.min(LiquidacaoRecebivel.tipo_movimento).label("tipo"),
        )
        .where(LiquidacaoRecebivel.tenant_id == tenant_id)
        .where(LiquidacaoRecebivel.data_posicao == data_d0)
        .where(
            (LiquidacaoRecebivel.unidade_administrativa_id == ua_id)
            | (
                (LiquidacaoRecebivel.unidade_administrativa_id.is_(None))
                & (LiquidacaoRecebivel.fundo_doc == fundo_doc)
            )
        )
        .group_by(
            LiquidacaoRecebivel.cedente_doc,
            LiquidacaoRecebivel.seu_numero,
            LiquidacaoRecebivel.documento,
        )
    )
    liq_eventos: dict[tuple[str, str, str], tuple[Decimal, str]] = {
        (r.cedente_doc, r.seu_numero, r.documento): (Decimal(r.sum_pago or 0), r.tipo or "—")
        for r in (await db.execute(liq_stmt)).all()
    }

    # ── Buckets C/M/LP: populacao constante nao-WOP ─────────────────────────
    apropriacao_n = 0
    apropriacao_total = ZERO
    mutacao_n = 0
    mutacao_total = ZERO
    liq_parcial_n = 0
    liq_parcial_total = ZERO
    abatimentos_n = 0
    abatimentos_total = ZERO
    mutacao_papeis_all: list[DrillDcMutacaoPapel] = []
    liq_parcial_papeis_all: list[DrillDcLiquidacaoParcialPapel] = []
    abatimentos_papeis_all: list[DrillDcAbatimentoPapel] = []
    for k in intersecao:
        r1, r0 = d1_map[k], d0_map[k]
        # Pula migracao WOP (ja contada no bucket W).
        if r1.faixa_pdd != "WOP" and r0.faixa_pdd == "WOP":
            continue
        # Pula casos exoticos: WOP em D-1 e nao-WOP em D0 (saida de WOP).
        # Raro/inexistente no REALINVEST; tratamos como ruido.
        if r1.faixa_pdd == "WOP" or r0.faixa_pdd == "WOP":
            continue

        delta_vp = Decimal(r0.valor_presente) - Decimal(r1.valor_presente)
        vn_d1 = Decimal(r1.valor_nominal)
        vn_d0 = Decimal(r0.valor_nominal)

        mudou_vn = vn_d1 != vn_d0
        mudou_taxa = Decimal(r1.taxa_recebivel) != Decimal(r0.taxa_recebivel)
        mudou_venc = r1.data_vencimento_ajustada != r0.data_vencimento_ajustada

        # Sem mudanca de parametro -> apropriacao (carrego).
        if not (mudou_vn or mudou_taxa or mudou_venc):
            apropriacao_n += 1
            apropriacao_total += delta_vp
            continue

        # Mudou parametro. Antes de chamar de "mutacao silenciosa", tenta casar
        # com evento de liquidacao parcial do dia: papel ficou + parcela paga.
        # Criterio (recomendacao b): ΔVN ≈ -Σvalor_pago dentro da tolerancia.
        evento = liq_eventos.get(k)
        if evento is not None and abs((vn_d0 - vn_d1) + evento[0]) <= _LIQ_PARCIAL_MATCH_TOL_BRL:
            sum_pago, tipo_mov = evento
            registra_detalhe = abs(delta_vp) >= _MUTACAO_MIN_DELTA_BRL
            # NATUREZA do evento casado decide o balde (liquidacao_natureza.py):
            #   credit_loss   -> ABATIMENTO CONCEDIDO: perda perdoada SEM caixa.
            #                    Value-mover do DC (entra no impacto da cota).
            #   cash_settlement -> recompra/liquidacao parcial: a perna de caixa
            #                    compensa. GIRO carteira->caixa (fora do impacto).
            if classify_liquidacao_nature(tipo_mov) == "credit_loss":
                abatimentos_n += 1
                abatimentos_total += delta_vp
                if registra_detalhe:
                    val_aq = Decimal(r0.valor_aquisicao)
                    abatimentos_papeis_all.append(
                        DrillDcAbatimentoPapel(
                            cedente_doc=r1.cedente_doc,
                            cedente_nome=r1.cedente_nome,
                            sacado_doc=r1.sacado_doc,
                            sacado_nome=r1.sacado_nome,
                            seu_numero=r1.seu_numero,
                            numero_documento=r1.numero_documento,
                            tipo_recebivel=r1.tipo_recebivel,
                            data_vencimento=r0.data_vencimento_ajustada,
                            tipo_movimento=tipo_mov,
                            vp_d1=Decimal(r1.valor_presente),
                            vp_d0=Decimal(r0.valor_presente),
                            delta_vp=delta_vp,
                            vn_d1=vn_d1,
                            vn_d0=vn_d0,
                            nominal_abatido=abs(vn_d0 - vn_d1),
                            valor_aquisicao=val_aq,
                            abaixo_do_custo=Decimal(r0.valor_presente) < val_aq,
                        )
                    )
            else:
                liq_parcial_n += 1
                liq_parcial_total += delta_vp
                if registra_detalhe:
                    liq_parcial_papeis_all.append(
                        DrillDcLiquidacaoParcialPapel(
                            cedente_doc=r1.cedente_doc,
                            cedente_nome=r1.cedente_nome,
                            sacado_doc=r1.sacado_doc,
                            sacado_nome=r1.sacado_nome,
                            seu_numero=r1.seu_numero,
                            numero_documento=r1.numero_documento,
                            tipo_recebivel=r1.tipo_recebivel,
                            data_vencimento=r0.data_vencimento_ajustada,
                            vp_d1=Decimal(r1.valor_presente),
                            vp_d0=Decimal(r0.valor_presente),
                            delta_vp=delta_vp,
                            vn_d1=vn_d1,
                            vn_d0=vn_d0,
                            tipo_movimento=tipo_mov,
                            valor_pago_evento=sum_pago,
                            reconcilia=True,
                        )
                    )
            continue

        # Sem evento casado -> mutacao silenciosa RESIDUAL (re-statement genuino).
        mutacao_n += 1
        mutacao_total += delta_vp
        # So registra na lista de detalhe se delta passar o threshold
        # (filtra arredondamentos de centavos).
        if abs(delta_vp) >= _MUTACAO_MIN_DELTA_BRL:
            mutacao_papeis_all.append(
                DrillDcMutacaoPapel(
                    cedente_doc=r1.cedente_doc,
                    cedente_nome=r1.cedente_nome,
                    sacado_doc=r1.sacado_doc,
                    sacado_nome=r1.sacado_nome,
                    seu_numero=r1.seu_numero,
                    numero_documento=r1.numero_documento,
                    tipo_recebivel=r1.tipo_recebivel,
                    vp_d1=Decimal(r1.valor_presente),
                    vp_d0=Decimal(r0.valor_presente),
                    delta_vp=delta_vp,
                    vn_d1=vn_d1,
                    vn_d0=vn_d0,
                    taxa_d1=Decimal(r1.taxa_recebivel),
                    taxa_d0=Decimal(r0.taxa_recebivel),
                    venc_d1=r1.data_vencimento_ajustada,
                    venc_d0=r0.data_vencimento_ajustada,
                    mudou_vn=mudou_vn,
                    mudou_taxa=mudou_taxa,
                    mudou_venc=mudou_venc,
                )
            )

    # Top N mutacoes por |delta_vp| (UI corta — backend devolve mais pra
    # debug futuro nao quebrar).
    mutacao_papeis_all.sort(key=lambda p: abs(p.delta_vp), reverse=True)
    mutacao_papeis_top = mutacao_papeis_all[:_TOP_MUTACAO_N]
    liq_parcial_papeis_all.sort(key=lambda p: abs(p.delta_vp), reverse=True)
    liq_parcial_papeis_top = liq_parcial_papeis_all[:_TOP_MUTACAO_N]
    abatimentos_papeis_all.sort(key=lambda p: abs(p.delta_vp), reverse=True)
    abatimentos_papeis_top = abatimentos_papeis_all[:_TOP_MUTACAO_N]

    # Identidade: saldo_d0 - (saldo_d1 + A - L - W + C + LP + AB + M) = residuo
    # LP (liq. parcial caixa), AB (abatimento) e M (mutacao) sao todos ΔVP de
    # papeis que ficaram — so o rotulo/destino difere. Somam igual na identidade,
    # entao mover ABATIMENTO de LP pra AB NAO altera o residuo.
    delta_saldo = saldo_d0 - saldo_d1
    explicado = (
        aquisicoes_total - liquidacoes_total - migracao_wop_total
        + apropriacao_total + liq_parcial_total + abatimentos_total + mutacao_total
    )
    residuo = delta_saldo - explicado

    # Cross-check com eventos publicados.
    diff_aq = aquisicoes_total - aquisicoes_evento_total
    diff_li = liquidacoes_total - liquidacoes_evento_total

    decomposicao = DrillDcDecomposicao(
        saldo_d1=saldo_d1,
        saldo_d0=saldo_d0,
        delta_saldo=delta_saldo,
        aquisicoes_n=aquisicoes_n,
        aquisicoes_total=aquisicoes_total,
        liquidacoes_n=liquidacoes_n,
        liquidacoes_total=liquidacoes_total,
        migracao_wop_n=migracao_wop_n,
        migracao_wop_total=migracao_wop_total,
        apropriacao_n=apropriacao_n,
        apropriacao_total=apropriacao_total,
        liquidacao_parcial_n=liq_parcial_n,
        liquidacao_parcial_total=liq_parcial_total,
        abatimentos_n=abatimentos_n,
        abatimentos_total=abatimentos_total,
        mutacao_n=mutacao_n,
        mutacao_total=mutacao_total,
        residuo=residuo,
        cross_check_aquisicoes_evento=aquisicoes_evento_total,
        cross_check_liquidacoes_evento=liquidacoes_evento_total,
        cross_check_diff_aquisicoes=diff_aq,
        cross_check_diff_liquidacoes=diff_li,
    )

    return (
        decomposicao,
        mutacao_papeis_top,
        liq_parcial_papeis_top,
        abatimentos_papeis_top,
        migracao_wop_papeis,
    )


def _build_resultado_do_dia(
    *,
    decomposicao: DrillDcDecomposicao,
    apropriacao_antecipada: Decimal,
    juros_mora: Decimal,
    desconto_concedido: Decimal,
) -> DrillDcResultadoDoDia:
    """Consolida os motores de renda da DC com sinal de IMPACTO no PL Sub.

    Move pra dentro da tool a "regra dura de sinal" que o prompt do agente
    carregava: ajuste<0 e renda (aumenta o ativo), ajuste>0 e custo — o agente
    nao precisa flipar o `ajuste` de cabeca (fonte do erro de ~3x ao confundir
    com `ganho_liquido`).

    Distincao chave (2026-05-30): o `ajuste<0` separa-se em
    `apropriacao_antecipada` (quitacao antes do vencimento = carrego futuro JA
    CONTRATADO, so trazido pra frente — NAO e receita extra) e `juros_mora`
    (atraso = renda extra). Por isso a apropriacao antecipada entra JUNTO do
    carrego na dominancia/outlier: um dia de muitas quitacoes antecipadas e
    rotina de apropriacao, nao um evento atipico.

    `motor_dominante` e `resultado_outlier` sao descritores de DOMINIO (nao
    enums do agente) — a tool wrapper deriva deles a `classificacao_sugerida`.
    """
    carrego = decomposicao.apropriacao_total
    # Apropriacao contratada do dia = carrego diario + carrego antecipado por
    # quitacao (mesma natureza: juros ja na curva). E a "rotina" do dia.
    apropriacao_contratada = carrego + apropriacao_antecipada
    # Eventos NAO-contratados das liquidacoes (o que realmente foge da rotina).
    evento_liquido = juros_mora - desconto_concedido
    ajuste_liquido = apropriacao_antecipada + juros_mora - desconto_concedido  # = -Σajuste
    mutacao = decomposicao.mutacao_total
    abatimentos = decomposicao.abatimentos_total
    wop = decomposicao.migracao_wop_total

    # Motor dominante: maior magnitude. Apropriacao antecipada conta no carrego.
    candidatos: dict[str, Decimal] = {
        "carrego": abs(apropriacao_contratada),
        "mora": abs(juros_mora),
        "desconto": abs(desconto_concedido),
        "abatimento": abs(abatimentos),
        "mutacao": abs(mutacao),
        "write_off": abs(wop),
    }
    top = max(candidatos, key=lambda k: candidatos[k])
    top_val = candidatos[top]
    # "misto" quando o 2o motor chega a >= 70% do dominante (nenhum domina claro).
    segundo = sorted(candidatos.values(), reverse=True)[1] if len(candidatos) > 1 else ZERO
    motor_dominante = "misto" if top_val > ZERO and segundo >= top_val * Decimal("0.7") else top

    # Outlier: a apropriacao contratada (carrego + antecipada) deixou de dominar
    # — um evento (mora/desconto), abatimento OU mutacao supera a rotina do dia.
    resultado_outlier = (
        abs(evento_liquido) > abs(apropriacao_contratada)
        or abs(abatimentos) > abs(apropriacao_contratada)
        or abs(mutacao) > abs(apropriacao_contratada)
    )

    return DrillDcResultadoDoDia(
        carrego_apropriacao=carrego,
        apropriacao_antecipada=apropriacao_antecipada,
        apropriacao_total_dia=apropriacao_contratada,
        juros_mora=juros_mora,
        desconto_concedido=desconto_concedido,
        ajuste_liquido_resultado=ajuste_liquido,
        mutacao_total=mutacao,
        abatimentos_total=abatimentos,
        migracao_wop_total=wop,
        giro_aquisicoes=decomposicao.aquisicoes_total,
        giro_liquidacoes=decomposicao.liquidacoes_total,
        giro_liquidacao_parcial=decomposicao.liquidacao_parcial_total,
        motor_dominante=motor_dominante,  # type: ignore[arg-type]
        resultado_outlier=resultado_outlier,
    )


async def compute_drill_dc(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> DrillDcResponse:
    """Drill DC: aquisicoes + liquidacoes por tipo + decomposicao do ΔDC.

    F2 redesign 2026-05-24: passa a calcular a `decomposicao` em 5 buckets
    a partir do granular (ver `_decompor_delta_dc`). A `apropriacao` antiga
    (formula residual) e mantida no payload pra retrocompat com a UI atual
    ate a Fase 3 entregar a nova UI.

    Args:
        tenant_id: escopo multi-tenant.
        ua_id: UUID da UA (FIDC).
        data_d0: dia analisado.
        data_d1: override opcional de D-1.

    Raises:
        ValueError: quando a UA nao existe.
    """
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

    # Estoque consolidado — agora granular ex-WOP (F1, 2026-05-24).
    estoque_d1 = await _sum_dc(db, tenant_id, ua_id, ua.nome, d1)
    estoque_d0 = await _sum_dc(db, tenant_id, ua_id, ua.nome, data_d0)

    aquisicoes, aquisicoes_qtd, aquisicoes_total = await _aquisicoes_do_dia(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        fundo_doc=ua.cnpj or "",
        data=data_d0,
    )

    (
        por_tipo, top_liq, liquidacoes_qtd, liquidacoes_total,
        apropriacao_antecipada, juros_mora, desconto_concedido,
    ) = await _liquidacoes_do_dia(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        fundo_doc=ua.cnpj or "",
        data=data_d0,
    )

    delta_estoque = estoque_d0 - estoque_d1
    apropriacao_val = delta_estoque + liquidacoes_total - aquisicoes_total

    # F2 redesign: decomposicao em buckets via granular.
    (
        decomposicao, mutacao_papeis, liquidacao_parcial_papeis,
        abatimentos_papeis, migracao_wop_papeis,
    ) = await _decompor_delta_dc(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        fundo_doc=ua.cnpj or "",
        data_d1=d1,
        data_d0=data_d0,
        aquisicoes_evento_total=aquisicoes_total,
        liquidacoes_evento_total=liquidacoes_total,
    )

    resultado_do_dia = _build_resultado_do_dia(
        decomposicao=decomposicao,
        apropriacao_antecipada=apropriacao_antecipada,
        juros_mora=juros_mora,
        desconto_concedido=desconto_concedido,
    )

    return DrillDcResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        aquisicoes_qtd=aquisicoes_qtd,
        aquisicoes_total=aquisicoes_total,
        aquisicoes=aquisicoes,
        liquidacoes_qtd=liquidacoes_qtd,
        liquidacoes_total=liquidacoes_total,
        liquidacoes_por_tipo=por_tipo,
        liquidacoes_top=top_liq,
        apropriacao=DrillDcApropriacao(
            estoque_d1=estoque_d1,
            estoque_d0=estoque_d0,
            delta_estoque=delta_estoque,
            aquisicoes_total=aquisicoes_total,
            liquidacoes_total=liquidacoes_total,
            apropriacao=apropriacao_val,
        ),
        decomposicao=decomposicao,
        resultado_do_dia=resultado_do_dia,
        mutacao_papeis=mutacao_papeis,
        liquidacao_parcial_papeis=liquidacao_parcial_papeis,
        abatimentos_papeis=abatimentos_papeis,
        migracao_wop_papeis=migracao_wop_papeis,
    )
