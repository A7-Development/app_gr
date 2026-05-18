"""Auto-revert do backfill_worker INTERVAL_SECONDS quando os 5 jobs market.*
enfileirados em 2026-05-17 concluirem. Script ad-hoc (nao commitado)."""
import asyncio
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

JOB_IDS = [
    "d4d2d268-5cd2-46d9-88ba-64a5c7870ed0",
    "6f44631a-10e4-4a33-bf31-a0bef357ca8e",
    "e6d5773b-f332-4c90-8511-a52037974c41",
    "ef445e78-0d73-427f-9e6f-11a9d3bf6ba1",
    "17da837f-8c84-423e-9417-d25dfff0a683",
]
LOG_FILE = Path("/var/log/auto-revert-worker.log")
WORKER_FILE = Path("/opt/app_gr/backend/app/scheduler/jobs/backfill_worker.py")
ENV_FILE = Path("/opt/app_gr/backend/.env")
POLL_SECONDS = 60


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n"
    try:
        with LOG_FILE.open("a") as f:
            f.write(line)
    except Exception:
        pass
    print(line, end="", flush=True)


def get_db_url() -> str:
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^DATABASE_URL\s*=\s*(.*)$", line)
        if not m:
            continue
        url = m.group(1).strip().strip('"').strip("'")
        url = url.replace("postgresql+asyncpg://", "postgresql://")
        url = url.replace("postgresql+psycopg2://", "postgresql://")
        url = url.replace("postgresql+psycopg://", "postgresql://")
        return url
    raise RuntimeError("DATABASE_URL nao encontrada em .env")


async def main() -> int:
    import asyncpg
    url = get_db_url()
    log(f"monitor iniciado; aguardando {len(JOB_IDS)} jobs market.* (poll={POLL_SECONDS}s)")
    iters = 0
    while True:
        try:
            conn = await asyncpg.connect(url)
            try:
                rows = await conn.fetch(
                    """
                    SELECT id::text AS id, endpoint_name, status,
                           coalesce(array_length(dates_pending, 1), 0) AS pending,
                           coalesce(array_length(dates_done, 1), 0) AS done
                    FROM backfill_job
                    WHERE id::text = ANY($1::text[])
                      AND status IN ('pending', 'running')
                    """,
                    JOB_IDS,
                )
            finally:
                await conn.close()
        except Exception as e:
            log(f"erro consultando DB: {type(e).__name__}: {e}; retry em {POLL_SECONDS}s")
            await asyncio.sleep(POLL_SECONDS)
            continue

        iters += 1
        if not rows:
            log("todos os 5 jobs market.* concluiram; revertendo worker")
            content = WORKER_FILE.read_text()
            new_content = content.replace("INTERVAL_SECONDS: int = 1", "INTERVAL_SECONDS: int = 5")
            if content == new_content:
                log("aviso: padrao 'INTERVAL_SECONDS: int = 1' nao encontrado no worker")
            else:
                WORKER_FILE.write_text(new_content)
                log("INTERVAL_SECONDS revertido para 5")
            r = subprocess.run(
                ["systemctl", "restart", "gr-api"],
                capture_output=True,
                text=True,
            )
            log(f"gr-api restart rc={r.returncode} stderr={r.stderr.strip()[:200]}")
            return 0

        if iters == 1 or iters % 10 == 0:
            tail = ", ".join(
                f"{r['endpoint_name'].replace('market.', '')}:{r['status']}:{r['pending']}p/{r['done']}d"
                for r in rows
            )
            log(f"iter {iters}: {len(rows)} ativos -> [{tail}]")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
