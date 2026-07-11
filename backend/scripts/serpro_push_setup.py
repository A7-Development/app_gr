"""Setup do Push NF-e do SERPRO -- cadastra a urlNotificacao do contrato.

ATENCAO: a URL de notificacao e UNICA POR CONTRATO SERPRO, e o contrato e
compartilhado com o Bitfin (que hoje NAO usa push — validado 2026-07-10:
sem urlNotificacao consumida la). Cadastrar a nossa URL nao muda nada no
fluxo do Bitfin, mas e mutacao de estado no contrato — rodar com aval.

Uso (de backend/, com .env):

    .venv\\Scripts\\python.exe scripts/serpro_push_setup.py            # consulta
    .venv\\Scripts\\python.exe scripts/serpro_push_setup.py --register # cadastra/atualiza

O token embutido na URL e derivado de SERPRO_WEBHOOK_SECRET (fallback:
QITECH_WEBHOOK_SECRET com salt proprio) — precisa do .env de producao.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401  (registry)
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.data.serpro.client import SerproClient
from app.modules.integracoes.adapters.data.serpro.errors import SerproError
from app.modules.integracoes.adapters.data.serpro.monitoring import (
    build_client_config,
    build_notification_url,
)

A7_CREDIT_TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--register",
        action="store_true",
        help="cadastra (ou atualiza) a urlNotificacao no contrato SERPRO",
    )
    parser.add_argument("--tenant-id", type=UUID, default=A7_CREDIT_TENANT_ID)
    args = parser.parse_args()

    url = build_notification_url()
    print(f"[setup] urlNotificacao alvo: {url}")

    async with AsyncSessionLocal() as db:
        config = await build_client_config(db, args.tenant_id)

    async with SerproClient(config=config) as client:
        try:
            atual = await client.push_consultar_cliente()
            print(f"[setup] cadastro atual no SERPRO: {atual}")
        except SerproError as e:
            atual = None
            print(f"[setup] sem cadastro atual ({type(e).__name__}: {e})")

        if not args.register:
            print("[setup] dry-run — use --register para cadastrar/atualizar.")
            return 0

        if atual and atual.get("urlNotificacao"):
            resp = await client.push_atualizar_cliente(url)
            print(f"[setup] URL ATUALIZADA: {resp}")
        else:
            resp = await client.push_cadastrar_cliente(url)
            print(f"[setup] URL CADASTRADA: {resp}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
