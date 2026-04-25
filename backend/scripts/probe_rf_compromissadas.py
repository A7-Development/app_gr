"""Probe rf-compromissadas dia-a-dia retroativo (Fase 0 do plano de mappers QiTech).

Loop sequencial de D-1 ate D-N (default 90 dias) procurando o primeiro dia em
que a QiTech retorna dados. Early-exit ao primeiro dia com dados — salva
sample em qitech_samples/a7-credit/<data>/rf-compromissadas.json e marca
Wave 5 do plano como ATIVA.

Se rodar todos os 90 dias sem encontrar dados, conclusao robusta de
"REALINVEST nao opera compromissadas" — descarta Wave 5.

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/probe_rf_compromissadas.py [--days 90]

Output:
    qitech_samples/_probes/probe_rf_compromissadas_<timestamp>.json
    qitech_samples/a7-credit/<data>/rf-compromissadas.json (se encontrar)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

# Side-effect imports (registry SQLAlchemy completo).
import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechHttpError
from app.modules.integracoes.adapters.admin.qitech.etl import _infer_http_status
from app.modules.integracoes.adapters.admin.qitech.reports import (
    fetch_market_report,
)
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
)

A7_CREDIT_TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")
TIPO = "rf-compromissadas"
SAMPLES_ROOT = Path(__file__).resolve().parent.parent / "qitech_samples"
PROBES_DIR = SAMPLES_ROOT / "_probes"


async def main(days: int) -> int:
    PROBES_DIR.mkdir(parents=True, exist_ok=True)
    probe_log: list[dict] = []
    found_data_on: date | None = None

    # 1. Carrega config QiTech do tenant.
    async with AsyncSessionLocal() as db:
        cfg_row = await get_config(
            db, A7_CREDIT_TENANT_ID, SourceType.ADMIN_QITECH, Environment.PRODUCTION
        )
        if cfg_row is None:
            print("[ERRO] sem config qitech para a7-credit/production")
            return 1
        plain = decrypt_config(cfg_row.config)
    config = QiTechConfig.from_dict(plain)
    print(
        f"[probe] tenant=a7-credit base_url={config.base_url} "
        f"client_id={config.client_id[:8]}... days={days}"
    )

    # 2. Loop sequencial D-1 ate D-N.
    today_utc = datetime.now(UTC).date()
    t0 = time.monotonic()

    async with build_async_client(
        tenant_id=A7_CREDIT_TENANT_ID,
        environment=Environment.PRODUCTION,
        config=config,
    ) as client:
        for offset in range(1, days + 1):
            target = today_utc - timedelta(days=offset)
            entry: dict = {
                "data": target.isoformat(),
                "offset": offset,
            }
            try:
                payload = await fetch_market_report(
                    client=client,
                    tipo_de_mercado=TIPO,
                    posicao=target,
                )
                http_status = _infer_http_status(payload, TIPO)
                entry["http_status"] = http_status
                items = (
                    payload.get("relatórios", {}).get(TIPO)
                    if isinstance(payload, dict)
                    else None
                )
                items_count = len(items) if isinstance(items, list) else 0
                entry["items_count"] = items_count

                if items_count > 0:
                    # Early exit — encontrou dados.
                    sample_dir = SAMPLES_ROOT / "a7-credit" / target.isoformat()
                    sample_dir.mkdir(parents=True, exist_ok=True)
                    sample_path = sample_dir / "rf-compromissadas.json"
                    sample_path.write_text(
                        json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    entry["sample_path"] = str(sample_path.relative_to(SAMPLES_ROOT.parent))
                    probe_log.append(entry)
                    found_data_on = target
                    print(
                        f"[probe] {target.isoformat()} HIT! items={items_count} "
                        f"-> {sample_path.relative_to(SAMPLES_ROOT.parent)}"
                    )
                    break
                else:
                    print(
                        f"[probe] {target.isoformat()} status={http_status} items=0"
                    )
            except QiTechHttpError as e:
                entry["http_status"] = e.status_code
                entry["error"] = f"HTTP {e.status_code}: {e}"
                print(f"[probe] {target.isoformat()} ERRO {e.status_code}: {e}")
            except Exception as e:
                entry["error"] = f"{type(e).__name__}: {e}"
                print(f"[probe] {target.isoformat()} EXC {type(e).__name__}: {e}")
            probe_log.append(entry)

    elapsed = time.monotonic() - t0

    # 3. Persistir log.
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = PROBES_DIR / f"probe_rf_compromissadas_{ts}.json"
    summary = {
        "tipo": TIPO,
        "tenant_id": str(A7_CREDIT_TENANT_ID),
        "days_attempted": len(probe_log),
        "max_days": days,
        "elapsed_seconds": round(elapsed, 1),
        "found_data_on": found_data_on.isoformat() if found_data_on else None,
        "wave_5_active": found_data_on is not None,
        "log": probe_log,
    }
    log_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("=" * 60)
    if found_data_on:
        print(f"WAVE 5 ATIVA — dados em {found_data_on.isoformat()}")
        print(f"Sample salvo em qitech_samples/a7-credit/{found_data_on.isoformat()}/")
    else:
        print(f"NENHUM DADO em {len(probe_log)} dias — Wave 5 descartada")
    print(f"Log: {log_path}")
    print("=" * 60)
    # Exit 0 em ambos os casos — probe e informativo, nao falha.
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.days)))
