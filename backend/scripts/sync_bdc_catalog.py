"""Roda um sync de catalogo BDC manualmente.

Uso tipico (1a execucao):

    .venv\\Scripts\\python.exe scripts/sync_bdc_catalog.py --save-payload bdc-precos.json

O `--save-payload` dumpa a resposta crua de POST /precos/ pra arquivo
ANTES do parse — util pra inspecionar shape e ajustar
`pricing_sync._parse_pricing_payload` se o BDC devolver formato fora dos 3
shapes ja suportados.

Em runs subsequentes, omita o flag (sync_run vira sucesso e os contadores
sao impressos).

Pre-requisitos:
    1. `alembic upgrade head` rodou (cria as 5 tabelas + seed BDC).
    2. `seed_bdc_credential.py` rodou (cifra+grava credencial).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.data.bigdatacorp.etl import (
    sync_catalog_for_provider,
)
from app.shared.data_providers.enums import (
    CatalogSyncStatus,
    DataProviderSlug,
)
from app.shared.data_providers.models.provider import DataProvider


async def _resolve_provider_id(slug: DataProviderSlug) -> UUID:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(DataProvider.id).where(DataProvider.slug == slug)
            )
        ).scalar_one_or_none()
    if row is None:
        raise SystemExit(
            f"Provider {slug.value!r} nao existe em provedor_dados. "
            "Rode `alembic upgrade head` antes."
        )
    return row


async def _main(
    *,
    slug: DataProviderSlug,
    save_payload: str | None,
    triggered_by: str,
) -> int:
    provider_id = await _resolve_provider_id(slug)

    async with AsyncSessionLocal() as db:
        report = await sync_catalog_for_provider(
            db=db,
            provider_id=provider_id,
            triggered_by=triggered_by,
            save_payload_to=save_payload,
        )

    print("=" * 60)
    print(f"Sync {slug.value!r} provider_id={provider_id}")
    print(f"  sync_run_id : {report.sync_run_id}")
    print(f"  status      : {report.status.value}")
    if report.latency_ms is not None:
        print(f"  latency     : {report.latency_ms:.1f} ms")
    if report.pricing_payload_keys is not None:
        print(f"  payload top : {report.pricing_payload_keys}")

    if report.status is CatalogSyncStatus.OK and report.counters is not None:
        c = report.counters
        print(
            f"  datasets    : +{c.added} added  ~{c.updated} updated  "
            f"={c.unchanged} unchanged  -{c.removed} removed"
        )
        print("=" * 60)
        return 0

    if report.error_message:
        print(f"  ERRO        : {report.error_message}", file=sys.stderr)
    print("=" * 60)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync de catalogo do provedor de dados (Fase 1)."
    )
    parser.add_argument(
        "--slug",
        default=DataProviderSlug.BIGDATACORP.value,
        choices=[s.value for s in DataProviderSlug],
        help='Slug do provider (default: "bigdatacorp").',
    )
    parser.add_argument(
        "--save-payload",
        default=None,
        metavar="PATH",
        help=(
            "Se fornecido, dumpa a resposta crua de /precos/ "
            "pra esse arquivo antes do parse (debug)."
        ),
    )
    parser.add_argument(
        "--triggered-by",
        default="manual",
        help='Texto livre gravado em sync_run.triggered_by (default: "manual").',
    )
    args = parser.parse_args()

    return asyncio.run(
        _main(
            slug=DataProviderSlug(args.slug),
            save_payload=args.save_payload,
            triggered_by=args.triggered_by,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
