"""Re-mapeia TODO o historico bronze Serasa PJ -> silver (em lote).

Uso (do diretorio backend/):

    .venv\\Scripts\\python.exe scripts/serasa_pj_remap_all.py [--limit N]

Itera todas as linhas de `wh_serasa_pj_raw_relatorio` (ordem cronologica)
e roda `remap_from_raw` em cada uma. UPSERT idempotente — re-rodar e
seguro. Nenhuma consulta paga nova a Serasa.

Caso de uso que motivou o script (2026-06-10): backfill das colunas
`negative_summary_message` + `suspeita_liminar` (regra serasa_liminar_v1)
sobre as ~2.8k consultas historicas.

Ao final imprime a reconciliacao da regra de liminar: total de consultas
com "NADA CONSTA" + CNPJs distintos sob suspeita (esperado em 2026-06-10:
56 consultas / 32 CNPJs, batendo com a flag `Liminar` do Bitfin).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import func, select

import app.shared.identity.tenant
import app.warehouse  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.services.serasa_pj_query import remap_from_raw
from app.warehouse.serasa_pj_consulta import SerasaPjConsulta
from app.warehouse.serasa_pj_raw_relatorio import SerasaPjRawRelatorio

_PROGRESS_EVERY = 100


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="processa so as N primeiras raws (smoke test)",
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        stmt = select(SerasaPjRawRelatorio.id).order_by(
            SerasaPjRawRelatorio.fetched_at
        )
        if args.limit:
            stmt = stmt.limit(args.limit)
        raw_ids = list((await db.execute(stmt)).scalars())

    total = len(raw_ids)
    print(f"[remap-all] {total} raws a processar")

    ok = 0
    failed: list[str] = []
    for i, raw_id in enumerate(raw_ids, start=1):
        summary = await remap_from_raw(raw_id=raw_id)
        if summary["ok"]:
            ok += 1
        else:
            failed.append(f"{raw_id}: {'; '.join(summary['errors'])}")
        if i % _PROGRESS_EVERY == 0 or i == total:
            print(f"[remap-all] {i}/{total} (ok={ok}, fail={len(failed)})")

    if failed:
        print(f"\n[remap-all] {len(failed)} FALHAS:")
        for line in failed[:20]:
            print(f"  - {line}")
        if len(failed) > 20:
            print(f"  ... +{len(failed) - 20}")

    # Reconciliacao da regra serasa_liminar_v1 pos-backfill.
    async with AsyncSessionLocal() as db:
        liminar_consultas = (
            await db.execute(
                select(func.count()).where(
                    SerasaPjConsulta.suspeita_liminar.is_(True)
                )
            )
        ).scalar_one()
        liminar_cnpjs = (
            await db.execute(
                select(func.count(func.distinct(SerasaPjConsulta.cnpj))).where(
                    SerasaPjConsulta.suspeita_liminar.is_(True)
                )
            )
        ).scalar_one()
        msg_dist = (
            await db.execute(
                select(
                    SerasaPjConsulta.negative_summary_message,
                    func.count(),
                )
                .group_by(SerasaPjConsulta.negative_summary_message)
                .order_by(func.count().desc())
            )
        ).all()

    print("\n[serasa_liminar_v1] reconciliacao:")
    print(f"  consultas suspeita_liminar=true: {liminar_consultas}")
    print(f"  cnpjs distintos sob suspeita:    {liminar_cnpjs}")
    print("  distribuicao de negative_summary_message:")
    for msg, n in msg_dist:
        print(f"    {msg!r}: {n}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
