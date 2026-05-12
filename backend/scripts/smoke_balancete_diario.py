"""Smoke test do service balancete_diario.

Confirma que o classifier carregado do DB (com regras seedadas pela
migration ba7032c76c17) produz os mesmos numeros do spike.

Esperado para REALINVEST 07->08/05/2026:
  PL Cota Sub D0  = 11.777.225,95
  Delta PL Sub    = +36.942,77 (+0,314667%)
  Residuo         = 0,00
  Cobertura pendentes <= 1 (compensacao esperada)

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/smoke_balancete_diario.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401  (registry)
from app.core.database import AsyncSessionLocal
from app.modules.controladoria.services.balancete_diario import (
    compute_balancete_diario,
)
from sqlalchemy import text


async def main() -> int:
    async with AsyncSessionLocal() as db:
        tenant_id = await db.scalar(
            text("SELECT id FROM tenants WHERE slug = 'a7-credit'")
        )
        ua_id = await db.scalar(
            text(
                "SELECT id FROM cadastros_unidade_administrativa "
                "WHERE nome = 'REALINVEST FIDC'"
            )
        )
        if tenant_id is None or ua_id is None:
            print("Tenant/UA nao encontrados.", file=sys.stderr)
            return 1

        resp = await compute_balancete_diario(
            db,
            tenant_id=UUID(str(tenant_id)),
            fundo_id=UUID(str(ua_id)),
            data_d_zero=date(2026, 5, 8),
            data_d_minus_1=date(2026, 5, 7),
        )

        rec = resp.reconciliacao
        cob = resp.cobertura
        print("=" * 70)
        print("SMOKE balancete_diario — REALINVEST 07->08/05/2026")
        print("=" * 70)
        print(f"PL Total       D-1: {rec.pl_total_d1:>18,.2f}   D0: {rec.pl_total_d0:>18,.2f}")
        print(f"Cotas Sr (mod) D-1: {rec.cotas_sr_emitidas_d1:>18,.2f}   D0: {rec.cotas_sr_emitidas_d0:>18,.2f}")
        print(f"Cotas Mez(mod) D-1: {rec.cotas_mez_emitidas_d1:>18,.2f}   D0: {rec.cotas_mez_emitidas_d0:>18,.2f}")
        print(f"PL Cota Sub    D-1: {rec.pl_cota_sub_d1:>18,.2f}   D0: {rec.pl_cota_sub_d0:>18,.2f}")
        print(f"Delta PL Sub:       {rec.delta_pl_cota_sub_real:>18,.2f}   ({rec.delta_pct_sobre_d1:.6f}% sobre D-1)")
        print(f"Residuo:            {rec.residuo:>18,.2f}")
        print()
        print(f"Total rows D0: {cob.total_rows}")
        for src in ("override", "rule", "pendente"):
            print(f"  {src:10s}: {cob.rows_por_source.get(src, 0):4d}")
        if cob.top_pendentes:
            print("\nTop pendentes:")
            for silv, ident, val in cob.top_pendentes:
                print(f"  {silv:30s} {ident:30s} {val:>15,.2f}")

        # Asserts
        expected_pl_sub = 11_777_225.95
        actual = float(rec.pl_cota_sub_d0)
        if abs(actual - expected_pl_sub) > 0.01:
            print(f"\nFALHA: PL Sub D0 esperado={expected_pl_sub} obtido={actual}")
            return 2
        if abs(float(rec.residuo)) > 0.01:
            print(f"\nFALHA: Residuo esperado=0 obtido={rec.residuo}")
            return 3
        print("\nOK — smoke test passou.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
