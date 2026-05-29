"""Smoke do `resumo` (sinal economico) no drill CPR (tools grossas, 2026-05-29).

Nasce do bug REALINVEST 28/05: o agente narrou "Contas a Pagar SUBIU R$ 108.555"
quando ela CAIU de R$ 157.311 para R$ 48.756 (reduziu o passivo, bom pra Sub).
Causa: o drill devolvia o total CRU negativo, cujo delta com sinal (+108k) e
OPOSTO a variacao da magnitude (-108k).

Valida:
  1. pagar.resumo.magnitude_d1/d0 == magnitudes reais; variacao_magnitude < 0
     (CAIU); impacto_pl_sub > 0 (reduz passivo).
  2. RECONCILIACAO: resumo.variacao_magnitude de cada lado == delta da linha
     correspondente no balanco estrutural (cpr_pagar / cpr_receber).
  3. Por natureza: apropriacao_despesa do lado pagar tem variacao_magnitude < 0
     e impacto_pl_sub > 0 (despesa paga/baixada — nao constituida).
  4. sugestao.resumo_factual diz "Contas a Pagar caiu".

Read-only. dev=prod seguro.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.agentic.tools.controladoria.cota_sub import _sugestao_drill_cpr  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.modules.controladoria.services.balanco_patrimonial import (  # noqa: E402
    compute_balanco_estrutural,
)
from app.modules.controladoria.services.cota_sub_drill_cpr import (  # noqa: E402
    compute_drill_cpr,
)

_failures: list[str] = []
TOL = Decimal("0.01")


def _check(cond: bool, label: str) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _failures.append(label)


def _fmt(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        row = (
            await db.execute(
                text(
                    "SELECT t.id, ua.id FROM tenants t "
                    "JOIN cadastros_unidade_administrativa ua ON ua.tenant_id=t.id "
                    "WHERE t.slug='a7-credit' AND ua.cnpj='42449234000160' LIMIT 1"
                )
            )
        ).first()
        tenant_id, ua_id = row
        d0 = date(2026, 5, 28)
        print(f"=== REALINVEST {d0.isoformat()} ===")

        bal = await compute_balanco_estrutural(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=d0)
        cp = next(ln for ln in bal.passivos if ln.key == "cpr_pagar")
        cr = next(ln for ln in bal.ativos if ln.key == "cpr_receber")
        print(f"  BALANCO cpr_pagar:   d1={_fmt(cp.d1)} d0={_fmt(cp.d0)} delta={_fmt(cp.delta)}")
        print(f"  BALANCO cpr_receber: d1={_fmt(cr.d1)} d0={_fmt(cr.d0)} delta={_fmt(cr.delta)}")

        pagar = await compute_drill_cpr(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=d0, side="pagar")
        receber = await compute_drill_cpr(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=d0, side="receber")
        rp, rr = pagar.resumo, receber.resumo
        assert rp is not None and rr is not None

        print(f"  DRILL pagar.resumo:   mag d1={_fmt(rp.magnitude_d1)} d0={_fmt(rp.magnitude_d0)} "
              f"var={_fmt(rp.variacao_magnitude)} impacto={_fmt(rp.impacto_pl_sub)} dir={rp.direcao}")

        # 1. Sinal economico correto no lado pagar.
        _check(rp.magnitude_d1 > rp.magnitude_d0, "pagar: magnitude D-1 > D0 (a divida encolheu)")
        _check(rp.direcao == "caiu", "pagar: direcao == 'caiu'")
        _check(rp.variacao_magnitude < 0, "pagar: variacao_magnitude < 0")
        _check(rp.impacto_pl_sub > 0, "pagar: impacto_pl_sub > 0 (reduz passivo, bom)")

        # 2. RECONCILIACAO com o balanco (a falha que enganou o agente).
        _check(abs(rp.variacao_magnitude - cp.delta) < TOL,
               f"pagar.variacao_magnitude ({_fmt(rp.variacao_magnitude)}) == balanco cpr_pagar.delta ({_fmt(cp.delta)})")
        _check(abs(rr.variacao_magnitude - cr.delta) < TOL,
               f"receber.variacao_magnitude ({_fmt(rr.variacao_magnitude)}) == balanco cpr_receber.delta ({_fmt(cr.delta)})")

        # 3. Por natureza: despesa apropriada do lado pagar caiu (paga/baixada).
        desp = next((n for n in pagar.naturezas if n.natureza == "apropriacao_despesa"), None)
        if desp is not None:
            print(f"  natureza despesa: sum_delta(cru)={_fmt(desp.sum_delta)} "
                  f"var_mag={_fmt(desp.variacao_magnitude)} impacto={_fmt(desp.impacto_pl_sub)}")
            _check(desp.variacao_magnitude < 0 and desp.impacto_pl_sub > 0,
                   "natureza despesa: magnitude caiu (impacto > 0) — paga, nao constituida")
            _check(desp.sum_delta > 0 and desp.variacao_magnitude < 0,
                   "natureza despesa: sum_delta CRU (+) tem sinal OPOSTO a variacao_magnitude (-)")

        # 4. sugestao narra certo.
        sug = _sugestao_drill_cpr(receber, pagar)
        print(f"  sugestao: {sug['resumo_factual']}")
        _check("Contas a Pagar caiu" in sug["resumo_factual"],
               "sugestao.resumo_factual diz 'Contas a Pagar caiu'")

    await engine.dispose()

    print(f"\n{'='*80}")
    if _failures:
        print(f"FALHOU — {len(_failures)} assercoes:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("TODAS as assercoes passaram. CPR resumo (sinal economico) OK.")


if __name__ == "__main__":
    asyncio.run(main())
