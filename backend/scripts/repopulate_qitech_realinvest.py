"""Repopula dados QiTech do tenant a7-credit / UA REALINVEST FIDC.

Loopa por um intervalo de datas chamando `sync_all` para cada uma. Cada
execucao cobre os 10 endpoints `/netreport/report/market/*` registrados
em `_PIPELINE` (etl.py): outros-fundos, conta-corrente, tesouraria,
outros-ativos, demonstrativo-caixa, cpr, mec, rentabilidade, rf,
rf-compromissadas.

NAO inclui `wh_estoque_recebivel` — esse vem por callback assincrono
(/v2/queue/scheduler/report/fidc-estoque) que ainda nao esta resolvido.

Cada `sync_all` ja:
- captura erros por endpoint (nao para a execucao)
- gravando 1 entry em `decision_log` por execucao (audit trail)
- e idempotente (UQ tenant_id+source_id): re-rodar a mesma data
  atualiza payloads sem duplicar linhas

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/repopulate_qitech_realinvest.py
    .venv\\Scripts\\python.exe scripts/repopulate_qitech_realinvest.py 2026-03-01 2026-04-26
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from uuid import UUID

# Side-effect imports (registry SQLAlchemy completo).
import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.etl import sync_all
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
)
from sqlalchemy import text

DEFAULT_START = date(2026, 3, 1)
DEFAULT_END = date(2026, 4, 26)  # D-1 quando rodando em 2026-04-27


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


async def _resolve_ids() -> tuple[UUID, UUID]:
    async with AsyncSessionLocal() as db:
        tenant_id = await db.scalar(
            text("SELECT id FROM tenants WHERE slug = 'a7-credit'")
        )
        if not tenant_id:
            raise RuntimeError("tenant a7-credit nao encontrado")
        ua_id = await db.scalar(
            text(
                "SELECT id FROM cadastros_unidade_administrativa "
                "WHERE cnpj = '42449234000160' AND tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
        if not ua_id:
            raise RuntimeError("UA REALINVEST FIDC nao encontrada")
    return tenant_id, ua_id


async def _load_config(
    tenant_id: UUID, ua_id: UUID
) -> QiTechConfig:
    async with AsyncSessionLocal() as db:
        cfg_row = await get_config(
            db,
            tenant_id,
            SourceType.ADMIN_QITECH,
            Environment.PRODUCTION,
            unidade_administrativa_id=ua_id,
        )
        if cfg_row is None:
            raise RuntimeError(
                "tenant_source_config QiTech/PRODUCTION/REALINVEST nao encontrado"
            )
        plain = decrypt_config(cfg_row.config)
    return QiTechConfig.from_dict(plain)


async def main() -> int:
    if len(sys.argv) >= 3:
        start = date.fromisoformat(sys.argv[1])
        end = date.fromisoformat(sys.argv[2])
    else:
        start = DEFAULT_START
        end = DEFAULT_END

    tenant_id, ua_id = await _resolve_ids()
    config = await _load_config(tenant_id, ua_id)
    dates = list(_daterange(start, end))
    print(
        f"[info] tenant=a7-credit ua=REALINVEST FIDC "
        f"datas={start.isoformat()}..{end.isoformat()} (n={len(dates)})"
    )
    print(
        f"[info] cada data executa 10 endpoints (estoque NAO incluso — webhook pendente)"
    )
    print()

    print(
        f"{'#':>3} {'DATA':<12} {'OK':<5} {'ROWS':>7} {'TIME':>7}  {'ERROS':<40}"
    )
    print("-" * 80)

    total_rows = 0
    total_errors = 0
    failures: list[tuple[date, list[str]]] = []

    for i, d in enumerate(dates, start=1):
        try:
            summary = await sync_all(
                tenant_id,
                config,
                since=d,
                environment=Environment.PRODUCTION,
                triggered_by="manual:repopulate_qitech_realinvest",
                unidade_administrativa_id=ua_id,
            )
        except Exception as e:
            print(f"{i:>3} {d.isoformat():<12} {'CRASH':<5} {'-':>7} {'-':>7}  {type(e).__name__}: {e}")
            failures.append((d, [f"crash: {type(e).__name__}: {e}"]))
            total_errors += 1
            continue

        ok = summary["ok"]
        rows = int(summary.get("rows_ingested") or 0)
        elapsed = summary.get("elapsed_seconds", 0.0)
        errs = summary.get("errors") or []

        total_rows += rows
        if errs:
            total_errors += len(errs)
            failures.append((d, errs))

        err_summary = ""
        if errs:
            err_summary = f"{len(errs)} erro(s) — 1o: {errs[0][:80]}"

        print(
            f"{i:>3} {d.isoformat():<12} "
            f"{('OK' if ok else 'ERR'):<5} "
            f"{rows:>7} "
            f"{elapsed:>6.1f}s  "
            f"{err_summary:<40}"
        )

    print()
    print("=" * 80)
    print(
        f"SUMARIO: {len(dates)} datas · {total_rows} linhas inseridas · "
        f"{total_errors} erro(s)"
    )

    if failures:
        print()
        print(f"DATAS COM ERRO ({len(failures)}):")
        for d, errs in failures:
            print(f"  {d.isoformat()}: {len(errs)} erro(s)")
            for e in errs[:3]:
                print(f"    - {e[:120]}")
            if len(errs) > 3:
                print(f"    ... e mais {len(errs) - 3}")

    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
