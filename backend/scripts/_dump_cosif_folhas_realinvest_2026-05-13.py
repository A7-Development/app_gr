"""Dump das contas COSIF folha do balancete REALINVEST 2026-05-13.

Uso pontual para o levantamento do mapping COSIF -> bucket (Cota Sub
explainers refactor 2026-05-17). Roda o `compute_balancete_diario` e
imprime as folhas (nivel >= 3) com codigo, nome, natureza, D-1, D0, Δ.
"""
from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.modules.controladoria.services.balancete_diario import (
    compute_balancete_diario,
)


TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")
UA_ID     = UUID("6170ce55-b566-42ba-a3e7-5ea8dde56b64")  # REALINVEST FIDC
DATA_D0   = date(2026, 5, 13)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        bal = await compute_balancete_diario(
            db,
            tenant_id=TENANT_ID,
            fundo_id=UA_ID,
            data_d_zero=DATA_D0,
        )

        folhas = [n for n in bal.nodes if n.codigo is not None and n.nivel >= 3]
        # Inclui pendentes (nivel=0) tambem para nao perder nada
        pendentes = [n for n in bal.nodes if n.codigo is None]

        print(f"D-1: {bal.data_d_minus_1}  D0: {bal.data_d_zero}")
        print(f"Total folhas (nivel >= 3): {len(folhas)}")
        print(f"Pendentes (nivel = 0):      {len(pendentes)}")
        print()
        print("codigo | natureza | grupo | nivel | d_minus_1 | d_zero | delta | nome | cosif_source")
        print("-" * 140)

        zero = Decimal(0)
        for n in sorted(folhas, key=lambda x: x.codigo or ""):
            print(
                f"{n.codigo} | {n.natureza} | {n.grupo} | {n.nivel} | "
                f"{n.d_minus_1} | {n.d_zero} | {n.delta} | {n.nome[:60]} | {n.cosif_source}"
            )

        if pendentes:
            print()
            print("PENDENTES (sem COSIF classificado):")
            for n in pendentes:
                if n.delta != zero or n.d_zero != zero or n.d_minus_1 != zero:
                    print(
                        f"  {n.nome[:60]} | "
                        f"d1={n.d_minus_1} d0={n.d_zero} delta={n.delta}"
                    )


if __name__ == "__main__":
    asyncio.run(main())
