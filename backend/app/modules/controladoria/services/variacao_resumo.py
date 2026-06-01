"""Controladoria · Resumo do dia — decomposicao causal por grupo de balanco.

Orquestrador DETERMINISTICO (zero LLM) do `GET /variacao/resumo`. Monta as 6
transformacoes do waterfall (= os 6 grupos de balanco, impacto giro-limpo),
as ancoras MEC, a reconciliacao e as atencoes. Ver schema (variacao_resumo.py).

Fechamento por construcao (regra dura §14):
    Σ grupos.impacto_pl_sub == cota_delta (= bal.pl_sub_delta)
Disponibilidades e o PLUG: absorve o giro (caixa↔DC↔aplicacoes) e o rendimento
de caixa, de modo que a soma sempre bate. O giro bruto vai como nota neutra; o
residuo vs MEC (apresentada - oficial) vai na reconciliacao (barra se != 0).

Silver-only via as tools (cada uma le so silver, §13.2.1).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.controladoria.schemas.variacao_resumo import (
    AtencaoResumo,
    GrupoResumo,
    GrupoResumoLinha,
    ReconciliacaoResumo,
    VariacaoResumoResponse,
)

ZERO = Decimal("0")
_TOL = Decimal("1000")        # abaixo disso, um sinal e ruido (nao vira atencao)
_TOL_SALDO = Decimal("10")    # saldo da cota bate com o MEC se |residuo_d0| < isto

# Labels canonicos (um nome em todo lugar — alinhado com o balanco estrutural).
_GRUPO_LABEL = {
    "direitos_creditorios": "Direitos Creditórios",
    "pdd_wop":              "PDD & WOP",  # frontend adiciona o "(-)" (contra-ativo)
    "aplicacoes":           "Aplicações",
    "disponibilidades":     "Disponibilidades",
    "obrigacoes_provisoes": "Obrigações e Provisões",
    "cotas_prioritarias":   "Cotas Prioritárias",
}


def _fmt(v: Decimal | float) -> str:
    """R$ compacto (ex.: 'R$ 8,1k')."""
    f = float(v)
    if abs(f) >= 1000:
        return f"R$ {f / 1000:,.1f}k".replace(",", "§").replace(".", ",").replace("§", ".")
    return f"R$ {f:,.0f}".replace(",", ".")


async def compute_variacao_resumo(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> VariacaoResumoResponse:
    """Monta o Resumo do dia (6 grupos giro-limpos + ancoras MEC + atencoes)."""
    # Imports tardios — evitam ciclo e so carregam o que o resumo usa.
    from app.modules.controladoria.services.balanco_patrimonial import (
        compute_balanco_estrutural,
    )
    from app.modules.controladoria.services.conferencia_aplicacoes import (
        compute_movimento_aplicacoes,
    )
    from app.modules.controladoria.services.conferencia_contas_a_pagar import (
        compute_movimento_contas_a_pagar,
    )
    from app.modules.controladoria.services.conferencia_cotas import (
        compute_movimento_cotas,
    )
    from app.modules.controladoria.services.conferencia_nota_comercial import (
        compute_conferencia_nota_comercial,
    )
    from app.modules.controladoria.services.cota_sub_drill_dc import compute_drill_dc
    from app.modules.controladoria.services.cota_sub_drill_pdd import compute_drill_pdd

    bal = await compute_balanco_estrutural(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=data_d1,
    )
    d1 = bal.data_anterior

    dc = await compute_drill_dc(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    pdd = await compute_drill_pdd(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    aplic = await compute_movimento_aplicacoes(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    nc = await compute_conferencia_nota_comercial(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    cap = await compute_movimento_contas_a_pagar(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    cot = await compute_movimento_cotas(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)

    # impacto no PL Sub por chave de linha do balanco (sinal ja corrigido).
    imp: dict[str, Decimal] = {
        ln.key: ln.impacto_pl_sub for ln in (list(bal.ativos) + list(bal.passivos))
    }

    def _imp(*keys: str) -> Decimal:
        return sum((imp.get(k, ZERO) for k in keys), ZERO)

    cota_delta = bal.pl_sub_d0 - bal.pl_sub_d1

    # ── 1. Direitos Creditorios — resultado giro-limpo ──────────────────────
    res = dc.resultado_do_dia
    if res is not None:
        dc_impacto = (
            res.carrego_apropriacao + res.apropriacao_antecipada
            + res.juros_mora - res.desconto_concedido + res.mutacao_total
        )
        giro_dc = res.giro_aquisicoes + res.giro_liquidacoes
        dc_resumo = f"carrego {_fmt(res.apropriacao_total_dia)}"
        if abs(res.juros_mora) >= _TOL:
            dc_resumo += f" · mora {_fmt(res.juros_mora)}"
        if abs(res.mutacao_total) >= _TOL:
            dc_resumo += f" · mutação {_fmt(res.mutacao_total)}"
    else:  # fallback retrocompat: usa o delta bruto do balanco (com giro)
        dc_impacto = _imp("dc_bruto")
        giro_dc = ZERO
        dc_resumo = "resultado do dia"
    dc_severidade = "atencao" if (res is not None and res.mutacao_total <= -_TOL) else "rotina"

    # ── 2. (-) PDD & WOP — contra-ativo (ja giro-limpo no balanco) ──────────
    pdd_impacto = _imp("pdd")
    n_wop = len(pdd.papeis_wop)
    pdd_resumo = (pdd.resumo.direcao if pdd.resumo else "Δ") + f" {_fmt(abs(pdd.pdd_consolidado_delta))}"
    if n_wop:
        pdd_resumo += f" · {n_wop} em WOP"

    # ── 3. Aplicacoes — valorizacao (DI) + carrego NC + linhas menores ──────
    menores_delta = sum((ln.delta for ln in aplic.outras_linhas), ZERO)
    aplic_impacto = aplic.total_valorizacao + nc.total_apropriacao + menores_delta
    aplic_resumo = f"rendimento DI {_fmt(aplic.total_valorizacao)}"
    if abs(nc.total_apropriacao) >= _TOL:
        aplic_resumo += f" · carrego NC {_fmt(nc.total_apropriacao)}"

    aplic_linhas: list[GrupoResumoLinha] = [
        GrupoResumoLinha(
            key="fundos_di", label="Fundos DI", impacto_pl_sub=aplic.total_valorizacao,
            resumo=f"rendimento · capital {_fmt(aplic.total_capital_liquido)} (giro)",
            drill_key="fundos_di",
        ),
        GrupoResumoLinha(
            key="op_estruturadas", label="Op. Estruturadas", impacto_pl_sub=nc.total_apropriacao,
            resumo=f"carrego · {nc.n_notas_d0} nota(s)", drill_key="op_estruturadas",
        ),
    ]
    for ln in aplic.outras_linhas:
        aplic_linhas.append(GrupoResumoLinha(
            key=ln.linha, label=ln.label, impacto_pl_sub=ln.delta,
            resumo=ln.nota, drill_key=ln.linha,
        ))

    # ── 5. Obrigacoes e Provisoes — despesa + obrigacoes com cotistas ───────
    obrig_impacto = _imp("cpr_pagar", "cpr_obrigacoes_cotistas")
    obrig_resumo = f"provisão {_fmt(cap.total_apropriacao)} · pago {_fmt(cap.total_pago)}"
    obrig_severidade = "rotina"
    if cap.impacto_resultado_nao_provisionado >= _TOL:
        obrig_resumo += f" · ⚠ não provisionado {_fmt(cap.impacto_resultado_nao_provisionado)}"
        obrig_severidade = "atencao"
    obrig_linhas = [
        GrupoResumoLinha(
            key="cpr_pagar", label="Contas a Pagar", impacto_pl_sub=_imp("cpr_pagar"),
            resumo=f"provisão {_fmt(cap.total_apropriacao)}", drill_key="cpr_pagar",
            severidade=obrig_severidade,
        ),
        GrupoResumoLinha(
            key="cpr_obrigacoes_cotistas", label="Obrigações com Cotistas",
            impacto_pl_sub=_imp("cpr_obrigacoes_cotistas"),
            resumo=f"saldo {_fmt(cot.obrigacoes_saldo_d0)}", drill_key="cpr_obrigacoes_cotistas",
        ),
    ]

    # ── 6. Cotas Prioritarias — carrego Sr/Mez + capital ────────────────────
    cotas_impacto = _imp("senior", "mezanino")
    cotas_resumo = f"carrego Sr+Mez {_fmt(cot.custo_prioritarias_valorizacao)}"
    cotas_severidade = "rotina"
    if abs(cot.capital_liquido_prioritarias) >= _TOL:
        cotas_resumo += f" · capital {_fmt(cot.capital_liquido_prioritarias)}"
        cotas_severidade = "atencao"
    cotas_linhas = [
        GrupoResumoLinha(key="senior", label="Cota Senior", impacto_pl_sub=_imp("senior"),
                         resumo="carrego prioritário", drill_key="senior"),
        GrupoResumoLinha(key="mezanino", label="Cota Mezanino", impacto_pl_sub=_imp("mezanino"),
                         resumo="carrego prioritário", drill_key="mezanino"),
    ]

    # ── 4. Disponibilidades — o PLUG (fecha a soma) ─────────────────────────
    # Σ 6 grupos == cota_delta por construcao: Disponibilidades = cota_delta - resto.
    # Absorve o giro (caixa↔DC↔aplicacoes) + rendimento de caixa. ~0 em dia tipico.
    disp_impacto = cota_delta - (dc_impacto + pdd_impacto + aplic_impacto + obrig_impacto + cotas_impacto)
    disp_resumo = "caixa, tesouraria e contas a receber — giro do dia"
    disp_linhas = [
        GrupoResumoLinha(key="tesouraria", label="Tesouraria", impacto_pl_sub=_imp("tesouraria"),
                         resumo="saldo de tesouraria", drill_key="tesouraria"),
        GrupoResumoLinha(key="saldo_conta_corrente", label="Saldo Conta Corrente",
                         impacto_pl_sub=_imp("saldo_conta_corrente"), resumo="contas bancárias",
                         drill_key="saldo_conta_corrente"),
        GrupoResumoLinha(key="cpr_receber", label="Contas a Receber", impacto_pl_sub=_imp("cpr_receber"),
                         resumo="floating + diferidos (↺ giro)", drill_key="cpr_receber"),
    ]

    grupos = [
        GrupoResumo(key="direitos_creditorios", label=_GRUPO_LABEL["direitos_creditorios"],
                    natureza="ativo", impacto_pl_sub=dc_impacto, resumo=dc_resumo,
                    drill_key="dc", severidade=dc_severidade),
        GrupoResumo(key="pdd_wop", label=_GRUPO_LABEL["pdd_wop"], natureza="contra_ativo",
                    impacto_pl_sub=pdd_impacto, resumo=pdd_resumo, drill_key="pdd",
                    severidade="atencao" if n_wop else "rotina"),
        GrupoResumo(key="aplicacoes", label=_GRUPO_LABEL["aplicacoes"], natureza="ativo",
                    impacto_pl_sub=aplic_impacto, resumo=aplic_resumo, drill_key="fundos_di",
                    linhas=aplic_linhas),
        GrupoResumo(key="disponibilidades", label=_GRUPO_LABEL["disponibilidades"], natureza="ativo",
                    impacto_pl_sub=disp_impacto, resumo=disp_resumo, drill_key="cpr_receber",
                    linhas=disp_linhas),
        GrupoResumo(key="obrigacoes_provisoes", label=_GRUPO_LABEL["obrigacoes_provisoes"],
                    natureza="passivo", impacto_pl_sub=obrig_impacto, resumo=obrig_resumo,
                    drill_key="cpr_pagar", severidade=obrig_severidade, linhas=obrig_linhas),
        GrupoResumo(key="cotas_prioritarias", label=_GRUPO_LABEL["cotas_prioritarias"],
                    natureza="passivo", impacto_pl_sub=cotas_impacto, resumo=cotas_resumo,
                    drill_key="senior", severidade=cotas_severidade, linhas=cotas_linhas),
    ]

    # ── Giro (nota neutra) ──────────────────────────────────────────────────
    giro_total = (giro_dc + abs(aplic.total_capital_liquido)
                  + nc.total_aquisicao + nc.total_amortizacao)

    # ── Reconciliacao MEC ───────────────────────────────────────────────────
    r = bal.reconciliacao
    reconciliacao = ReconciliacaoResumo(
        variacao_apresentada=cota_delta,
        variacao_mec=r.pl_fonte_delta,
        residuo=r.residuo_delta,
        fecha=abs(r.residuo_delta) < Decimal("1"),
        residuo_saldo_d0=r.residuo_d0,
    )

    # ── Atencoes (lentes sobre o que ja esta no waterfall) ──────────────────
    atencoes: list[AtencaoResumo] = []
    if res is not None and (res.mutacao_total <= -_TOL or (dc.mutacao_papeis and abs(res.mutacao_total) >= _TOL)):
        papel = dc.mutacao_papeis[0] if dc.mutacao_papeis else None
        desc = "Mutação silenciosa na carteira"
        if papel is not None:
            mudou = []
            if papel.mudou_vn:
                mudou.append("valor nominal")
            if papel.mudou_taxa:
                mudou.append(f"taxa {float(papel.taxa_d1):.4f}→{float(papel.taxa_d0):.4f}")
            if papel.mudou_venc:
                mudou.append("vencimento")
            causa = " · ".join(mudou) if mudou else "parâmetro"
            desc = f"Mutação silenciosa · {papel.cedente_nome[:20]}→{papel.sacado_nome[:16]}: {causa}"
        atencoes.append(AtencaoResumo(
            tipo="mutacao", descricao=desc, valor=res.mutacao_total,
            grupo_key="direitos_creditorios", grupo_label=_GRUPO_LABEL["direitos_creditorios"],
            drill_key="dc", investigavel=True,
        ))
    if cap.impacto_resultado_nao_provisionado >= _TOL:
        atencoes.append(AtencaoResumo(
            tipo="despesa_nao_provisionada",
            descricao="Pagamento de despesa acima da provisão bateu no PL Sub",
            valor=cap.impacto_resultado_nao_provisionado,
            grupo_key="obrigacoes_provisoes", grupo_label=_GRUPO_LABEL["obrigacoes_provisoes"],
            drill_key="cpr_pagar",
        ))
    if pdd.papeis_wop:
        atencoes.append(AtencaoResumo(
            tipo="write_off",
            descricao=f"{n_wop} título(s) levado(s) a write-off (WOP) — saíram sem liquidação",
            valor=pdd.papeis_wop_total_pdd_d1,
            grupo_key="pdd_wop", grupo_label=_GRUPO_LABEL["pdd_wop"],
            drill_key="pdd", investigavel=True,
        ))
    if abs(cot.capital_liquido_prioritarias) >= _TOL:
        atencoes.append(AtencaoResumo(
            tipo="capital",
            descricao="Evento de capital numa prioritária (diluiu/concentrou a Sub)",
            valor=cot.capital_liquido_prioritarias,
            grupo_key="cotas_prioritarias", grupo_label=_GRUPO_LABEL["cotas_prioritarias"],
            drill_key="senior",
        ))
    if abs(r.residuo_d0) >= _TOL_SALDO:
        atencoes.append(AtencaoResumo(
            tipo="reconciliacao", descricao="Saldo da cota não bate com o MEC",
            valor=r.residuo_d0, investigavel=True,
        ))
    for item in (getattr(bal, "nao_reconhecidos", None) or []):
        valor = Decimal(str(getattr(item, "valor_d0", 0) or 0))
        if abs(valor) >= _TOL:
            atencoes.append(AtencaoResumo(
                tipo="nao_reconhecido",
                descricao=f"Lançamento não reconhecido: {getattr(item, 'label', '?')}",
                valor=valor, investigavel=True,
            ))
    atencoes.sort(key=lambda a: abs(a.valor), reverse=True)

    return VariacaoResumoResponse(
        fundo_id=str(ua_id),
        fundo_nome=bal.fundo_nome,
        data=data_d0,
        data_anterior=d1,
        pl_sub_mec_d1=r.pl_fonte_d1,
        pl_sub_mec_d0=r.pl_fonte_d0,
        pl_sub_calc_d1=bal.pl_sub_d1,
        pl_sub_calc_d0=bal.pl_sub_d0,
        cota_delta=cota_delta,
        grupos=grupos,
        giro_total=giro_total,
        reconciliacao=reconciliacao,
        atencoes=atencoes,
    )
