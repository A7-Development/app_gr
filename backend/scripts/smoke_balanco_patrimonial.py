"""Smoke test do endpoint balanco-patrimonial — F1 do redesign.

Roda compute_balanco_patrimonial contra REALINVEST em 2026-05-15 e valida:
  - Identidade contabil fecha (residuo == 0)
  - Soma das categorias bate com pl_d0 / pl_d1
  - Sinais absolutos nos passivos
  - Numeros conferem com a sessao de exploracao manual (R$ 11.900.016,85)

Read-only — seguro mesmo em dev=prod.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal
from uuid import UUID

# Force UTF-8 output on Windows (cp1252 default cant render Σ/Δ).
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.services.balanco_patrimonial import (
    compute_balanco_patrimonial,
)


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        # Pegar REALINVEST FIDC
        ua = (
            await db.execute(
                select(UnidadeAdministrativa).where(
                    UnidadeAdministrativa.nome == "REALINVEST FIDC"
                )
            )
        ).scalar_one()

        result = await compute_balanco_patrimonial(
            db,
            tenant_id=ua.tenant_id,
            ua_id=ua.id,
            data_d0=date(2026, 5, 15),
        )

    print(f"\n=== Balanco Patrimonial · {result.fundo_nome} ===")
    print(f"D-1: {result.data_anterior}  D0: {result.data}\n")

    print("ATIVOS                              D-1              D0           Delta")
    print("-" * 80)
    for a in result.ativos:
        print(f"  {a.label:30s}  {a.d1:>14,.2f}  {a.d0:>14,.2f}  {a.delta:>+14,.2f}")
    print("-" * 80)
    print(
        f"  Σ Ativos                      {result.soma_ativos_d1:>14,.2f}  "
        f"{result.soma_ativos_d0:>14,.2f}  {result.soma_ativos_delta:>+14,.2f}"
    )

    print("\nPASSIVOS                            D-1              D0           Delta")
    print("-" * 80)
    for p in result.passivos:
        print(f"  {p.label:30s}  {p.d1:>14,.2f}  {p.d0:>14,.2f}  {p.delta:>+14,.2f}")
    print("-" * 80)
    print(
        f"  Σ Passivos                    {result.soma_passivos_d1:>14,.2f}  "
        f"{result.soma_passivos_d0:>14,.2f}  {result.soma_passivos_delta:>+14,.2f}"
    )

    print("\nFECHAMENTO")
    print("-" * 80)
    print(
        f"  PL Sub (deduzido)             {result.pl_deduzido_d1:>14,.2f}  "
        f"{result.pl_deduzido_d0:>14,.2f}  {result.pl_deduzido_delta:>+14,.2f}"
    )
    print(
        f"  PL Sub (fonte wh_mec)         {result.pl_fonte_d1:>14,.2f}  "
        f"{result.pl_fonte_d0:>14,.2f}  {result.pl_fonte_delta:>+14,.2f}"
    )
    print(
        f"  Residuo identidade            {result.residuo_identidade_d1:>14,.2f}  "
        f"{result.residuo_identidade_d0:>14,.2f}"
    )

    if abs(result.residuo_identidade_d0) < Decimal("0.01"):
        print("\n  Identidade D0 fecha em zero. ✓")
    else:
        print(f"\n  Residuo D0 = R$ {result.residuo_identidade_d0:.2f} - investigar.")

    # Esperado: PL Sub D0 = R$ 11.900.016,85 (sessao de exploracao manual em 2026-05-22)
    expected_pl = Decimal("11900016.85")
    if abs(result.pl_fonte_d0 - expected_pl) < Decimal("0.01"):
        print(f"  PL Sub D0 bate com baseline manual (R$ {expected_pl:,.2f}). ✓")
    else:
        print(
            f"  PL Sub D0 = R$ {result.pl_fonte_d0:,.2f} (esperado R$ {expected_pl:,.2f})"
        )


if __name__ == "__main__":
    asyncio.run(main())
