"""Re-mapeia wh_extrato_bancario a partir do raw imutavel (sem re-fetch QiTech).

Motivo: o mapper bank_account_statement foi escrito contra schema INFERIDO e
gravou silver errado (tipo sempre 'C', descricao nula, dict cru em historico,
linhas de saldo S misturadas). Corrigido em qitech_adapter_v0.5.0 (2026-05-26).
Como raw e imutavel (§13.2), reprocessar e barato: le cada raw, roda o mapper
novo, e troca a particao silver via replace-by-partition (scope raw_id).

Cada raw vira 1 chamada `_replace_canonical_partition(completeness="complete")`:
business keys que sumiram (todas as antigas — descricao mudou de NULL pra texto)
viram orfas DELETADAS + auditadas em decision_log; rows novas entram corretas.
A linha legada com raw_id IS NULL (pre-Fase 1.6) e removida no fim.

Uso:
    .venv/Scripts/python.exe scripts/remap_bank_account_statement.py            # dry-run
    .venv/Scripts/python.exe scripts/remap_bank_account_statement.py --apply    # grava
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import app.shared.identity  # noqa: F401 — carrega Tenant pra resolver FKs
import app.warehouse  # noqa: F401
from sqlalchemy import select, text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.modules.integracoes.adapters.admin.qitech.critical_fields import (  # noqa: E402
    get_critical_fields,
)
from app.modules.integracoes.adapters.admin.qitech.etl import (  # noqa: E402
    _replace_canonical_partition,
)
from app.modules.integracoes.adapters.admin.qitech.mappers import (  # noqa: E402
    map_bank_account_statement,
)
from app.warehouse.extrato_bancario import ExtratoBancario  # noqa: E402
from app.warehouse.qitech_raw_bank_account_statement import (  # noqa: E402
    QiTechRawBankAccountStatement,
)

# Business key — espelha uq_wh_extrato_bancario / bank_account_sync.py.
_BUSINESS_KEY = [
    "tenant_id",
    "unidade_administrativa_id",
    "agencia",
    "conta",
    "data_lancamento",
    "valor",
    "tipo",
    "descricao",
    "contrapartida_doc",
]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Grava de fato. Sem essa flag, so simula (dry-run).",
    )
    args = ap.parse_args()
    dry = not args.apply

    async with AsyncSessionLocal() as db:
        raws = (
            (
                await db.execute(
                    select(QiTechRawBankAccountStatement).order_by(
                        QiTechRawBankAccountStatement.fetched_at
                    )
                )
            )
            .scalars()
            .all()
        )

    print(f"== {'DRY-RUN' if dry else 'APPLY'} == {len(raws)} raw(s) de statement\n")

    total_rows = 0
    total_inserted = 0
    total_orphans = 0
    for raw in raws:
        mapped = map_bank_account_statement(
            payload=raw.payload,
            tenant_id=raw.tenant_id,
            unidade_administrativa_id=raw.unidade_administrativa_id,
            agencia=raw.agencia,
            conta=raw.conta,
        )
        total_rows += len(mapped)
        label = (
            f"{raw.agencia}/{raw.conta} "
            f"{raw.periodo_inicio}..{raw.periodo_fim}"
        )
        if dry:
            print(f"  [{label}] -> {len(mapped)} movimento(s)")
            continue

        async with AsyncSessionLocal() as wdb:
            result = await _replace_canonical_partition(
                wdb,
                ExtratoBancario,
                mapped,
                _BUSINESS_KEY,
                raw_id=raw.id,
                completeness="complete",
                tenant_id=raw.tenant_id,
                endpoint_name="bank_account.statement",
                data_referencia=raw.periodo_inicio,
                critical_fields_for_audit=get_critical_fields(
                    ExtratoBancario.__tablename__
                ),
                unidade_administrativa_id=raw.unidade_administrativa_id,
                triggered_by="remap_bank_account_statement_v0.5.0",
            )
            await wdb.commit()
        total_inserted += result.get("inserted", 0)
        total_orphans += result.get("orphans_count", 0)
        print(
            f"  [{label}] {result.get('mode')}: "
            f"+{result.get('inserted', 0)} / orfas {result.get('orphans_count', 0)}"
        )

    if not dry:
        # Remove a linha legada com raw_id IS NULL (pre-Fase 1.6) — fora de
        # qualquer particao, nao seria substituida pelo replace acima.
        async with AsyncSessionLocal() as wdb:
            res = await wdb.execute(
                text("DELETE FROM wh_extrato_bancario WHERE raw_id IS NULL")
            )
            await wdb.commit()
            print(f"\n  legado raw_id IS NULL removido: {res.rowcount or 0} linha(s)")

    print(
        f"\n== {'simulado' if dry else 'gravado'}: {total_rows} movimentos mapeados"
        + ("" if dry else f", {total_inserted} inseridos, {total_orphans} orfas removidas")
    )


if __name__ == "__main__":
    asyncio.run(main())
