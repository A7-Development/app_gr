"""Smoke test: sync de Outros Fundos contra QiTech real.

Uso (do diretorio backend/):

    .venv\\Scripts\\python.exe scripts/smoke_qitech_outros_fundos.py [aaaa-mm-dd]

Default da data: 2026-01-13 (sample conhecido com 3 posicoes REALINVEST).
Tenant: a7-credit (UUID hardcoded — primeiro e unico tenant com config
QiTech no DB de dev).

NAO use em producao. Bypass do `enabled=false`, bypass de auth de usuario.
Util pra validar que o pipeline raw->canonico funciona end-to-end com
credenciais reais antes de cabear ao endpoint REST.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from uuid import UUID

# Side-effect imports: registram tabelas referenciadas por FK no metadata
# do SQLAlchemy. Sem isso, o flush do DecisionLog (FK -> tenants) falha
# com NoReferencedTableError. O FastAPI app faz isso ao subir; script
# standalone precisa fazer manualmente.
import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.etl import sync_all
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
)

A7_CREDIT_TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")


async def main() -> int:
    data_arg = sys.argv[1] if len(sys.argv) > 1 else "2026-01-13"
    data_posicao = date.fromisoformat(data_arg)

    async with AsyncSessionLocal() as db:
        cfg_row = await get_config(
            db,
            A7_CREDIT_TENANT_ID,
            SourceType.ADMIN_QITECH,
            Environment.PRODUCTION,
        )
        if cfg_row is None:
            print("[ERRO] sem config qitech para a7-credit/production")
            return 1
        plain = decrypt_config(cfg_row.config)

    config = QiTechConfig.from_dict(plain)
    print(
        f"[smoke] base_url={config.base_url} "
        f"client_id={config.client_id[:8]}... "
        f"data_posicao={data_posicao.isoformat()}"
    )

    summary = await sync_all(
        A7_CREDIT_TENANT_ID,
        config,
        data_posicao,
        environment=Environment.PRODUCTION,
        triggered_by="smoke_test:cli",
    )

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, indent=2, default=str, ensure_ascii=False))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
