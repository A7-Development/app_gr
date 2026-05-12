"""Smoke test de paridade: silver `wh_dre_mensal` (novo pipeline) vs vw_DRE (legado).

Rodar APOS aplicar a migration `c1e7b2a4d5f3` e o codigo do adapter v2.0.0
na VM 26, e APOS o primeiro ciclo de sync ter populado o bronze. Esse
script compara, por competencia, os totais agregados (n, receita, custo,
resultado) por (grupo_dre, fonte) -- se baterem 1:1, o cutover do silver
e seguro.

Uso:
    python -m scripts.smoke_dre_mensal_paridade <tenant_slug> <comp_from> <comp_to>

Exemplo:
    python -m scripts.smoke_dre_mensal_paridade a7-credit 2026-01-01 2026-04-30

Saida:
    Lista de linhas com diff != 0 (se houver). Exit 0 quando paridade total;
    exit 1 quando qualquer divergencia. Tolera ate `EPSILON_MONETARY` de
    diferenca em valores monetarios (ruido de arredondamento decimal).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import fetch_rows
from app.modules.integracoes.models.tenant_source_config import (
    TenantSourceConfig,
)
from app.shared.identity.tenant import Tenant
from app.warehouse.dre import DreMensal

EPSILON_MONETARY = Decimal("0.10")  # tolerancia em BRL


async def _load_bitfin_config(db: AsyncSession, tenant_slug: str) -> BitfinConfig:
    tenant = (
        await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    ).scalar_one()
    cfg_row = (
        await db.execute(
            select(TenantSourceConfig).where(
                TenantSourceConfig.tenant_id == tenant.id,
                TenantSourceConfig.source_type == "ERP_BITFIN",
            )
        )
    ).scalar_one()
    return BitfinConfig.from_dict(cfg_row.config)


def _fetch_legacy_vw_dre_aggregate(
    config: BitfinConfig, comp_from: date, comp_to: date
) -> list[dict[str, Any]]:
    """SUM por (competencia, grupo_dre, fonte) lendo direto de ANALYTICS.vw_DRE.
    Snapshot do estado anterior ao cutover."""
    if not config.database_analytics:
        raise RuntimeError(
            "database_analytics nao configurado -- impossivel comparar vs vw_DRE"
        )
    query = """
        SELECT
            Competencia AS competencia,
            GrupoDRE AS grupo_dre,
            Fonte AS fonte,
            COUNT(*) AS n,
            CAST(ROUND(SUM(Receita), 2) AS DECIMAL(18,2)) AS receita,
            CAST(ROUND(SUM(Custo), 2) AS DECIMAL(18,2)) AS custo,
            CAST(ROUND(SUM(Resultado), 2) AS DECIMAL(18,2)) AS resultado
        FROM dbo.vw_DRE
        WHERE Competencia BETWEEN ? AND ?
        GROUP BY Competencia, GrupoDRE, Fonte
        ORDER BY Competencia, Fonte, GrupoDRE
    """
    return fetch_rows(config, config.database_analytics, query, (comp_from, comp_to))


async def _aggregate_silver(
    db: AsyncSession, tenant_slug: str, comp_from: date, comp_to: date
) -> list[dict[str, Any]]:
    """SUM por (competencia, grupo_dre, fonte) lendo de wh_dre_mensal."""
    from sqlalchemy import func

    tenant = (
        await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    ).scalar_one()
    stmt = (
        select(
            DreMensal.competencia,
            DreMensal.grupo_dre,
            DreMensal.fonte,
            func.count().label("n"),
            func.sum(DreMensal.receita).label("receita"),
            func.sum(DreMensal.custo).label("custo"),
            func.sum(DreMensal.resultado).label("resultado"),
        )
        .where(
            DreMensal.tenant_id == tenant.id,
            DreMensal.competencia >= comp_from,
            DreMensal.competencia <= comp_to,
        )
        .group_by(DreMensal.competencia, DreMensal.grupo_dre, DreMensal.fonte)
        .order_by(DreMensal.competencia, DreMensal.fonte, DreMensal.grupo_dre)
    )
    rows = await db.execute(stmt)
    return [dict(r._mapping) for r in rows]


def _diff(
    legacy: list[dict], silver: list[dict]
) -> tuple[list[dict], list[dict], list[dict]]:
    """Retorna (only_legacy, only_silver, value_mismatches)."""

    def _key(r: dict) -> tuple:
        return (r["competencia"], r["grupo_dre"], r["fonte"])

    legacy_idx = {_key(r): r for r in legacy}
    silver_idx = {_key(r): r for r in silver}

    only_legacy = [legacy_idx[k] for k in legacy_idx.keys() - silver_idx.keys()]
    only_silver = [silver_idx[k] for k in silver_idx.keys() - legacy_idx.keys()]
    mismatches: list[dict] = []
    for k in legacy_idx.keys() & silver_idx.keys():
        a, b = legacy_idx[k], silver_idx[k]
        if a["n"] != b["n"] or any(
            abs(Decimal(str(a[f] or 0)) - Decimal(str(b[f] or 0))) > EPSILON_MONETARY
            for f in ("receita", "custo", "resultado")
        ):
            mismatches.append(
                {
                    "key": k,
                    "legacy": {f: a[f] for f in ("n", "receita", "custo", "resultado")},
                    "silver": {f: b[f] for f in ("n", "receita", "custo", "resultado")},
                }
            )
    return only_legacy, only_silver, mismatches


async def main(tenant_slug: str, comp_from: date, comp_to: date) -> int:
    async with AsyncSessionLocal() as db:
        config = await _load_bitfin_config(db, tenant_slug)
        silver = await _aggregate_silver(db, tenant_slug, comp_from, comp_to)
    legacy = _fetch_legacy_vw_dre_aggregate(config, comp_from, comp_to)

    only_legacy, only_silver, mismatches = _diff(legacy, silver)

    print(f"Legacy (vw_DRE)   rows: {len(legacy)}")
    print(f"Silver (new path) rows: {len(silver)}")
    print(f"Periodo: {comp_from} -> {comp_to}")
    if only_legacy:
        print(f"\n[FALTANDO no silver novo] {len(only_legacy)} chave(s):")
        for r in only_legacy[:10]:
            print(f"  {r}")
    if only_silver:
        print(f"\n[EXCEDENTE no silver novo] {len(only_silver)} chave(s):")
        for r in only_silver[:10]:
            print(f"  {r}")
    if mismatches:
        print(f"\n[VALORES DIVERGEM] {len(mismatches)} chave(s):")
        for m in mismatches[:10]:
            print(f"  {m['key']}: legacy={m['legacy']} silver={m['silver']}")

    if not only_legacy and not only_silver and not mismatches:
        print("\nOK -- paridade total")
        return 0
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    _, tenant_slug, comp_from_str, comp_to_str = sys.argv
    comp_from = datetime.strptime(comp_from_str, "%Y-%m-%d").date()
    comp_to = datetime.strptime(comp_to_str, "%Y-%m-%d").date()
    sys.exit(asyncio.run(main(tenant_slug, comp_from, comp_to)))
