"""One-shot: cifra credenciais BDC do ambiente e grava em provedor_dados_credencial.

Uso:

    set BDC_ACCESS_TOKEN=...
    set BDC_TOKEN_ID=...
    .venv\\Scripts\\python.exe scripts/seed_bdc_credential.py --alias bigdatacorp_prod

Idempotencia:
    - Se ja existir credencial com o mesmo alias, faz UPDATE (rotacao).
    - Se nao existir, INSERT.

Acessivel apenas localmente. Em prod o fluxo correto vai ser pela UI
`/admin/servicos-externos/provedores-dados/[bigdatacorp]/credenciais`
(Fase 2 do plano), que reaproveita esta mesma logica via service.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.shared.crypto.envelope import encrypt_envelope
from app.shared.data_providers.enums import DataProviderSlug
from app.shared.data_providers.models.credential import (
    DataProviderCredential,
)
from app.shared.data_providers.models.provider import DataProvider


async def _main(*, alias: str, slug: DataProviderSlug) -> int:
    access_token = os.environ.get("BDC_ACCESS_TOKEN")
    token_id = os.environ.get("BDC_TOKEN_ID")
    if not access_token or not token_id:
        print(
            "ERRO: BDC_ACCESS_TOKEN e BDC_TOKEN_ID devem estar setados no env.",
            file=sys.stderr,
        )
        return 2

    async with AsyncSessionLocal() as db:
        provider = (
            await db.execute(
                select(DataProvider).where(DataProvider.slug == slug)
            )
        ).scalar_one_or_none()
        if provider is None:
            print(
                f"ERRO: provider {slug.value!r} nao existe em provedor_dados. "
                "Rode `alembic upgrade head` antes (a migration baseline "
                "cria a row do BDC).",
                file=sys.stderr,
            )
            return 1

        envelope = encrypt_envelope(
            {"access_token": access_token, "token_id": token_id}
        )

        existing = (
            await db.execute(
                select(DataProviderCredential).where(
                    DataProviderCredential.alias == alias
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            row = DataProviderCredential(
                provider_id=provider.id,
                alias=alias,
                encrypted_payload=envelope,
                active=True,
            )
            db.add(row)
            action = "INSERT"
        else:
            existing.encrypted_payload = envelope
            existing.active = True
            existing.rotated_at = datetime.now(timezone.utc)
            row = existing
            action = "UPDATE (rotacao)"

        await db.commit()

    print(
        f"OK [{action}] credencial alias={alias!r} cifrada e salva. "
        f"id={row.id} provider={slug.value} active=True"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cifra credenciais BDC e grava em provedor_dados_credencial."
    )
    parser.add_argument(
        "--alias",
        default="bigdatacorp_prod",
        help='Alias da credencial (default: "bigdatacorp_prod").',
    )
    parser.add_argument(
        "--slug",
        default=DataProviderSlug.BIGDATACORP.value,
        choices=[s.value for s in DataProviderSlug],
        help='Slug do provider (default: "bigdatacorp").',
    )
    args = parser.parse_args()

    slug = DataProviderSlug(args.slug)
    return asyncio.run(_main(alias=args.alias, slug=slug))


if __name__ == "__main__":
    raise SystemExit(main())
