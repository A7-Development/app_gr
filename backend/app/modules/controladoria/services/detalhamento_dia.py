"""Controladoria · Detalhamento do dia (painel dos 60%) — orquestra as tools.

Um card por area do balanco, com o resumo de 1 linha da sua tool + o delta
(impacto no PL Sub) + a chave do drill. Determinismo total, zero LLM. Ver schema
(detalhamento_dia.py) pro racional.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.controladoria.schemas.detalhamento_dia import (
    AreaDetalhe,
    DetalhamentoDiaResponse,
)

ZERO = Decimal("0")
_TOL = Decimal("1000")


def _fmt(v: Decimal | float) -> str:
    """R$ compacto (ex.: 'R$ 8,1k')."""
    f = float(v)
    if abs(f) >= 1000:
        return f"R$ {f / 1000:,.1f}k".replace(",", "§").replace(".", ",").replace("§", ".")
    return f"R$ {f:,.0f}".replace(",", ".")


async def compute_detalhamento_dia(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> DetalhamentoDiaResponse:
    """Monta o detalhamento do dia (uma area por card) a partir das tools."""
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

    # impacto no PL Sub por chave de linha do balanco.
    imp: dict[str, Decimal] = {
        ln.key: ln.impacto_pl_sub for ln in (list(bal.ativos) + list(bal.passivos))
    }

    def _soma(*keys: str) -> Decimal:
        return sum((imp.get(k, ZERO) for k in keys), ZERO)

    areas: list[AreaDetalhe] = []

    # ── ATIVO ───────────────────────────────────────────────────────────────
    # Direitos Creditorios — resultado vs giro.
    dc = await compute_drill_dc(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    r = dc.resultado_do_dia
    resultado = r.carrego_apropriacao + r.apropriacao_antecipada + r.juros_mora - r.desconto_concedido + r.mutacao_total
    giro = r.giro_aquisicoes - r.giro_liquidacoes
    dc_resumo = f"resultado {_fmt(resultado)}"
    if abs(r.mutacao_total) >= _TOL:
        dc_resumo += f" (mutacao {_fmt(r.mutacao_total)})"
    dc_resumo += f" · giro {_fmt(giro)} neutro"
    areas.append(AreaDetalhe(
        key="dc", label="Direitos Creditórios", grupo="ativo",
        delta=imp.get("dc_bruto", ZERO), resumo=dc_resumo, drill_key="dc",
        severidade="atencao" if r.mutacao_total <= -_TOL else "rotina",
    ))

    # PDD (constituicao/reversao vive em pdd.resumo, pode ser None).
    pdd = await compute_drill_pdd(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    direcao = pdd.resumo.direcao if pdd.resumo is not None else "Δ"
    pdd_resumo = f"{direcao} {_fmt(abs(pdd.pdd_consolidado_delta))}"
    areas.append(AreaDetalhe(
        key="pdd", label="PDD", grupo="ativo", delta=imp.get("pdd", ZERO),
        resumo=pdd_resumo, drill_key="pdd",
    ))

    # Notas Comerciais (Op. Estruturadas).
    nc = await compute_conferencia_nota_comercial(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    areas.append(AreaDetalhe(
        key="op_estruturadas", label="Notas Comerciais", grupo="ativo",
        delta=imp.get("op_estruturadas", ZERO),
        resumo=f"carrego {_fmt(nc.total_apropriacao)} · {len(nc.movimentos)} movimento(s)",
        drill_key="op_estruturadas",
    ))

    # Aplicacoes (Fundos DI + TPF + Compromissada + Outros).
    aplic = await compute_movimento_aplicacoes(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    areas.append(AreaDetalhe(
        key="fundos_di", label="Aplicações", grupo="ativo",
        delta=_soma("fundos_di", "titulos_publicos", "compromissada", "outros_ativos"),
        resumo=f"rendimento {_fmt(aplic.total_valorizacao)} · capital {_fmt(aplic.total_capital_liquido)}",
        drill_key="fundos_di",
    ))

    # Disponibilidades (Caixa: floating + tesouraria + conta corrente).
    areas.append(AreaDetalhe(
        key="cpr_receber", label="Disponibilidades", grupo="ativo",
        delta=_soma("tesouraria", "saldo_conta_corrente", "cpr_receber"),
        resumo="caixa, floating e tesouraria — movimentação do dia",
        drill_key="cpr_receber",
    ))

    # ── PASSIVO ──────────────────────────────────────────────────────────────
    cap = await compute_movimento_contas_a_pagar(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    cap_resumo = f"provisão {_fmt(cap.total_apropriacao)} · pago {_fmt(cap.total_pago)}"
    if cap.impacto_resultado_nao_provisionado >= _TOL:
        cap_resumo += f" · ⚠ não provisionado {_fmt(cap.impacto_resultado_nao_provisionado)}"
    areas.append(AreaDetalhe(
        key="cpr_pagar", label="Contas a Pagar", grupo="passivo",
        delta=imp.get("cpr_pagar", ZERO), resumo=cap_resumo, drill_key="cpr_pagar",
        severidade="atencao" if cap.impacto_resultado_nao_provisionado >= _TOL else "rotina",
    ))

    cotas = await compute_movimento_cotas(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1)
    cot_resumo = f"carrego {_fmt(cotas.custo_prioritarias_valorizacao)}"
    if abs(cotas.capital_liquido_prioritarias) >= _TOL:
        cot_resumo += f" · capital {_fmt(cotas.capital_liquido_prioritarias)}"
    areas.append(AreaDetalhe(
        key="senior", label="Cotas Prioritárias", grupo="passivo",
        delta=_soma("senior", "mezanino"), resumo=cot_resumo, drill_key="senior",
        severidade="atencao" if abs(cotas.capital_liquido_prioritarias) >= _TOL else "rotina",
    ))

    # Obrigacoes com Cotistas — so quando ha saldo.
    if abs(cotas.obrigacoes_saldo_d0) >= _TOL or abs(cotas.obrigacoes_delta) >= _TOL:
        areas.append(AreaDetalhe(
            key="cpr_obrigacoes_cotistas", label="Obrigações com Cotistas", grupo="passivo",
            delta=imp.get("cpr_obrigacoes_cotistas", ZERO),
            resumo=f"saldo {_fmt(cotas.obrigacoes_saldo_d0)} · {len(cotas.obrigacoes)} em aberto",
            drill_key="cpr_obrigacoes_cotistas", severidade="atencao",
        ))

    # Ordena: ativo antes de passivo; dentro, por |delta|.
    areas.sort(key=lambda a: (a.grupo != "ativo", -abs(a.delta)))

    return DetalhamentoDiaResponse(
        fundo_id=str(ua_id),
        fundo_nome=bal.fundo_nome,
        data=data_d0,
        data_anterior=d1,
        areas=areas,
    )
