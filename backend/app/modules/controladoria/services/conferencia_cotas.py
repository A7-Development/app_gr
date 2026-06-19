"""Controladoria · Movimento de Cotas (passivo de cotistas) — prioritarias + obrigacoes.

Fecha o lado COTISTA/PATRIMONIO do balanco Cota Sub:
  1. Cotas Prioritarias (Senior/Mezanino) — capital vs valorizacao via
     compute_decomposicao_classes_mec (wh_mec_evolucao_cotas).
  2. Obrigacoes com Cotistas — CPR natureza capital_cotista (Cotas a Resgatar,
     Aporte, Resgate de Cotas), via classify_cpr_nature.

Ver schema (conferencia_cotas.py) pro racional. Silver-only (§13.2.1).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.conferencia_cotas import (
    ClasseCotaMovimento,
    ConferenciaCotasResponse,
    ObrigacaoCotista,
)
from app.modules.controladoria.services.cpr_natureza import classify_cpr_nature
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.cpr_movimento import CprMovimento

ZERO = Decimal("0")
_TOL = Decimal("1.0")


def _norm_obrig(d: str | None) -> str:
    """Descricao da obrigacao sem a data do texto (errada)."""
    import re

    s = re.sub(r"\s*\d{1,2}[./]\d{1,2}([./]\d{2,4})?.*$", "", d or "").strip(" .-")
    return s or (d or "")


async def compute_movimento_cotas(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> ConferenciaCotasResponse:
    """Movimento do passivo de cotistas do dia: prioritarias + obrigacoes."""
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

    # ── Classes de cota (reusa o decompositor capital vs valorizacao) ───────
    from app.modules.controladoria.services.balanco_patrimonial import (
        compute_decomposicao_classes_mec,
    )

    dec = await compute_decomposicao_classes_mec(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d1=d1,
    )

    classes: list[ClasseCotaMovimento] = []
    custo_prior = cap_prior = cap_sub = result_sub = ZERO
    for c in dec["classes"]:
        classe = c["classe"]
        ec = Decimal(c["efeito_capital"])
        ev = Decimal(c["efeito_valorizacao"])
        delta_pl = Decimal(c["delta_pl"])
        is_prior = classe in ("senior", "mezanino")
        # Prioritaria e passivo, MAS o capital (aporte/resgate) entra/sai do caixa
        # na mesma medida -> NEUTRO no PL Sub em R$ (so dilui/concentra o % de
        # subordinacao, nao o valor). So o CARREGO (valorizacao) que a Sub paga
        # impacta. O capital fica na coluna propria (efeito_capital).
        #
        # A propria Sub Jr: o `impacto` (e o cota_delta) e a RENTABILIDADE
        # (efeito_valorizacao), NAO o delta_pl. O aporte/resgate do cotista
        # subordinado (efeito_capital) e neutro no valor da cota — entra caixa e
        # cota juntos — entao NAO e resultado. Antes usava delta_pl e o aporte
        # vazava pro plug de Disponibilidades como se fosse resultado (bug 18/06).
        impacto = -ev if is_prior else ev
        if is_prior:
            custo_prior += ev
            cap_prior += ec
        else:
            cap_sub += ec
            result_sub += ev
        classes.append(
            ClasseCotaMovimento(
                classe=classe, label=c["label"],
                patrimonio_d1=Decimal(c["patrimonio_d1"]),
                patrimonio_d0=Decimal(c["patrimonio_d0"]),
                delta_pl=delta_pl,
                valor_cota_d1=Decimal(c["valor_cota_d1"]),
                valor_cota_d0=Decimal(c["valor_cota_d0"]),
                delta_quantidade=Decimal(c["delta_quantidade"]),
                efeito_capital=ec, efeito_valorizacao=ev,
                classificacao=c["classificacao"], impacto_pl_sub=impacto,
            )
        )

    # ── Obrigacoes com Cotistas (CPR capital_cotista) ───────────────────────
    async def _load_cap(data: date) -> dict[str, Decimal]:
        rows = (
            await db.execute(
                select(CprMovimento.descricao, CprMovimento.valor)
                .where(CprMovimento.tenant_id == tenant_id)
                .where(CprMovimento.unidade_administrativa_id == ua_id)
                .where(CprMovimento.data_posicao == data)
            )
        ).all()
        acc: dict[str, Decimal] = {}
        for desc, valor in rows:
            if classify_cpr_nature(desc) != "capital_cotista":
                continue
            key = _norm_obrig(desc)
            acc[key] = acc.get(key, ZERO) + Decimal(valor or 0)
        return acc

    cap1 = await _load_cap(d1)
    cap0 = await _load_cap(data_d0)

    obrigacoes: list[ObrigacaoCotista] = []
    for key in sorted(set(cap1) | set(cap0)):
        s1 = cap1.get(key, ZERO)
        s0 = cap0.get(key, ZERO)
        delta = s0 - s1
        if abs(s0) < _TOL and abs(delta) < _TOL:
            continue
        if key not in cap1:
            tipo = "nova"
        elif key not in cap0 or abs(s0) < _TOL:
            tipo = "quitada"
        elif abs(delta) < _TOL:
            tipo = "nova" if abs(s1) < _TOL else "aumento"  # estavel: mantem aberta
        elif (s0 < 0 and delta < 0) or (s0 > 0 and delta > 0):
            tipo = "aumento"  # cresceu em magnitude
        else:
            tipo = "reducao"
        obrigacoes.append(
            ObrigacaoCotista(descricao=key, saldo_d1=s1, saldo_d0=s0, delta=delta, tipo=tipo)
        )
    obrigacoes.sort(key=lambda o: -abs(o.saldo_d0))

    obrig_d0 = sum(cap0.values(), ZERO)
    obrig_d1 = sum(cap1.values(), ZERO)

    return ConferenciaCotasResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        classes=classes,
        custo_prioritarias_valorizacao=custo_prior,
        capital_liquido_prioritarias=cap_prior,
        capital_liquido_sub=cap_sub,
        resultado_sub=result_sub,
        obrigacoes=obrigacoes,
        obrigacoes_saldo_d0=obrig_d0,
        obrigacoes_delta=obrig_d0 - obrig_d1,
    )
