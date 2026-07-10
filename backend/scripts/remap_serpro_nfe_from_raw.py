"""Re-mapeia o silver do estado da NF-e a partir do bronze wh_serpro_raw_nfe.

Uso (de backend/):

    .venv\\Scripts\\python.exe scripts/remap_serpro_nfe_from_raw.py [--chave X]

Sem argumentos, processa TODOS os snapshots do bronze em ordem cronologica
(fetched_at ASC) — eventos acumulam por identidade natural (sem duplicar) e
a situacao termina refletindo o snapshot mais recente de cada chave.

Idempotente e barato (zero chamadas ao SERPRO): e o caminho de replay
quando a regra do mapper muda (CLAUDE.md secao 13.2.1).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import sqlalchemy as sa

import app.shared.identity.tenant  # noqa: F401  (registry)
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.data.serpro.mappers.nfe_estado import (
    mapear_snapshot,
)
from app.warehouse.serpro_raw_nfe import SerproRawNfe


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chave", default=None, help="re-mapeia apenas esta chave de acesso"
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        stmt = sa.select(SerproRawNfe).order_by(SerproRawNfe.fetched_at.asc())
        if args.chave:
            stmt = stmt.where(SerproRawNfe.chave_acesso == args.chave.strip())
        raws = (await db.execute(stmt)).scalars().all()
        if not raws:
            print("[remap] bronze vazio para o filtro pedido — nada a fazer")
            return 0

        total_eventos_novos = 0
        for raw in raws:
            result = await mapear_snapshot(db, raw)
            total_eventos_novos += result.eventos_novos
            print(
                f"[remap] {result.chave} fetched_at={raw.fetched_at:%Y-%m-%d %H:%M} "
                f"situacao={result.situacao} eventos={result.qtd_eventos} "
                f"(novos={result.eventos_novos})"
            )
        await db.commit()

    print(f"\n[remap] {len(raws)} snapshots processados, "
          f"{total_eventos_novos} eventos novos no silver")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
