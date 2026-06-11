"""Backfill historico do relatorio fidc-estoque (QiTech, async report).

Dispara request_fidc_estoque_report() data a data, COM PACING, e deixa o
poller do gr-api (que precisa estar rodando) baixar + mapear cada arquivo.
Nao baixa nada aqui — apenas cria os jobs no scheduler da QiTech.

Por que pacing: em 2026-06-02 um lote de 63 dispatches em rajada levou 403
em TODOS (rate-limit do /v2/queue/scheduler). Default de 75s entre datas.
Em 403, espera --cooldown (default 600s) e tenta a MESMA data 1x; segundo
403 aborta com instrucao de resume.

Cada dispatch e uma consulta paga no administrador — escolha o escopo:
    --month-ends   so a ultima data util de cada mes do range (~15 datas
                   pra 2025) — suficiente pro evolutivo mensal.
    (default)      todas as datas uteis do range (~300 pra jan/2025-mar/2026).

Pula automaticamente datas que ja tem silver populada ou job SUCCESS nas
ultimas 24h (anti-duplicate do proprio endpoint).

Uso (na VM26, de /opt/app_gr/backend):
    sudo -u app_gr .venv/bin/python scripts/backfill_fidc_estoque_report.py \
        --start 2025-01-02 --end 2026-03-31 --month-ends [--dry-run]

Args:
    --start / --end       range de reference_date (default 2025-01-02 / 2026-03-31)
    --cnpj                CNPJ do fundo (default REALINVEST 42449234000160)
    --tenant-slug         default a7-credit
    --sleep               segundos entre dispatches (default 75)
    --cooldown            segundos de espera apos 403 (default 600)
    --month-ends          so ultima data util de cada mes
    --dry-run             lista as datas que seriam disparadas, sem chamar
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import app.shared.identity  # noqa: F401,E402
import app.warehouse  # noqa: F401,E402
from sqlalchemy import select, text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.enums import Environment, SourceType  # noqa: E402
from app.modules.integracoes.adapters.admin.qitech.config import (  # noqa: E402
    QiTechConfig,
)
from app.modules.integracoes.adapters.admin.qitech.custodia import (  # noqa: E402
    resolve_ua_id_by_cnpj,
)
from app.modules.integracoes.adapters.admin.qitech.errors import (  # noqa: E402
    QiTechHttpError,
)
from app.modules.integracoes.adapters.admin.qitech.report_jobs import (  # noqa: E402
    request_fidc_estoque_report,
)
from app.modules.integracoes.services.source_config import (  # noqa: E402
    decrypt_config,
    get_config,
)

_SILVER_DATES_SQL = text(
    "SELECT DISTINCT data_referencia FROM wh_estoque_recebivel"
)
_RECENT_SUCCESS_SQL = text(
    """
    SELECT DISTINCT reference_date FROM qitech_report_job
    WHERE report_type = 'fidc-estoque' AND status = 'SUCCESS'
      AND created_at >= :cutoff
    """
)
_TENANT_SQL = text("SELECT id FROM tenants WHERE slug = :slug")


def _business_days(start: date, end: date) -> list[date]:
    out: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _month_ends(days: list[date]) -> list[date]:
    """Ultima data util de cada (ano, mes) presente na lista."""
    by_month: dict[tuple[int, int], date] = {}
    for d in days:
        key = (d.year, d.month)
        if key not in by_month or d > by_month[key]:
            by_month[key] = d
    return sorted(by_month.values())


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--cnpj", default="42449234000160")
    parser.add_argument("--tenant-slug", default="a7-credit")
    parser.add_argument("--sleep", type=float, default=75.0)
    parser.add_argument("--cooldown", type=float, default=600.0)
    parser.add_argument("--month-ends", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    days = _business_days(start, end)
    if args.month_ends:
        days = _month_ends(days)

    async with AsyncSessionLocal() as db:
        tenant_id = (
            await db.execute(_TENANT_SQL, {"slug": args.tenant_slug})
        ).scalar_one()

        have_silver = {
            row[0] for row in (await db.execute(_SILVER_DATES_SQL)).all()
        }
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        recent_ok = {
            row[0]
            for row in (
                await db.execute(_RECENT_SUCCESS_SQL, {"cutoff": cutoff})
            ).all()
        }
        targets = [d for d in days if d not in have_silver and d not in recent_ok]

        print(
            f"Range {start}..{end} | candidatas {len(days)} | "
            f"ja na silver {len([d for d in days if d in have_silver])} | "
            f"a disparar {len(targets)}"
        )
        if args.dry_run or not targets:
            for d in targets:
                print(f"  {d}")
            return

        ua_id = await resolve_ua_id_by_cnpj(
            tenant_id=tenant_id, cnpj_fundo=args.cnpj
        )
        cfg_row = await get_config(
            db,
            tenant_id,
            SourceType.ADMIN_QITECH,
            Environment.PRODUCTION,
            unidade_administrativa_id=ua_id,
        )
        if cfg_row is None and ua_id is not None:
            cfg_row = await get_config(
                db, tenant_id, SourceType.ADMIN_QITECH, Environment.PRODUCTION
            )
        if cfg_row is None:
            print(f"ERRO: sem config QiTech (ua={ua_id})")
            return
        config = QiTechConfig.from_dict(decrypt_config(cfg_row.config))

        for i, target in enumerate(targets, 1):
            attempt = 0
            while True:
                attempt += 1
                try:
                    job = await request_fidc_estoque_report(
                        db=db,
                        tenant_id=tenant_id,
                        environment=Environment.PRODUCTION,
                        config=config,
                        cnpj_fundo=args.cnpj,
                        reference_date=target,
                        triggered_by="script:backfill_fidc_estoque",
                        unidade_administrativa_id=ua_id,
                    )
                    print(
                        f"[{i}/{len(targets)}] {target}: job {job.qitech_job_id} criado",
                        flush=True,
                    )
                    break
                except QiTechHttpError as e:
                    if e.status_code == 403 and attempt == 1:
                        print(
                            f"[{i}/{len(targets)}] {target}: 403 (rate-limit?) — "
                            f"esperando {args.cooldown:.0f}s e tentando 1x",
                            flush=True,
                        )
                        await asyncio.sleep(args.cooldown)
                        continue
                    print(
                        f"ABORTADO em {target}: QiTech {e.status_code}: {e}\n"
                        f"Resume: --start {target.isoformat()}",
                        flush=True,
                    )
                    return
            if i < len(targets):
                await asyncio.sleep(args.sleep)

        print("Concluido. O poller do gr-api baixa e mapeia em background.")


if __name__ == "__main__":
    asyncio.run(main())
