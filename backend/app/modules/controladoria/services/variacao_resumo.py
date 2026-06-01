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
    GiroCapitalItem,
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
        dc_resumo = f"carrego {_fmt(res.apropriacao_total_dia)}"
        if abs(res.juros_mora) >= _TOL:
            dc_resumo += f" · mora {_fmt(res.juros_mora)}"
        if abs(res.mutacao_total) >= _TOL:
            dc_resumo += f" · mutação {_fmt(res.mutacao_total)}"
    else:  # fallback retrocompat: usa o delta bruto do balanco (com giro)
        dc_impacto = _imp("dc_bruto")
        dc_resumo = "resultado do dia"
    dc_severidade = "atencao" if (res is not None and res.mutacao_total <= -_TOL) else "rotina"

    # ── 2. (-) PDD & WOP — contra-ativo (ja giro-limpo no balanco) ──────────
    pdd_impacto = _imp("pdd")
    n_wop = len(pdd.papeis_wop)
    pdd_resumo = (pdd.resumo.direcao if pdd.resumo else "Δ") + f" {_fmt(abs(pdd.pdd_consolidado_delta))}"
    if n_wop:
        pdd_resumo += f" · {n_wop} em WOP"

    # ── 3. Aplicacoes — GIRO-LIMPO: rendimento DI + carrego NC + marcacao TPF.
    # Capital (aplicacao/resgate de fundo DI) e giro (compromissada) saem pra
    # giro_capital. Σ sublinhas == aplic_impacto (coerente com o drill).
    tpf_marcacao = _imp("titulos_publicos")
    aplic_impacto = aplic.total_valorizacao + nc.total_apropriacao + tpf_marcacao
    aplic_resumo = f"rendimento DI {_fmt(aplic.total_valorizacao)}"
    if abs(nc.total_apropriacao) >= _TOL:
        aplic_resumo += f" · carrego NC {_fmt(nc.total_apropriacao)}"
    aplic_linhas: list[GrupoResumoLinha] = [
        GrupoResumoLinha(key="fundos_di", label="Fundos DI", impacto_pl_sub=aplic.total_valorizacao,
                         resumo="rendimento DI (líquido de IR)", drill_key=None),
        GrupoResumoLinha(key="op_estruturadas", label="Op. Estruturadas", impacto_pl_sub=nc.total_apropriacao,
                         resumo=f"carrego · {nc.n_notas_d0} nota(s)", drill_key=None),
        GrupoResumoLinha(key="titulos_publicos", label="Títulos Públicos", impacto_pl_sub=tpf_marcacao,
                         resumo="marcação a mercado", drill_key=None),
    ]

    # ── 5. Obrigacoes e Provisoes — so DESPESA (cpr_pagar). O capital de cotista
    # (Obrigacoes com Cotistas) sai pra giro_capital (e neutro pro PL Sub).
    obrig_impacto = _imp("cpr_pagar")
    obrig_resumo = f"provisão {_fmt(cap.total_apropriacao)} · pago {_fmt(cap.total_pago)}"
    obrig_severidade = "rotina"
    if cap.impacto_resultado_nao_provisionado >= _TOL:
        obrig_resumo += f" · ⚠ não provisionado {_fmt(cap.impacto_resultado_nao_provisionado)}"
        obrig_severidade = "atencao"
    obrig_linhas = [
        GrupoResumoLinha(
            key="cpr_pagar", label="Contas a Pagar", impacto_pl_sub=_imp("cpr_pagar"),
            resumo=f"provisão {_fmt(cap.total_apropriacao)} · pago {_fmt(cap.total_pago)}",
            drill_key="cpr_pagar", severidade=obrig_severidade,
        ),
    ]

    # ── 6. Cotas Prioritarias — so CARREGO (remuneracao Sr/Mez que a Sub paga).
    # O capital (aporte/resgate) sai pra giro_capital. Σ sublinhas (carrego por
    # classe) == cotas_impacto.
    cotas_impacto = -cot.custo_prioritarias_valorizacao
    cotas_resumo = f"carrego Sr+Mez {_fmt(cot.custo_prioritarias_valorizacao)}"
    cotas_severidade = "atencao" if abs(cot.capital_liquido_prioritarias) >= _TOL else "rotina"
    cotas_linhas = [
        GrupoResumoLinha(
            key=c.classe, label=c.label, impacto_pl_sub=-c.efeito_valorizacao,
            resumo="carrego (remuneração da cota)", drill_key="senior",
        )
        for c in cot.classes if c.classe != "sub_jr"
    ]

    # ── 4. Disponibilidades — rendimento LIQUIDO de caixa. Como os outros 5
    # grupos ja sao giro/capital-limpos, o residuo (cota_delta - eles) e o
    # rendimento real do caixa (pequeno). O giro/floating/capital do caixa vai
    # pra giro_capital. Atomico (sem sublinhas): o detalhe vive na secao giro.
    disp_impacto = cota_delta - (dc_impacto + pdd_impacto + aplic_impacto + obrig_impacto + cotas_impacto)
    disp_resumo = "rendimento líquido de caixa — giro/floating do dia em 'Giro e capital'"
    disp_linhas: list[GrupoResumoLinha] = []

    grupos = [
        GrupoResumo(key="direitos_creditorios", label=_GRUPO_LABEL["direitos_creditorios"],
                    natureza="ativo", impacto_pl_sub=dc_impacto, resumo=dc_resumo,
                    drill_key="dc", severidade=dc_severidade),
        GrupoResumo(key="pdd_wop", label=_GRUPO_LABEL["pdd_wop"], natureza="contra_ativo",
                    impacto_pl_sub=pdd_impacto, resumo=pdd_resumo, drill_key="pdd",
                    severidade="atencao" if n_wop else "rotina"),
        GrupoResumo(key="aplicacoes", label=_GRUPO_LABEL["aplicacoes"], natureza="ativo",
                    impacto_pl_sub=aplic_impacto, resumo=aplic_resumo, drill_key=None,
                    linhas=aplic_linhas),
        GrupoResumo(key="disponibilidades", label=_GRUPO_LABEL["disponibilidades"], natureza="ativo",
                    impacto_pl_sub=disp_impacto, resumo=disp_resumo, drill_key=None,
                    linhas=disp_linhas),
        GrupoResumo(key="obrigacoes_provisoes", label=_GRUPO_LABEL["obrigacoes_provisoes"],
                    natureza="passivo", impacto_pl_sub=obrig_impacto, resumo=obrig_resumo,
                    drill_key="cpr_pagar", severidade=obrig_severidade, linhas=obrig_linhas),
        GrupoResumo(key="cotas_prioritarias", label=_GRUPO_LABEL["cotas_prioritarias"],
                    natureza="passivo", impacto_pl_sub=cotas_impacto, resumo=cotas_resumo,
                    drill_key="senior", severidade=cotas_severidade, linhas=cotas_linhas),
    ]

    # ── Giro e capital do dia (movimentos NEUTROS, fora do waterfall) ────────
    giro_capital: list[GiroCapitalItem] = []
    giro_carteira = (res.giro_aquisicoes - res.giro_liquidacoes) if res is not None else ZERO
    if res is not None and abs(giro_carteira) >= _TOL:
        giro_capital.append(GiroCapitalItem(
            tipo="giro_carteira", label="Compra/liquidação de carteira", valor=giro_carteira,
            nota=f"comprou {_fmt(res.giro_aquisicoes)} · liquidou {_fmt(res.giro_liquidacoes)}",
        ))
    if abs(cot.capital_liquido_prioritarias) >= _TOL:
        giro_capital.append(GiroCapitalItem(
            tipo="capital_cotista", label="Aporte/resgate em cota prioritária",
            valor=cot.capital_liquido_prioritarias,
            nota="entra/sai caixa e cota na mesma medida — neutro no PL Sub total",
        ))
    if abs(cot.obrigacoes_delta) >= _TOL:
        giro_capital.append(GiroCapitalItem(
            tipo="capital_cotista", label="Obrigações com cotistas",
            valor=cot.obrigacoes_delta, nota="resgates/aportes a liquidar",
        ))
    if abs(aplic.total_capital_liquido) >= _TOL:
        giro_capital.append(GiroCapitalItem(
            tipo="capital_aplicacao", label="Aplicação/resgate em Fundos DI",
            valor=aplic.total_capital_liquido, nota="caixa ocioso estacionado/retirado",
        ))
    floating = _imp("cpr_receber")
    if abs(floating) >= _TOL:
        giro_capital.append(GiroCapitalItem(
            tipo="floating", label="Floating de liquidações (Contas a Receber)",
            valor=floating, nota="recebíveis liquidados em trânsito",
        ))
    compr = _imp("compromissada")
    if abs(compr) >= _TOL:
        giro_capital.append(GiroCapitalItem(
            tipo="outros", label="Compromissada (overnight)", valor=compr,
        ))
    giro_capital.sort(key=lambda g: abs(g.valor), reverse=True)
    giro_total = sum((abs(g.valor) for g in giro_capital), ZERO)

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
        giro_capital=giro_capital,
        reconciliacao=reconciliacao,
        atencoes=atencoes,
    )
