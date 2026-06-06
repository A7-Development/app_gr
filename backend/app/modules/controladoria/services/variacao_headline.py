"""Controladoria · Headline da Variacao da Cota Sub (o read de 10s, 0 LLM).

Orquestrador DETERMINISTICO: chama as tools que ja existem e monta veredito +
drivers (ranqueados por impacto LIMPO, giro separado) + flags. Nenhuma chamada
de LLM. Ver schema (variacao_headline.py) pro racional.

A "inteligencia" mora aqui: pegar o `resultado_do_dia` (giro ja separado do
value-mover) em vez do ΔDC cru, somar o carrego das prioritarias, o impacto
nao-provisionado, e empurrar os flags ate o topo.

Silver-only via as tools (cada uma le so silver, §13.2.1).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.controladoria.schemas.variacao_headline import (
    HeadlineDriver,
    HeadlineFlag,
    VariacaoHeadlineResponse,
)

ZERO = Decimal("0")
# Abaixo disso, um motor/flag e ruido — vira "rotina" / nao sobe.
_TOL_MATERIAL = Decimal("1000")
# Saldo da cota bate com o MEC se o residuo do SALDO (D0) e < isto (rounding).
_TOL_SALDO = Decimal("10")


def _fmt(v: Decimal) -> str:
    """R$ compacto pra detalhe (ex.: 'R$ 34,2k')."""
    a = abs(v)
    if a >= 1000:
        return f"R$ {float(v) / 1000:,.1f}k".replace(",", "§").replace(".", ",").replace("§", ".")
    return f"R$ {float(v):,.0f}".replace(",", ".")


async def compute_variacao_headline(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> VariacaoHeadlineResponse:
    """Monta o headline da variacao da cota do dia D0 a partir das tools."""
    # Imports tardios — evitam ciclo e so carregam o que o headline usa.
    from app.modules.controladoria.services.balanco_patrimonial import (
        compute_balanco_estrutural,
    )
    from app.modules.controladoria.services.conferencia_contas_a_pagar import (
        compute_movimento_contas_a_pagar,
    )
    from app.modules.controladoria.services.conferencia_cotas import (
        compute_movimento_cotas,
    )
    from app.modules.controladoria.services.cota_sub_drill_dc import compute_drill_dc

    bal = await compute_balanco_estrutural(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=data_d1,
    )
    d1 = bal.data_anterior
    dc = await compute_drill_dc(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    cot = await compute_movimento_cotas(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    cap = await compute_movimento_contas_a_pagar(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)

    res = dc.resultado_do_dia
    cota_delta = bal.pl_sub_d0 - bal.pl_sub_d1

    drivers: list[HeadlineDriver] = []

    # 1. Resultado da carteira (value-movers, giro JA fora) ──────────────────
    resultado_carteira = (
        res.carrego_apropriacao + res.apropriacao_antecipada
        + res.juros_mora - res.desconto_concedido + res.mutacao_total
    )
    det = [f"carrego {_fmt(res.carrego_apropriacao + res.apropriacao_antecipada)}"]
    if res.juros_mora >= _TOL_MATERIAL:
        det.append(f"mora {_fmt(res.juros_mora)}")
    if abs(res.mutacao_total) >= _TOL_MATERIAL:
        det.append(f"mutacao {_fmt(res.mutacao_total)}")
    drivers.append(HeadlineDriver(
        key="resultado_carteira", label="Resultado da carteira",
        impacto_pl_sub=resultado_carteira, detalhe=" · ".join(det), drill_key="dc",
        severidade="atencao" if res.mutacao_total <= -_TOL_MATERIAL else "rotina",
    ))

    # 2. Carrego das prioritarias (custo que a Sub paga) ────────────────────
    drivers.append(HeadlineDriver(
        key="carrego_prioritarias", label="Carrego prioritarias",
        impacto_pl_sub=-cot.custo_prioritarias_valorizacao,
        detalhe=f"Sr+Mez remuneracao {_fmt(cot.custo_prioritarias_valorizacao)}",
        drill_key=None,
    ))

    # 3. Despesa apropriada (accrual de taxas/consultoria) ──────────────────
    if cap.total_apropriacao >= _TOL_MATERIAL:
        drivers.append(HeadlineDriver(
            key="despesa", label="Despesa apropriada",
            impacto_pl_sub=-cap.total_apropriacao,
            detalhe=f"accrual do dia {_fmt(cap.total_apropriacao)}", drill_key="cpr_pagar",
        ))

    # 4. Despesa NAO provisionada (excesso que bate na cota) ────────────────
    if cap.impacto_resultado_nao_provisionado >= _TOL_MATERIAL:
        drivers.append(HeadlineDriver(
            key="despesa_nao_provisionada", label="Despesa nao provisionada",
            impacto_pl_sub=-cap.impacto_resultado_nao_provisionado,
            detalhe=f"pago acima da provisao {_fmt(cap.impacto_resultado_nao_provisionado)}",
            drill_key="cpr_pagar", severidade="atencao",
        ))

    # 5. PDD (limpo no balanco — sem giro) ──────────────────────────────────
    pdd_imp = next((ln.impacto_pl_sub for ln in bal.ativos if ln.key == "pdd"), ZERO)
    if abs(pdd_imp) >= _TOL_MATERIAL:
        drivers.append(HeadlineDriver(
            key="pdd", label="Provisao PDD", impacto_pl_sub=pdd_imp,
            detalhe=f"variacao de PDD {_fmt(pdd_imp)}", drill_key="pdd",
        ))

    # 6. Capital de cotista (aporte/resgate) — NEUTRO no PL Sub em R$: o caixa
    # entra/sai junto com o passivo; muda so o % de subordinacao (diluicao/
    # concentracao), nao o valor. Fica como evento de CONTEXTO (impacto 0), nao
    # como motor de resultado — senao distorce o ranking e o residuo de giro.
    if abs(cot.capital_liquido_prioritarias) >= _TOL_MATERIAL:
        drivers.append(HeadlineDriver(
            key="capital_cotista", label="Capital em prioritaria",
            impacto_pl_sub=ZERO,
            detalhe=f"aporte/resgate {_fmt(cot.capital_liquido_prioritarias)} "
                    "(neutro no PL Sub; dilui/concentra a subordinacao)",
            drill_key=None, severidade="atencao",
        ))

    # Os motores nomeados (P&L) ranqueiam por impacto.
    drivers.sort(key=lambda d: abs(d.impacto_pl_sub), reverse=True)

    # 7. Giro / reclassificacao = o residual (PL-neutro) — SEMPRE por ultimo.
    # Tudo que a cota mexeu menos os motores nomeados = movimentacao DC<->caixa
    # <->DI + linhas menores nao decompostas. Contexto, nao mover de resultado —
    # por isso fica no fim, fora do ranking (senao parece "o que moveu a cota").
    nomeados = sum((d.impacto_pl_sub for d in drivers), ZERO)
    giro_resid = cota_delta - nomeados
    if abs(giro_resid) >= _TOL_MATERIAL:
        drivers.append(HeadlineDriver(
            key="giro_reclassificacao", label="Giro / reclassificacao",
            impacto_pl_sub=giro_resid,
            detalhe=f"compra {_fmt(res.giro_aquisicoes)} / liquidacao {_fmt(res.giro_liquidacoes)} (neutro)",
            drill_key="dc", severidade="rotina",
        ))

    # ── Flags (o que vigiar) ────────────────────────────────────────────────
    flags: list[HeadlineFlag] = []

    if res.mutacao_total <= -_TOL_MATERIAL or (dc.decomposicao.mutacao_n and abs(res.mutacao_total) >= _TOL_MATERIAL):
        papel = dc.mutacao_papeis[0] if dc.mutacao_papeis else None
        desc = "Mutacao silenciosa na carteira"
        if papel is not None:
            # O que MUTOU (a causa) = o parametro editado; o IMPACTO = ΔVP.
            mudou: list[str] = []
            if papel.mudou_vn:
                pct_vn = ((papel.vn_d0 - papel.vn_d1) / papel.vn_d1 * 100) if papel.vn_d1 else ZERO
                mudou.append(f"VN {pct_vn:+.0f}% ({_fmt(papel.vn_d1)}->{_fmt(papel.vn_d0)})")
            if papel.mudou_taxa:
                mudou.append(f"taxa {float(papel.taxa_d1):.4f}->{float(papel.taxa_d0):.4f}")
            if papel.mudou_venc:
                mudou.append("vencimento")
            causa = " · ".join(mudou) if mudou else "parametro"
            desc = f"Mutacao {papel.cedente_nome[:22]}->{papel.sacado_nome[:16]}: {causa}"
        flags.append(HeadlineFlag(
            tipo="mutacao", descricao=desc, valor=res.mutacao_total,
            drill_key="dc", investigavel=True,
        ))

    if cap.impacto_resultado_nao_provisionado >= _TOL_MATERIAL:
        flags.append(HeadlineFlag(
            tipo="despesa_nao_provisionada",
            descricao="Pagamento de despesa acima da provisao bateu no PL Sub",
            valor=cap.impacto_resultado_nao_provisionado, drill_key="cpr_pagar",
        ))

    if abs(cot.capital_liquido_prioritarias) >= _TOL_MATERIAL:
        flags.append(HeadlineFlag(
            tipo="capital",
            descricao="Aporte/resgate de capital numa cota prioritaria",
            valor=cot.capital_liquido_prioritarias, drill_key=None,
        ))
    for o in cot.obrigacoes:
        if abs(o.saldo_d0) >= _TOL_MATERIAL:
            flags.append(HeadlineFlag(
                tipo="capital", descricao=f"Obrigacao com cotista em aberto: {o.descricao}",
                valor=o.saldo_d0, drill_key=None,
            ))

    # Flag SO quando o SALDO nao bate (a cota de verdade). O delta FORA sozinho e
    # lag de timing do dia anterior — nao acende flag (assustava sem motivo).
    if abs(bal.reconciliacao.residuo_d0) >= _TOL_SALDO:
        flags.append(HeadlineFlag(
            tipo="reconciliacao",
            descricao="Saldo da cota nao bate com o MEC",
            valor=bal.reconciliacao.residuo_d0, drill_key=None, investigavel=True,
        ))

    for nr in (getattr(bal, "nao_reconhecidos", None) or []):
        valor = Decimal(str(getattr(nr, "valor", 0) or 0))
        if abs(valor) >= _TOL_MATERIAL:
            flags.append(HeadlineFlag(
                tipo="nao_reconhecido",
                descricao=f"Lancamento nao reconhecido: {getattr(nr, 'descricao', '?')}",
                valor=valor, drill_key=None, investigavel=True,
            ))

    flags.sort(key=lambda f: abs(f.valor), reverse=True)

    return VariacaoHeadlineResponse(
        fundo_id=str(ua_id),
        fundo_nome=bal.fundo_nome,
        data=data_d0,
        data_anterior=d1,
        cota_sub_d1=bal.pl_sub_d1,
        cota_sub_d0=bal.pl_sub_d0,
        cota_sub_delta=cota_delta,
        delta_ativo=bal.total_ativo_delta,
        delta_passivo=bal.total_passivo_delta,
        reconciliacao_saldo=bal.reconciliacao.residuo_d0,
        reconciliacao_residuo=bal.reconciliacao.residuo_delta,
        reconciliacao_ok=abs(bal.reconciliacao.residuo_d0) < _TOL_SALDO,
        n_atencao=len(flags),
        drivers=drivers,
        giro_aquisicoes=res.giro_aquisicoes,
        giro_liquidacoes=res.giro_liquidacoes,
        flags=flags,
    )
