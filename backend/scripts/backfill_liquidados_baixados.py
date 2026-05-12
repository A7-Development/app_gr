"""Backfill liquidados-baixados QiTech REALINVEST FIDC — janela arbitraria.

Itera em chunks de N dias (default 7) chamando `sync_liquidados_baixados`
por chunk. Cada chunk e 1 GET ao QiTech com periodo no path; upsert por
`source_id` em `wh_liquidacao_recebivel` deduplica chunks sobrepostos.

Por que chunks: o httpx client do adapter tem timeout default de 30s
(`connection.py::_DEFAULT_TIMEOUT`); janelas de 30 dias estouram. Chunks
de 7 dias rodam em ~10s cada (medido). Trocar o timeout em prod nao vale
o risco — chunks resolvem do lado do script.

Origem 2026-05-12: precisamos popular abril/2026 inteiro pra analisar
forense o ajuste negativo grande de 2026-04-13 (incidente operacional).

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/backfill_liquidados_baixados.py
    .venv\\Scripts\\python.exe scripts/backfill_liquidados_baixados.py 2026-04-01 2026-04-30
    .venv\\Scripts\\python.exe scripts/backfill_liquidados_baixados.py 2026-04-01 2026-04-30 14
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import text

# Side-effect imports (registry SQLAlchemy completo).
import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.custodia import (
    sync_liquidados_baixados,
)
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
)

# REALINVEST FIDC — CNPJ digits-only (normalizado pelo adapter de qualquer forma).
CNPJ_REALINVEST = "42449234000160"
DEFAULT_START = date(2026, 4, 1)
DEFAULT_END = date(2026, 4, 30)
DEFAULT_CHUNK_DAYS = 7  # 7 dias roda em ~10s; 30 dias estoura timeout de 30s


def _chunks(start: date, end: date, days: int) -> list[tuple[date, date]]:
    """Quebra [start..end] em janelas inclusivas de `days` dias."""
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=days - 1), end)
        out.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return out


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
                "WHERE cnpj = :cnpj AND tenant_id = :tid"
            ),
            {"tid": tenant_id, "cnpj": CNPJ_REALINVEST},
        )
        if not ua_id:
            raise RuntimeError("UA REALINVEST FIDC nao encontrada")
    return tenant_id, ua_id


async def _load_config(tenant_id: UUID, ua_id: UUID) -> QiTechConfig:
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
    chunk_days = int(sys.argv[3]) if len(sys.argv) >= 4 else DEFAULT_CHUNK_DAYS

    tenant_id, ua_id = await _resolve_ids()
    config = await _load_config(tenant_id, ua_id)

    chunks = _chunks(start, end, chunk_days)

    print(
        f"[info] tenant=a7-credit ua=REALINVEST FIDC ({CNPJ_REALINVEST})"
    )
    print(
        f"[info] janela: {start.isoformat()} -> {end.isoformat()} "
        f"({(end - start).days + 1} dias) em {len(chunks)} chunks de ate {chunk_days} dias"
    )
    print()
    print(
        f"{'#':>3} {'INICIAL':<12} {'FINAL':<12} {'OK':<5} {'ROWS':>7} {'TIME':>7}  {'ERROS':<40}"
    )
    print("-" * 80)

    total_rows = 0
    total_errors = 0
    failed_chunks: list[tuple[date, date, list[str]]] = []

    for i, (di, df) in enumerate(chunks, start=1):
        try:
            step = await sync_liquidados_baixados(
                tenant_id=tenant_id,
                environment=Environment.PRODUCTION,
                config=config,
                cnpj_fundo=CNPJ_REALINVEST,
                data_inicial=di,
                data_final=df,
                unidade_administrativa_id=ua_id,
            )
        except Exception as e:
            print(
                f"{i:>3} {di.isoformat():<12} {df.isoformat():<12} "
                f"{'CRASH':<5} {'-':>7} {'-':>7}  {type(e).__name__}: {e}"
            )
            failed_chunks.append((di, df, [f"crash: {type(e).__name__}: {e}"]))
            total_errors += 1
            continue

        ok = step.get("ok")
        rows = int(step.get("canonical_rows_upserted") or 0)
        elapsed = step.get("elapsed_seconds", 0.0)
        errs = step.get("errors") or []

        total_rows += rows
        if errs:
            total_errors += len(errs)
            failed_chunks.append((di, df, errs))

        err_summary = ""
        if errs:
            err_summary = f"{len(errs)} erro(s) — 1o: {errs[0][:60]}"

        print(
            f"{i:>3} {di.isoformat():<12} {df.isoformat():<12} "
            f"{('OK' if ok else 'ERR'):<5} "
            f"{rows:>7} "
            f"{elapsed:>6.1f}s  "
            f"{err_summary:<40}"
        )

    print()
    print("=" * 80)
    print(f"  total chunks            : {len(chunks)}")
    print(f"  total rows upserted     : {total_rows}")
    print(f"  total errors            : {total_errors}")
    if failed_chunks:
        print(f"  failed chunks ({len(failed_chunks)}):")
        for di, df, errs in failed_chunks:
            print(f"    - {di.isoformat()}..{df.isoformat()}: {errs[0][:80]}")
    print("=" * 80)

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
