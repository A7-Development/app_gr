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

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub_drill import (
    DrillDcApropriacao,
    DrillDcAquisicao,
    DrillDcDecomposicao,
    DrillDcLiquidacaoLinha,
    DrillDcLiquidacaoPorTipo,
    DrillDcMigracaoWopPapel,
    DrillDcMutacaoPapel,
    DrillDcResponse,
    DrillDcResultadoDoDia,
)
from app.modules.controladoria.services.cota_sub import _sum_dc
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
    renda_multa_juros, desconto_concedido).

    - `total_valor_aquisicao` e o que sai do estoque (custo no FIDC); usado
      na formula da apropriacao.
    - `renda_multa_juros` = -Σ(ajuste<0): sacado pagou ACIMA do vencimento
      (multa/juros de mora). Sempre >= 0 (renda).
    - `desconto_concedido` = Σ(ajuste>0): sacado pagou ABAIXO do vencimento
      (abatimento). Magnitude >= 0 (custo). Split por sinal feito em SQL
      (case por linha), entao tipos com ajuste misto contam corretamente.
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
            func.coalesce(
                func.sum(case((LiquidacaoRecebivel.ajuste < 0, LiquidacaoRecebivel.ajuste), else_=ZERO)),
                ZERO,
            ).label("sum_aj_neg"),
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
    renda_multa_juros = ZERO  # -Σ(ajuste<0), acumulado por linha via SQL
    desconto_concedido = ZERO  # Σ(ajuste>0)
    for tipo, qtd, sum_pago, sum_aq, sum_venc, sum_aj, sum_aj_neg, sum_aj_pos in agg_rows:
        sum_pago_d = Decimal(sum_pago or 0)
        sum_aq_d = Decimal(sum_aq or 0)
        sum_aj_d = Decimal(sum_aj or 0)
        qtd_total += int(qtd or 0)
        sum_aquisicao_total += sum_aq_d
        renda_multa_juros += -Decimal(sum_aj_neg or 0)  # ajuste<0 -> renda positiva
        desconto_concedido += Decimal(sum_aj_pos or 0)  # ajuste>0 -> custo (magnitude)
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
        renda_multa_juros, desconto_concedido,
    )


async def _decompor_delta_dc(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data_d1: date,
    data_d0: date,
    aquisicoes_evento_total: Decimal,
    liquidacoes_evento_total: Decimal,
) -> tuple[DrillDcDecomposicao, list[DrillDcMutacaoPapel], list[DrillDcMigracaoWopPapel]]:
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
                    faixa_pdd_d1=r1.faixa_pdd,
                    vp_d1=Decimal(r1.valor_presente),
                    valor_pdd_d1=Decimal(r1.valor_pdd),
                )
            )

    # ── Buckets C/M: populacao constante nao-WOP ───────────────────────────
    apropriacao_n = 0
    apropriacao_total = ZERO
    mutacao_n = 0
    mutacao_total = ZERO
    mutacao_papeis_all: list[DrillDcMutacaoPapel] = []
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

        mudou_vn = Decimal(r1.valor_nominal) != Decimal(r0.valor_nominal)
        mudou_taxa = Decimal(r1.taxa_recebivel) != Decimal(r0.taxa_recebivel)
        mudou_venc = r1.data_vencimento_ajustada != r0.data_vencimento_ajustada

        if mudou_vn or mudou_taxa or mudou_venc:
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
                        vn_d1=Decimal(r1.valor_nominal),
                        vn_d0=Decimal(r0.valor_nominal),
                        taxa_d1=Decimal(r1.taxa_recebivel),
                        taxa_d0=Decimal(r0.taxa_recebivel),
                        venc_d1=r1.data_vencimento_ajustada,
                        venc_d0=r0.data_vencimento_ajustada,
                        mudou_vn=mudou_vn,
                        mudou_taxa=mudou_taxa,
                        mudou_venc=mudou_venc,
                    )
                )
        else:
            apropriacao_n += 1
            apropriacao_total += delta_vp

    # Top N mutacoes por |delta_vp| (UI corta — backend devolve mais pra
    # debug futuro nao quebrar).
    mutacao_papeis_all.sort(key=lambda p: abs(p.delta_vp), reverse=True)
    mutacao_papeis_top = mutacao_papeis_all[:_TOP_MUTACAO_N]

    # Identidade: saldo_d0 - (saldo_d1 + A - L - W + C + M) = residuo
    delta_saldo = saldo_d0 - saldo_d1
    explicado = aquisicoes_total - liquidacoes_total - migracao_wop_total + apropriacao_total + mutacao_total
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
        mutacao_n=mutacao_n,
        mutacao_total=mutacao_total,
        residuo=residuo,
        cross_check_aquisicoes_evento=aquisicoes_evento_total,
        cross_check_liquidacoes_evento=liquidacoes_evento_total,
        cross_check_diff_aquisicoes=diff_aq,
        cross_check_diff_liquidacoes=diff_li,
    )

    return decomposicao, mutacao_papeis_top, migracao_wop_papeis


