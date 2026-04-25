"""Smoke real dos 3 endpoints sincronos /v2/fidc-custodia/report/* contra
a QiTech. Usa tenant a7-credit + REALINVEST FIDC.

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/smoke_fidc_custodia.py \\
        [--di 2026-01-01] [--df 2026-01-08]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401  (registry)
from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.custodia import (
    get_qitech_config_for_tenant,
    sync_aquisicao_consolidada,
    sync_detalhes_operacoes,
    sync_liquidados_baixados,
)

A7 = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")
CNPJ = "42449234000160"


async def main(di: date, df: date) -> int:
    config = await get_qitech_config_for_tenant(
        tenant_id=A7, environment=Environment.PRODUCTION
    )
    if config is None:
        print("[ERRO] sem config qitech a7-credit")
        return 1

    print(f"[smoke] cnpj={CNPJ} periodo={di}..{df}")
    print()

    print("=" * 70)
    print("1. aquisicao-consolidada")
    print("=" * 70)
    s1 = await sync_aquisicao_consolidada(
        tenant_id=A7,
        environment=Environment.PRODUCTION,
        config=config,
        cnpj_fundo=CNPJ,
        data_inicial=di,
        data_final=df,
    )
    print(json.dumps(s1, indent=2, ensure_ascii=False))
    print()

    print("=" * 70)
    print("2. liquidados-baixados/v2")
    print("=" * 70)
    s2 = await sync_liquidados_baixados(
        tenant_id=A7,
        environment=Environment.PRODUCTION,
        config=config,
        cnpj_fundo=CNPJ,
        data_inicial=di,
        data_final=df,
    )
    print(json.dumps(s2, indent=2, ensure_ascii=False))
    print()

    print("=" * 70)
    print(f"3. detalhes-operacoes (data={df})")
    print("=" * 70)
    s3 = await sync_detalhes_operacoes(
        tenant_id=A7,
        environment=Environment.PRODUCTION,
        config=config,
        cnpj_fundo=CNPJ,
        data_importacao=df,
    )
    print(json.dumps(s3, indent=2, ensure_ascii=False))
    print()

    all_ok = all([s1["ok"], s2["ok"], s3["ok"]])
    return 0 if all_ok else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--di", default="2026-01-01")
    parser.add_argument("--df", default="2026-01-08")
    args = parser.parse_args()
    sys.exit(
        asyncio.run(
            main(date.fromisoformat(args.di), date.fromisoformat(args.df))
        )
    )
