"""Probe descoberta da familia /queue/scheduler/report/ (assincrono).

Objetivo: descobrir o schema concreto que a QiTech retorna nas 3 fases:
1. POST /v2/queue/scheduler/report/fidc-estoque  -> response inicial
2. GET /v2/queue/job?reportType=fidc-estoque    -> lista de jobs
3. (manual via webhook.site) callback           -> payload com link/arquivo

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/probe_fidc_estoque.py \\
        --callback https://webhook.site/<uuid> \\
        --cnpj 42449234000160 \\
        --date 2026-01-08

Apenas dispara + lista. Nao processa o callback (precisa do user
colar o payload do webhook.site pra desenhar o adapter completo).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

import httpx

import app.shared.identity.tenant  # noqa: F401  (registry)
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
)

A7_CREDIT_TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")


async def main(callback_url: str, cnpj_fundo: str, ref_date: str) -> int:
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
    print(f"[probe] base_url={config.base_url}")
    print(f"[probe] callback_url={callback_url}")
    print(f"[probe] cnpj_fundo={cnpj_fundo} date={ref_date}")
    print()

    async with build_async_client(
        tenant_id=A7_CREDIT_TENANT_ID,
        environment=Environment.PRODUCTION,
        config=config,
    ) as client:
        # 1. POST -- cria job
        body = {
            "callbackUrl": callback_url,
            "cnpjFundo": cnpj_fundo,
            "date": ref_date,
        }
        print("=" * 70)
        print("[1/3] POST /v2/queue/scheduler/report/fidc-estoque")
        print("=" * 70)
        print(f"body: {json.dumps(body, indent=2)}")
        try:
            resp = await client.post(
                "/v2/queue/scheduler/report/fidc-estoque", json=body
            )
            print(f"status={resp.status_code}")
            print("headers (selecionados):")
            for k in ("content-type", "x-request-id", "date"):
                if k in resp.headers:
                    print(f"  {k}: {resp.headers[k]}")
            try:
                post_body = resp.json()
                print("response body:")
                print(json.dumps(post_body, indent=2, ensure_ascii=False))
                job_id = post_body.get("jobId")
            except ValueError:
                print(f"response (nao-JSON): {resp.text[:500]}")
                return 2
        except httpx.HTTPError as e:
            print(f"erro HTTP: {type(e).__name__}: {e}")
            return 2

        if not job_id:
            print("[ERRO] response sem jobId — abortando")
            return 2

        print()
        print("[2/3] aguardando 5s antes do GET...")
        await asyncio.sleep(5)

        # 2. GET -- lista jobs
        print("=" * 70)
        print("[2/3] GET /v2/queue/job?reportType=fidc-estoque&page=0&limit=10")
        print("=" * 70)
        try:
            resp = await client.get(
                "/v2/queue/job",
                params={"reportType": "fidc-estoque", "page": 0, "limit": 10},
            )
            print(f"status={resp.status_code}")
            try:
                get_body = resp.json()
                print("response body:")
                print(json.dumps(get_body, indent=2, ensure_ascii=False))
                # Procurar nosso jobId na lista (pode ser que apareca como taskId)
                jobs = get_body.get("jobs") or []
                ours = [
                    j for j in jobs
                    if (j.get("taskId") == job_id or j.get("jobId") == job_id)
                ]
                if ours:
                    print()
                    print(f"NOSSO JOB encontrado: status={ours[0].get('status')}")
                else:
                    print()
                    print(f"NOSSO JOB ({job_id}) nao apareceu na lista ainda")
            except ValueError:
                print(f"response (nao-JSON): {resp.text[:500]}")
        except httpx.HTTPError as e:
            print(f"erro HTTP: {type(e).__name__}: {e}")

        # 3. Tentar GET no detalhe (existe?)
        print()
        print("=" * 70)
        print(f"[3/3] tentativa GET /v2/queue/job/{job_id}")
        print("=" * 70)
        try:
            resp = await client.get(f"/v2/queue/job/{job_id}")
            print(f"status={resp.status_code}")
            if resp.status_code < 400:
                try:
                    detail = resp.json()
                    print("response body:")
                    print(json.dumps(detail, indent=2, ensure_ascii=False))
                except ValueError:
                    print(f"response (nao-JSON): {resp.text[:500]}")
            else:
                print("endpoint detalhe nao existe ou nao acessivel")
                print(f"response: {resp.text[:300]}")
        except httpx.HTTPError as e:
            print(f"erro HTTP: {type(e).__name__}: {e}")

    print()
    print("=" * 70)
    print("PROBE CONCLUIDA")
    print("=" * 70)
    print(f"job_id criado: {job_id}")
    print(f"aguarde alguns minutos e olhe {callback_url}")
    print("qdo o callback chegar, cole o headers+body completos pro Claude")
    print("depois rode novamente este script com o mesmo callback pra ver")
    print("como o status muda de WAITING -> SUCCESS na lista de jobs.")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--callback",
        default="https://webhook.site/5d37be20-ffdb-4e51-b6ce-c54bacf7d320",
        help="URL do webhook.site pra receber o callback",
    )
    parser.add_argument("--cnpj", default="42449234000160")
    parser.add_argument("--date", default="2026-01-08")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.callback, args.cnpj, args.date)))
