"""Smoke + CI guard para o detector de NAO RECONHECIDOS da Cota Sub.

Roda `scan_nao_reconhecidos` contra REALINVEST nas datas dadas e imprime os
itens que cada fonte da pagina nao soube classificar. EXIT CODE != 0 quando
ha item em modo `vaza_residuo` ou `entra_indevido` acima do threshold — isso
e a rede de seguranca: uma sigla nova da QiTech (tipo a VCNC) deixa o smoke
vermelho antes de chegar despercebida em prod.

`vigia` (informacional) nao reprova — so aparece no relatorio.

Uso:
    # default: REALINVEST 2026-05-25 (regressao do caso VCNC — deve passar)
    .venv/Scripts/python.exe scripts/smoke_cota_sub_completude.py

    # datas especificas
    .venv/Scripts/python.exe scripts/smoke_cota_sub_completude.py 2026-05-25 2026-05-26
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.cadastros.models.unidade_administrativa import UnidadeAdministrativa
from app.modules.controladoria.services.cota_sub_completude import scan_nao_reconhecidos
from app.modules.integracoes.public import dia_util_anterior_qitech

REALINVEST_NAME = "REALINVEST FIDC"
THRESHOLD = Decimal("1")


async def _run_date(db: AsyncSession, tenant_id, ua_id, ua_nome, fundo_doc, d0: date) -> bool:
    try:
        d_prev = await dia_util_anterior_qitech(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=d0)
    except ValueError as exc:
        print(f"==== {d0} ==== (pulado: {exc})\n")
        return True
    report = await scan_nao_reconhecidos(
        db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua_nome, fundo_doc=fundo_doc,
        data_d0=d0, data_d_prev=d_prev, threshold=THRESHOLD,
    )

    print(f"==== {d_prev} -> {d0} ====")
    if not report.itens:
        print("  OK — nenhum item nao reconhecido (todas as fontes 100% classificadas)")
        print()
        return True

    print(f"{'modo':<14} {'fonte':<26} {'driver':<22} {'D-1':>14} {'D0':>14}  item")
    print("-" * 110)
    for i in report.itens:
        print(
            f"{i.modo:<14} {i.fonte:<26} {i.driver_afetado:<22} "
            f"{float(i.valor_d_prev):>14,.2f} {float(i.valor_d0):>14,.2f}  {i.label}"
        )
        print(f"{'':>14}   -> {i.motivo}")
    print()
    print(f"  Σ vaza_residuo (|D0|): R$ {float(report.total_vaza_residuo_d0):,.2f}")
    print(f"  alerta (drop/false-include): {'SIM' if report.tem_alerta else 'nao (so vigia)'}")
    print()
    return not report.tem_alerta


async def _run() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL nao setada")

    args = sys.argv[1:]
    dates = [date.fromisoformat(a) for a in args] if args else [date(2026, 5, 25)]

    engine = create_async_engine(db_url, pool_pre_ping=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    all_ok = True
    async with session_maker() as db:
        ua = (
            await db.execute(
                select(UnidadeAdministrativa).where(UnidadeAdministrativa.nome == REALINVEST_NAME)
            )
        ).scalar_one_or_none()
        if not ua:
            raise SystemExit(f"UA {REALINVEST_NAME!r} nao encontrada")

        print(f"Tenant={ua.tenant_id} UA={ua.id} ({REALINVEST_NAME})\n")
        for d0 in dates:
            ok = await _run_date(db, ua.tenant_id, ua.id, ua.nome, ua.cnpj or "", d0)
            all_ok = all_ok and ok

    await engine.dispose()

    if not all_ok:
        print("FALHOU: ha itens nao reconhecidos vazando pro residuo ou entrando indevido.")
        raise SystemExit(1)
    print("OK: nenhum drop/false-include acima do threshold.")


if __name__ == "__main__":
    import contextlib

    # Windows console e cp1252 por default; motivos tem em-dash/acentos.
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    asyncio.run(_run())
