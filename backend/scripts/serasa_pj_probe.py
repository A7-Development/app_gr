"""Probe diagnostico: descobre qual variacao de path/metodo a Serasa responde.

Tenta varias combinacoes de path comuns + metodos sem disparar consulta
real (usa OPTIONS, ou POST com body deliberadamente invalido — 400/422
indica "endpoint existe mas request invalido", 404 indica "endpoint nao
existe nessa versao").

Uso:

    .venv\\Scripts\\python.exe scripts/serasa_pj_probe.py --tenant a7-credit

Para cada path testado, imprime status code + headers selecionados +
body preview. Util pra identificar:
    - 404 vazio          -> path nao existe naquele cluster (ou WAF bloqueia)
    - 400/422            -> path existe, body precisa ser ajustado
    - 401/403            -> path existe, problema de auth/permission
    - 405                -> path existe mas com outro metodo
    - 200                -> path certo (raro num probe, mas confirma)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

import httpx
from sqlalchemy import select

import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.bureau.serasa_pj.config import (
    SerasaPjConfig,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.connection import (
    build_async_client,
)
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
)
from app.shared.identity.tenant import Tenant


PATHS_TO_PROBE = [
    "/credit-services/business-information-report/v1/creditreport",
    "/credit-services/business-information-report/v1/reports",
    "/credit-services/business-information-report/v2/creditreport",
    "/credit-services/business-information-report/v2/reports",
    "/credit-services/business-report/v1/creditreport",
    "/credit-services/business-information-report/v1",
    "/credit-services/business-information-report",
    "/credit-services",
]


async def _resolve_tenant(slug_or_uuid: str) -> UUID:
    try:
        return UUID(slug_or_uuid)
    except ValueError:
        pass
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(Tenant.id).where(Tenant.slug == slug_or_uuid)
            )
        ).scalar_one_or_none()
    if row is None:
        raise SystemExit(f"tenant '{slug_or_uuid}' nao encontrado")
    return row


def _summarize(resp: httpx.Response) -> str:
    interesting_headers = {
        k: v
        for k, v in resp.headers.items()
        if k.lower()
        in {
            "content-type",
            "content-length",
            "server",
            "via",
            "x-amzn-requestid",
            "x-amzn-errortype",
            "x-amzn-trace-id",
            "x-cache",
            "www-authenticate",
            "allow",
        }
    }
    body = resp.text[:300] if resp.text else "<empty>"
    return f"  headers={interesting_headers}\n  body={body}"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument(
        "--env", choices=["production", "sandbox"], default="production"
    )
    args = parser.parse_args()

    tenant_id = await _resolve_tenant(args.tenant)
    env = Environment(args.env)

    async with AsyncSessionLocal() as db:
        cfg_row = await get_config(
            db, tenant_id, SourceType.BUREAU_SERASA_PJ, env
        )
        if cfg_row is None:
            print(
                f"[erro] sem config bureau:serasa_pj para tenant={tenant_id} env={env.value}"
            )
            return 2
        plain = decrypt_config(cfg_row.config)

    config = SerasaPjConfig.from_dict(plain)
    print(f"[probe] base_url={config.base_url}")
    print(
        f"[probe] retailer_document_id={config.retailer_document_id}"
        f" client_id={config.client_id[:10]}..."
    )
    print()

    async with build_async_client(
        tenant_id=tenant_id, environment=env, config=config
    ) as client:
        for path in PATHS_TO_PROBE:
            print(f"=== {path} ===")
            # OPTIONS — geralmente nao cobra, descobre se path existe.
            try:
                r = await client.options(path)
                print(f"  OPTIONS -> {r.status_code}")
                print(_summarize(r))
            except httpx.HTTPError as e:
                print(f"  OPTIONS -> erro de rede: {type(e).__name__}: {e}")

            # GET — alguns endpoints respondem 405 (Method Not Allowed) se
            # path existe mas exige POST. Sem custo (a Serasa nao gera
            # cobranca pra GET sem documentId).
            try:
                r = await client.get(path)
                print(f"  GET     -> {r.status_code}")
                print(_summarize(r))
            except httpx.HTTPError as e:
                print(f"  GET     -> erro de rede: {type(e).__name__}: {e}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
