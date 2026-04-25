"""Smoke agregador final: sync_all real contra QiTech + validacao SQL.

Roda `etl.sync_all` no tenant a7-credit pra data alvo (default 2026-01-13)
e imprime contagem de linhas em todas as tabelas canonicas + raw.

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/smoke_qitech_full.py [aaaa-mm-dd]

NAO usa em producao. Bypass de auth de usuario, escreve direto no DB.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from uuid import UUID

# Side-effect imports (registry SQLAlchemy completo).
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

CANONICAL_TABLES = [
    ("wh_qitech_raw_relatorio", "raw"),
    ("wh_posicao_cota_fundo", "outros-fundos"),
    ("wh_saldo_conta_corrente", "conta-corrente"),
    ("wh_saldo_tesouraria", "tesouraria"),
    ("wh_posicao_outros_ativos", "outros-ativos"),
    ("wh_movimento_caixa", "demonstrativo-caixa"),
    ("wh_cpr_movimento", "cpr"),
    ("wh_mec_evolucao_cotas", "mec"),
    ("wh_rentabilidade_fundo", "rentabilidade"),
    ("wh_posicao_renda_fixa", "rf"),
    ("wh_posicao_compromissada", "rf-compromissadas"),
]


async def _count_rows(table: str, tenant_id: UUID, data_posicao: date) -> int:
    from sqlalchemy import text

    if table == "wh_qitech_raw_relatorio":
        sql = text(
            f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tid AND data_posicao = :dp"
        )
    elif table == "wh_movimento_caixa":
        sql = text(
            f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tid AND data_liquidacao = :dp"
        )
    else:
        sql = text(
            f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tid AND data_posicao = :dp"
        )

    async with AsyncSessionLocal() as db:
        result = await db.execute(sql, {"tid": tenant_id, "dp": data_posicao})
        return int(result.scalar() or 0)


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
        f"[smoke-full] tenant=a7-credit data_posicao={data_posicao.isoformat()} "
        f"endpoints_no_pipeline=10"
    )
    print()

    summary = await sync_all(
        A7_CREDIT_TENANT_ID,
        config,
        data_posicao,
        environment=Environment.PRODUCTION,
        triggered_by="smoke_full:cli",
    )

    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(
        f"ok={summary['ok']} elapsed={summary['elapsed_seconds']}s "
        f"rows_ingested={summary['rows_ingested']} "
        f"errors={len(summary['errors'])}"
    )
    if summary["errors"]:
        print("ERRORS:")
        for e in summary["errors"]:
            print(f"  - {e}")
    print()

    print(f"{'STEP':<25} {'OK':<5} {'STATUS':<7} {'CANON':<8} {'ELAPSED':<10}")
    print("-" * 72)
    for step in summary["steps"]:
        print(
            f"{step['tipo_de_mercado']:<25} "
            f"{('OK' if step['ok'] else 'ERR'):<5} "
            f"{step.get('raw_http_status') or '-'!s:<7} "
            f"{step.get('canonical_rows_upserted', 0):<8} "
            f"{step['elapsed_seconds']:<10}"
        )
    print()

    print("=" * 72)
    print("VALIDACAO SQL (linhas no DB)")
    print("=" * 72)
    print(f"{'TABELA':<32} {'ENDPOINT':<22} {'LINHAS':<7}")
    print("-" * 72)
    for table, endpoint in CANONICAL_TABLES:
        n = await _count_rows(table, A7_CREDIT_TENANT_ID, data_posicao)
        print(f"{table:<32} {endpoint:<22} {n:<7}")
    print()

    print("Summary completo (JSON):")
    print(json.dumps(summary, indent=2, default=str, ensure_ascii=False))

    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
