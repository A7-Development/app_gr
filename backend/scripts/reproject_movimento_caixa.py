"""Re-projeta wh_movimento_caixa a partir dos raws (replace-by-partition).

Conserta os dois bugs diagnosticados em 2026-05-30 (ver migration
f4a2c9d8e1b7):

  - OUTAGE: silver parou em 19/05 porque o refactor "espelho fiel" exigia
    raw_id e a tabela nao tinha. Agora tem -> re-projetar recupera 20/05+.
  - DUPLICACAO: o caminho antigo (sha16 com saldo volatil) acumulava 1
    copia por re-fetch. Re-projetar pelo novo caminho (raw_id+seq_no)
    recria cada dia limpo.

Estrategia: o raw e a fonte da verdade (1147 'complete' desde 2021). Pra
cada raw 'complete' do demonstrativo-caixa, roda `_replace_canonical_partition`
(mesma funcao do ETL) e limpa as linhas legacy (raw_id IS NULL) das datas
re-projetadas. No fim, `--purge-legacy` varre qualquer legacy remanescente.

Idempotente: re-rodar nao duplica (replace-by-partition no scope raw_id).

Uso:
    python -m scripts.reproject_movimento_caixa            # re-projeta tudo
    python -m scripts.reproject_movimento_caixa --since 2026-05-13 --limit 3
    python -m scripts.reproject_movimento_caixa --purge-legacy   # so a varredura final
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import delete, func, select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.modules.integracoes.adapters.admin.qitech.critical_fields import (  # noqa: E402
    get_critical_fields,
)
from app.modules.integracoes.adapters.admin.qitech.etl import (  # noqa: E402
    _replace_canonical_partition,
)
from app.modules.integracoes.adapters.admin.qitech.mappers import (  # noqa: E402
    map_demonstrativo_caixa,
)
from app.warehouse.movimento_caixa import MovimentoCaixa  # noqa: E402
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio  # noqa: E402

TABLE = MovimentoCaixa.__table__
CONFLICT = ["tenant_id", "raw_id", "seq_no"]


async def _reproject_one(raw_row) -> dict:
    """Re-projeta 1 raw e limpa legacy das datas tocadas. Sessao propria."""
    async with AsyncSessionLocal() as db:
        rows = map_demonstrativo_caixa(
            payload=raw_row.payload if isinstance(raw_row.payload, dict) else {},
            tenant_id=raw_row.tenant_id,
            data_posicao=raw_row.data_posicao,
        )
        result = await _replace_canonical_partition(
            db,
            MovimentoCaixa,
            rows,
            CONFLICT,
            raw_id=raw_row.id,
            completeness=raw_row.completeness,
            tenant_id=raw_row.tenant_id,
            endpoint_name="market.demonstrativo-caixa",
            data_referencia=raw_row.data_posicao,
            critical_fields_for_audit=get_critical_fields(TABLE.name),
            unidade_administrativa_id=raw_row.unidade_administrativa_id,
            triggered_by="reproject_movimento_caixa",
        )
        # Limpa legacy (raw_id IS NULL) das datas que esta re-projecao cobriu.
        fresh_dates = {r["data_liquidacao"] for r in rows}
        legacy_deleted = 0
        if fresh_dates and result["mode"] == "replace":
            res = await db.execute(
                delete(TABLE)
                .where(TABLE.c.tenant_id == raw_row.tenant_id)
                .where(TABLE.c.raw_id.is_(None))
                .where(TABLE.c.data_liquidacao.in_(fresh_dates))
            )
            legacy_deleted = res.rowcount or 0
        await db.commit()
        return {
            "inserted": result["inserted"],
            "mode": result["mode"],
            "legacy_deleted": legacy_deleted,
        }


async def reproject(since: date | None, limit: int | None) -> None:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(QiTechRawRelatorio)
            .where(QiTechRawRelatorio.tipo_de_mercado == "demonstrativo-caixa")
            .where(QiTechRawRelatorio.completeness == "complete")
            .order_by(QiTechRawRelatorio.data_posicao)
        )
        if since:
            stmt = stmt.where(QiTechRawRelatorio.data_posicao >= since)
        if limit:
            stmt = stmt.limit(limit)
        raws = (await db.execute(stmt)).scalars().all()

    print(f"[reproject] {len(raws)} raws 'complete' a re-projetar")
    tot_ins = tot_leg = 0
    for i, raw in enumerate(raws, 1):
        r = await _reproject_one(raw)
        tot_ins += r["inserted"]
        tot_leg += r["legacy_deleted"]
        if i % 100 == 0 or i == len(raws):
            print(
                f"  {i}/{len(raws)} | inseridas={tot_ins} legacy_removidas={tot_leg}"
            )
    print(f"[reproject] OK. inseridas={tot_ins} legacy_removidas={tot_leg}")


async def purge_legacy() -> None:
    """Varredura final: remove qualquer linha legacy (raw_id IS NULL)."""
    async with AsyncSessionLocal() as db:
        n_null = (
            await db.execute(
                select(func.count())
                .select_from(TABLE)
                .where(TABLE.c.raw_id.is_(None))
            )
        ).scalar_one()
        n_total = (
            await db.execute(select(func.count()).select_from(TABLE))
        ).scalar_one()
        print(f"[purge] raw_id IS NULL = {n_null} de {n_total} total")
        if n_null:
            res = await db.execute(delete(TABLE).where(TABLE.c.raw_id.is_(None)))
            await db.commit()
            print(f"[purge] removidas {res.rowcount} linhas legacy")
        else:
            print("[purge] nada a remover")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date())
    ap.add_argument("--limit", type=int)
    ap.add_argument("--purge-legacy", action="store_true")
    args = ap.parse_args()

    if args.purge_legacy:
        await purge_legacy()
    else:
        await reproject(args.since, args.limit)


if __name__ == "__main__":
    asyncio.run(main())
