"""Reprocessa wh_aquisicao_recebivel a partir de wh_qitech_raw_relatorio.

Necessario apos fix de escala (2026-05-18, ADAPTER_VERSION v0.2.1): valorCompra
e valorVencimento eram gravados em centavos no silver porque o endpoint
fidc-custodia/aquisicao-consolidada da QiTech retorna em INT centavos (mas
demais endpoints retornam em reais). Mapper agora divide por 100 — re-mapear
o historico do raw corrige os dados ja gravados sem precisar re-fetch.

Idempotente — upsert sobre `(tenant_id, source_id)`. Raw e imutavel,
silver e re-mapeavel por construcao (CLAUDE.md §13.2).

NAO bate na QiTech. Sem efeito em scheduler / jobs / decision_log.

Uso (de backend/):
    # Reprocessa 1 data especifica
    .venv\\Scripts\\python.exe -m scripts.reprocess_aquisicao_consolidada \\
        --tenant-slug a7-credit --data-posicao 2026-05-13

    # Reprocessa TODOS os snapshots do tenant
    .venv\\Scripts\\python.exe -m scripts.reprocess_aquisicao_consolidada \\
        --tenant-slug a7-credit --all
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from itertools import islice
from uuid import UUID

# Side-effect imports (registry SQLAlchemy completo).
import app.shared.identity.tenant  # noqa: F401
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.admin.qitech.etl import (
    CHUNK_SIZE,
    MAX_PG_PARAMS,
)
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_aquisicao_consolidada,
)
from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio


TIPO_DE_MERCADO = "fidc-custodia/aquisicao-consolidada"


async def _resolve_tenant_id(slug: str) -> UUID:
    async with AsyncSessionLocal() as db:
        tid = await db.scalar(
            text("SELECT id FROM tenants WHERE slug = :s"), {"s": slug}
        )
        if not tid:
            raise RuntimeError(f"tenant slug='{slug}' nao encontrado")
        return tid


async def _list_raws(
    tenant_id: UUID, data_posicao: date | None
) -> list[QiTechRawRelatorio]:
    async with AsyncSessionLocal() as db:
        stmt = select(QiTechRawRelatorio).where(
            QiTechRawRelatorio.tenant_id == tenant_id,
            QiTechRawRelatorio.tipo_de_mercado == TIPO_DE_MERCADO,
        )
        if data_posicao is not None:
            stmt = stmt.where(QiTechRawRelatorio.data_posicao == data_posicao)
        stmt = stmt.order_by(QiTechRawRelatorio.data_posicao.asc())
        return list((await db.execute(stmt)).scalars().all())


def _chunked(it, size):
    it = iter(it)
    while chunk := list(islice(it, size)):
        yield chunk


def _extract_cnpj_fundo(payload: dict) -> str:
    """Extrai fundoCnpj do primeiro item do payload pra passar pro mapper.

    Mapper aceita int ou string e normaliza via `_normalize_cnpj_any`. Quando
    payload e vazio ou nao tem itens, retorna '' (mapper devolve []).
    """
    items = payload.get("aquisicaoConsolidada", []) if isinstance(payload, dict) else []
    if not items:
        return ""
    first = items[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("fundoCnpj", ""))


async def _reprocess_one(raw: QiTechRawRelatorio) -> int:
    """Re-mapeia um raw e faz upsert no canonico. Retorna linhas afetadas."""
    if not raw.payload:
        print(
            f"  [skip] raw {raw.id} ({raw.data_posicao}): payload vazio "
            f"(http_status={raw.http_status})"
        )
        return 0

    cnpj_fundo = _extract_cnpj_fundo(raw.payload)
    canonical_rows = map_aquisicao_consolidada(
        payload=raw.payload,
        tenant_id=raw.tenant_id,
        cnpj_fundo=cnpj_fundo,
    )
    if not canonical_rows:
        print(f"  [skip] raw {raw.id} ({raw.data_posicao}): mapper retornou 0 linhas")
        return 0

    # Anotar UA do raw em cada row (mapper nao seta — adapter ETL normalmente
    # injeta isso via `_apply_ua_context`; pra reprocesso, propagamos do raw).
    for row in canonical_rows:
        row["unidade_administrativa_id"] = raw.unidade_administrativa_id

    all_columns = [
        c.name for c in AquisicaoRecebivel.__table__.columns if c.name != "id"
    ]
    normalized = [{c: row.get(c) for c in all_columns} for row in canonical_rows]
    seen: dict[str, dict] = {}
    for r in normalized:
        seen[r["source_id"]] = r
    deduped = list(seen.values())

    chunk_size = max(1, min(CHUNK_SIZE, MAX_PG_PARAMS // len(all_columns)))
    update_cols = [
        c.name
        for c in AquisicaoRecebivel.__table__.columns
        if c.name not in {"id", "tenant_id", "source_id", "ingested_at"}
    ]

    rows_upserted = 0
    async with AsyncSessionLocal() as db:
        for chunk in _chunked(deduped, chunk_size):
            stmt = pg_insert(AquisicaoRecebivel.__table__).values(chunk)
            update_set = {name: stmt.excluded[name] for name in update_cols}
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "source_id"], set_=update_set
            )
            await db.execute(stmt)
            rows_upserted += len(chunk)
        await db.commit()
    return rows_upserted


async def _main_async(args: argparse.Namespace) -> int:
    tenant_id = await _resolve_tenant_id(args.tenant_slug)
    data_posicao: date | None = (
        date.fromisoformat(args.data_posicao) if args.data_posicao else None
    )
    raws = await _list_raws(tenant_id, data_posicao)
    if not raws:
        scope = (
            f"data_posicao={data_posicao.isoformat()}"
            if data_posicao
            else "TODOS os snapshots aquisicao-consolidada"
        )
        print(f"[reprocess] nenhum raw encontrado pra tenant={args.tenant_slug} ({scope})")
        return 1

    print(
        f"[reprocess] tenant={args.tenant_slug} tenant_id={tenant_id} "
        f"raws_a_processar={len(raws)}"
    )
    total = 0
    for raw in raws:
        n = await _reprocess_one(raw)
        total += n
        print(f"  [ok] {raw.data_posicao}: {n} linhas upserted")
    print(f"[reprocess] DONE total_rows_upserted={total}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--tenant-slug", required=True, help="Slug do tenant (ex.: a7-credit)"
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--data-posicao",
        help="Data a reprocessar (ISO YYYY-MM-DD). Reprocessa apenas esse dia.",
    )
    g.add_argument(
        "--all",
        action="store_true",
        dest="reprocess_all",
        help="Reprocessa TODOS os snapshots aquisicao-consolidada do tenant.",
    )
    args = p.parse_args()
    if args.reprocess_all:
        args.data_posicao = None
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
