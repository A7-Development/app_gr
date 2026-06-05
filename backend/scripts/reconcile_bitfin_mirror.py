"""Reconcile do espelho Bitfin: hard-delete de orfaos no gr_db.

O ETL do Bitfin e upsert-only (ON CONFLICT DO UPDATE) e nunca enxerga
delecoes. Quando o Bitfin re-edita uma operacao, os titulos antigos sao
APAGADOS FISICAMENTE na fonte (sem flag/tombstone); no nosso espelho ficam
orfaos para sempre, poluindo a "carteira atual" (ex.: conciliacao de boletos
marcando "So BITFIN" para titulos que nem existem mais). Este oneshot faz o
anti-join e remove os orfaos do gr_db.

NUNCA toca o Bitfin: la e SELECT id-only; o DELETE acontece SO no gr_db, nas
tabelas wh_titulo / wh_operacao / wh_operacao_item, escopado por tenant_id.

Uso:
    python -m scripts.reconcile_bitfin_mirror                  # DRY-RUN (a7-credit)
    python -m scripts.reconcile_bitfin_mirror --apply          # executa o delete
    python -m scripts.reconcile_bitfin_mirror --tenant a7-credit --apply
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select

import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import fetch_rows
from app.modules.integracoes.adapters.erp.bitfin.etl import (
    _RECONCILE_TARGETS,
    sync_reconcile_mirror,
)
from app.modules.integracoes.services.source_config import get_decrypted_config
from app.shared.identity.tenant import Tenant


async def _resolve_tenant_id(slug: str) -> UUID:
    async with AsyncSessionLocal() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        if tenant is None:
            raise SystemExit(f"Tenant '{slug}' nao encontrado.")
        return tenant.id


async def _load_config(tenant_id: UUID) -> BitfinConfig:
    async with AsyncSessionLocal() as db:
        cfg_dict = await get_decrypted_config(db, tenant_id, SourceType.ERP_BITFIN)
    if cfg_dict is None:
        raise SystemExit(f"Tenant {tenant_id} sem tenant_source_config erp:bitfin.")
    return BitfinConfig.from_dict(cfg_dict)


async def _dry_run(tenant_id: UUID, config: BitfinConfig) -> None:
    """Conta orfaos por tabela SEM deletar — mesma logica do anti-join."""
    async with AsyncSessionLocal() as db:
        for model, query, label in _RECONCILE_TARGETS:
            live_rows = await asyncio.to_thread(
                fetch_rows, config, config.database_bitfin, query
            )
            live_ids = {str(r["source_id"]) for r in live_rows}
            if not live_ids:
                print(f"  {label}: conjunto vivo VAZIO -> ABORTA (guarda).")
                continue
            wh_ids = set(
                (
                    await db.execute(
                        select(model.source_id).where(model.tenant_id == tenant_id)
                    )
                )
                .scalars()
                .all()
            )
            phantoms = wh_ids - live_ids
            frac = (len(phantoms) / len(wh_ids) * 100) if wh_ids else 0
            print(
                f"  {label}: vivo_bitfin={len(live_ids)} espelho={len(wh_ids)} "
                f"orfaos={len(phantoms)} ({frac:.2f}%)"
            )
            # Amostra dos primeiros orfaos para inspecao.
            for sid in list(phantoms)[:5]:
                print(f"      orfao source_id={sid}")


async def _main(tenant_slug: str, apply: bool) -> None:
    tenant_id = await _resolve_tenant_id(tenant_slug)
    config = await _load_config(tenant_id)
    print(
        f"[reconcile] tenant={tenant_slug} ({tenant_id}) "
        f"db={config.database_bitfin} mode={'APPLY' if apply else 'DRY-RUN'}"
    )

    if not apply:
        await _dry_run(tenant_id, config)
        print("[reconcile] DRY-RUN — nada deletado. Use --apply para executar.")
        return

    result = await sync_reconcile_mirror(tenant_id, config, force=True)
    print(f"[reconcile] APLICADO — total_deleted={result.get('total_deleted')}")
    for r in result.get("reconcile", []):
        print(f"  {r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile espelho Bitfin (hard-delete orfaos)")
    parser.add_argument("--tenant", default="a7-credit")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Executa o DELETE no gr_db. Sem esta flag, apenas DRY-RUN.",
    )
    args = parser.parse_args()
    asyncio.run(_main(args.tenant, args.apply))


if __name__ == "__main__":
    main()
