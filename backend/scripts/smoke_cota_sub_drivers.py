"""Smoke E2E para `compute_drivers` (Fase 4b — 2026-05-18).

Roda `compute_drivers` contra REALINVEST 12/05 → 13/05 e imprime quantos
itens cada campo de evidencia recebeu por driver. Confirma que os 5 tipos
de evidencia (PDD, MtM, CPR, Remuneracao Sr/Mez, Movimento Carteira)
estao sendo populados pelos compute_fns certos.

Uso:
    .venv/Scripts/python.exe scripts/smoke_cota_sub_drivers.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.cadastros.models.unidade_administrativa import UnidadeAdministrativa
from app.modules.controladoria.services.cota_sub_drivers import compute_drivers


REALINVEST_NAME = "REALINVEST FIDC"
D0 = date(2026, 5, 13)
D1 = date(2026, 5, 12)


async def _run() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL nao setada")

    engine = create_async_engine(db_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as db:
        # Find REALINVEST UA + tenant
        ua = (
            await db.execute(
                select(UnidadeAdministrativa).where(
                    UnidadeAdministrativa.nome == REALINVEST_NAME
                )
            )
        ).scalar_one_or_none()
        if not ua:
            raise SystemExit(f"UA {REALINVEST_NAME!r} nao encontrada")
        tenant_id = ua.tenant_id
        ua_id = ua.id

        print(f"Rodando compute_drivers para {REALINVEST_NAME} D-1={D1} D0={D0}")
        print(f"  tenant_id={tenant_id}  ua_id={ua_id}\n")

        result = await compute_drivers(
            db, tenant_id=tenant_id, ua_id=ua_id, data_d0=D0, data_d_prev=D1,
        )

        print(f"PL Sub D-1: R$ {result.pl_sub_d_prev:>20,.2f}")
        print(f"PL Sub D0:  R$ {result.pl_sub_d0:>20,.2f}")
        print(f"dPL Sub:    R$ {result.pl_sub_delta:>20,.2f}")
        print(f"Soma drivers:  R$ {result.soma_drivers:>20,.2f}")
        print(f"Residuo:    R$ {result.residuo:>20,.2f}\n")

        print(f"{'Driver':<35} {'valor_brl':>18}  PDD MtM CPR Rmn MvC  Indt")
        print("-" * 90)
        for d in result.drivers:
            flags = (
                f" {len(d.pdd_evidencias):>3d}"
                f" {len(d.mtm_evidencias):>3d}"
                f" {len(d.cpr_evidencias):>3d}"
                f" {len(d.remuneracao_evidencias):>3d}"
                f" {len(d.movimento_carteira_evidencias):>3d}"
            )
            indt = " IND" if d.indeterminado_por_dado else "   ."
            print(f"{d.label:<35} {float(d.valor_brl):>18,.2f} {flags}  {indt}")

        print("\nLegenda: PDD=pdd_evidencias, MtM=mtm_evidencias,")
        print("         CPR=cpr_evidencias, Rmn=remuneracao_evidencias,")
        print("         MvC=movimento_carteira_evidencias, IND=indeterminado_por_dado")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
