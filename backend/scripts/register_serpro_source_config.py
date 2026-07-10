"""Registra a credencial SERPRO em `tenant_source_config` (cifrada, envelope).

Uso (de backend/, com .env carregando FERNET/DB do ambiente):

    .venv\\Scripts\\python.exe scripts/register_serpro_source_config.py \\
        --consumer-key <key> --consumer-secret <secret> [--plan df]

A credencial e a MESMA que o Bitfin consome (contrato A7 — decisao
2026-07-10: consumo somado). Copie Chave/Segredo do cadastro `Serpro`
(ParceiroId=5) em `dbo.OrganizacaoParceiro` do Bitfin, ou da Area do
Cliente SERPRO.

Pre-requisito: migration f2a7d4c1e8b5 aplicada (source_catalog tem a linha
DATA_SERPRO_NFE — o FK de tenant_source_config exige).

Idempotente: upsert por (tenant, source, environment, UA=NULL). A credencial
e da organizacao (nao por fundo), entao UA fica NULL de proposito.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401  (registry)
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.data.serpro.config import SerproConfig
from app.modules.integracoes.services.source_config import upsert_config

A7_CREDIT_TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer-key", required=True)
    parser.add_argument("--consumer-secret", required=True)
    parser.add_argument(
        "--plan",
        choices=("df", "escalonado"),
        default="df",
        help="plano contratado (define a base URL; 403 na consulta = plano errado)",
    )
    parser.add_argument(
        "--tenant-id",
        type=UUID,
        default=A7_CREDIT_TENANT_ID,
        help="default: a7-credit",
    )
    args = parser.parse_args()

    plain = {
        "consumer_key": args.consumer_key.strip(),
        "consumer_secret": args.consumer_secret.strip(),
        "plan": args.plan,
    }
    # Valida o shape antes de persistir (mesmo parser usado pelo client).
    config = SerproConfig.from_dict(plain)

    async with AsyncSessionLocal() as db:
        await upsert_config(
            db,
            args.tenant_id,
            SourceType.DATA_SERPRO_NFE,
            plain,
            environment=Environment.PRODUCTION,
            enabled=True,
            # Consulta on-demand, sem sync batch agendada (F0).
            sync_frequency_minutes=None,
            unidade_administrativa_id=None,
        )

    print(
        f"[ok] DATA_SERPRO_NFE registrado para tenant={args.tenant_id} "
        f"plan={args.plan} base={config.base_url}"
    )
    print("Valide com: scripts/smoke_serpro_nfe.py --prod --chave <chave real>")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