def _build_resultado_do_dia(
    *,
    decomposicao: DrillDcDecomposicao,
    renda_multa_juros: Decimal,
    desconto_concedido: Decimal,
) -> DrillDcResultadoDoDia:
    """Consolida os motores de renda da DC com sinal de IMPACTO no PL Sub.

    Move pra dentro da tool a "regra dura de sinal" que o prompt do agente
    carregava: renda de multa/juros e SEMPRE positiva (= -Σajuste<0), desconto
    e custo (Σajuste>0), e o agente nao precisa mais flipar o `ajuste` de cabeca
    (fonte do erro de ~3x ao confundir com `ganho_liquido`).

    `motor_dominante` e `resultado_outlier` sao descritores de DOMINIO (nao
    enums do agente) — a tool wrapper deriva deles a `classificacao_sugerida`.
    """
    carrego = decomposicao.apropriacao_total
    ajuste_liquido = renda_multa_juros - desconto_concedido
    mutacao = decomposicao.mutacao_total
    wop = decomposicao.migracao_wop_total

    # Motor dominante: maior magnitude entre os motores de renda/correcao.
    candidatos: dict[str, Decimal] = {
        "carrego": abs(carrego),
        "multa_juros": abs(renda_multa_juros),
        "desconto": abs(desconto_concedido),
        "mutacao": abs(mutacao),
        "write_off": abs(wop),
    }
    top = max(candidatos, key=lambda k: candidatos[k])
    top_val = candidatos[top]
    # "misto" quando o 2o motor chega a >= 70% do dominante (nenhum domina claro).
    segundo = sorted(candidatos.values(), reverse=True)[1] if len(candidatos) > 1 else ZERO
    motor_dominante = "misto" if top_val > ZERO and segundo >= top_val * Decimal("0.7") else top

    # Outlier: carrego deixou de ser o motor (ajuste OU mutacao supera o carrego).
    resultado_outlier = (
        abs(ajuste_liquido) > abs(carrego) or abs(mutacao) > abs(carrego)
    )

    return DrillDcResultadoDoDia(
        carrego_apropriacao=carrego,
        renda_multa_juros=renda_multa_juros,
        desconto_concedido=desconto_concedido,
        ajuste_liquido_resultado=ajuste_liquido,
        mutacao_total=mutacao,
        migracao_wop_total=wop,
        giro_aquisicoes=decomposicao.aquisicoes_total,
        giro_liquidacoes=decomposicao.liquidacoes_total,
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
        renda_multa_juros, desconto_concedido,
    ) = await _liquidacoes_do_dia(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        fundo_doc=ua.cnpj or "",
        data=data_d0,
    )

    delta_estoque = estoque_d0 - estoque_d1
    apropriacao_val = delta_estoque + liquidacoes_total - aquisicoes_total

    # F2 redesign: decomposicao em 5 buckets via granular.
    decomposicao, mutacao_papeis, migracao_wop_papeis = await _decompor_delta_dc(
        db,
        tenant_id=tenant_id,
        fundo_doc=ua.cnpj or "",
        data_d1=d1,
        data_d0=data_d0,
        aquisicoes_evento_total=aquisicoes_total,
        liquidacoes_evento_total=liquidacoes_total,
    )

    resultado_do_dia = _build_resultado_do_dia(
        decomposicao=decomposicao,
        renda_multa_juros=renda_multa_juros,
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
        migracao_wop_papeis=migracao_wop_papeis,
    )
