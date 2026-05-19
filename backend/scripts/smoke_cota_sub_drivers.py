"""Smoke E2E para `compute_drivers` (Fase 4b — 2026-05-18).

Roda `compute_drivers` contra REALINVEST e imprime, por driver, valor_brl +
quantas evidencias de cada tipo o driver populou. Aceita uma ou mais datas
D0 via CLI (D-1 = dia anterior pelo calendar do dia, podendo passar
explicito --d1).

Confirma que:
  - Os 5 tipos de evidencia (PDD, MtM, CPR, Remuneracao, Mov Carteira)
    populam apenas no driver certo (sem leakage)
  - Drivers Sr/Mez (Fase 3c-A) refletem APENAS rendimento (cash flow
    subtraido) — comparar dia sem aporte vs dia com aporte.

Uso:
    # default: REALINVEST 13/05 (controle, sem cash flow)
    .venv/Scripts/python.exe scripts/smoke_cota_sub_drivers.py

    # uma data especifica
    .venv/Scripts/python.exe scripts/smoke_cota_sub_drivers.py 2026-05-06

    # multiplas datas
    .venv/Scripts/python.exe scripts/smoke_cota_sub_drivers.py 2026-05-06 2026-05-13
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.cadastros.models.unidade_administrativa import UnidadeAdministrativa
from app.modules.controladoria.services.cota_sub_drivers import compute_drivers


REALINVEST_NAME = "REALINVEST FIDC"


async def _run_date(db: AsyncSession, tenant_id, ua_id, d0: date) -> None:
    d_prev = d0 - timedelta(days=1)
    # Pular finais de semana / sem dado D-1: cai pro dia util anterior empiricamente.
    # Simplificacao: tenta D-1, D-2, D-3 ate achar.
    result = None
    used_d_prev = None
    for offset in (1, 2, 3, 4):
        try:
            d_try = d0 - timedelta(days=offset)
            r = await compute_drivers(
                db, tenant_id=tenant_id, ua_id=ua_id, data_d0=d0, data_d_prev=d_try,
            )
            if r.pl_sub_d_prev != 0:
                result = r
                used_d_prev = d_try
                break
        except Exception:
            continue
    if result is None:
        # Fallback: deixa compute_drivers resolver d_prev sozinho.
        result = await compute_drivers(
            db, tenant_id=tenant_id, ua_id=ua_id, data_d0=d0, data_d_prev=None,
        )
        used_d_prev = result.data_d_prev

    print(f"==== {used_d_prev} -> {d0} ====")
    print(f"PL Sub D-1: R$ {result.pl_sub_d_prev:>20,.2f}")
    print(f"PL Sub D0:  R$ {result.pl_sub_d0:>20,.2f}")
    print(f"dPL Sub:    R$ {result.pl_sub_delta:>20,.2f}")
    print(f"Soma drv:   R$ {result.soma_drivers:>20,.2f}")
    print(f"Residuo:    R$ {result.residuo:>20,.2f}")
    print()
    print(f"{'Driver':<28} {'valor_brl':>16}  PDD MtM CPR Rmn MvC ApD STe  Indt")
    print("-" * 88)
    for d in result.drivers:
        flags = (
            f" {len(d.pdd_evidencias):>3d}"
            f" {len(d.mtm_evidencias):>3d}"
            f" {len(d.cpr_evidencias):>3d}"
            f" {len(d.remuneracao_evidencias):>3d}"
            f" {len(d.movimento_carteira_evidencias):>3d}"
            f" {len(d.apropriacao_dc_evidencias):>3d}"
            f" {len(d.saldo_tesouraria_evidencias):>3d}"
        )
        indt = " IND" if d.indeterminado_por_dado else "   ."
        print(f"{d.label:<28} {float(d.valor_brl):>16,.2f} {flags}  {indt}")

        if d.evidencias_indisponiveis_motivo:
            print(f"    motivo: {d.evidencias_indisponiveis_motivo}")

        # Verifica Sum evidencias dos novos campos = valor_brl
        if d.apropriacao_dc_evidencias:
            soma = sum(float(e.valor_brl) for e in d.apropriacao_dc_evidencias)
            diff = soma - float(d.valor_brl)
            marker = "OK" if abs(diff) < 0.01 else f"FAIL diff={diff:+.2f}"
            print(f"    sum apropriacao_dc_evidencias = {soma:>16,.2f} [{marker}]")
        if d.saldo_tesouraria_evidencias:
            soma = sum(float(e.delta) for e in d.saldo_tesouraria_evidencias)
            diff = soma - float(d.valor_brl)
            marker = "OK" if abs(diff) < 0.01 else f"FAIL diff={diff:+.2f}"
            print(f"    sum saldo_tesouraria_evidencias = {soma:>14,.2f} [{marker}]")
    print()


async def _run() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL nao setada")

    args = sys.argv[1:]
    if args:
        dates = [date.fromisoformat(a) for a in args]
    else:
        dates = [date(2026, 5, 13)]

    engine = create_async_engine(db_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as db:
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

        print(f"Tenant={tenant_id} UA={ua_id} ({REALINVEST_NAME})\n")

        for d0 in dates:
            await _run_date(db, tenant_id, ua_id, d0)

        print("Legenda: PDD=pdd_evidencias, MtM=mtm_evidencias,")
        print("         CPR=cpr_evidencias, Rmn=remuneracao_evidencias,")
        print("         MvC=movimento_carteira_evidencias, IND=indeterminado_por_dado")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
