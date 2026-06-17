"""Mapper raw (BDC) -> silver canônico `wh_pj_cadastro`.

A camada `integracoes` popula o warehouse (§11.3). Este service materializa o
cadastro canônico VENDOR-NEUTRO de uma PJ a partir dos campos já parseados pelo
mapper do BDC (`CadastralFields`). Grão: 1 linha por (tenant, cnpj) — upsert.

Ver `docs/central-de-dados-arquitetura.md` §5/§5.2. Reaproveitado tanto pelo
fluxo on-demand (`fetch_cadastral_pj`) quanto pelo backfill sobre o raw.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.cadastral import (
    CadastralFields,
)
from app.warehouse.pj_cadastro import PjCadastro

# Colunas reescritas no conflito (todas menos a business key e o id).
_UPSERT_COLS = (
    "unidade_administrativa_id",
    "raw_id",
    "razao_social",
    "nome_fantasia",
    "situacao_cadastral",
    "data_fundacao",
    "capital_social",
    "cnae_principal",
    "cnaes",
    "source_type",
    "source_id",
    "source_updated_at",
    "ingested_by_version",
    "hash_origem",
    "trust_level",
)


def _cnae_principal(cnaes: list[dict[str, Any]]) -> str | None:
    """Código do CNAE principal (IsMain) ou o primeiro disponível."""
    for c in cnaes or []:
        if c.get("is_main"):
            return c.get("code")
    return (cnaes[0].get("code") if cnaes else None)


async def upsert_pj_cadastro(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj: str,
    fields: CadastralFields,
    raw_id: UUID | None,
    hash_origem: str | None,
    ingested_by_version: str,
    unidade_administrativa_id: UUID | None = None,
    source_updated_at: datetime | None = None,
) -> None:
    """Upsert do cadastro canônico em `wh_pj_cadastro` (por tenant+cnpj).

    `source_updated_at` = `BasicData.LastUpdateDate` da fonte (idade do dado,
    §14). Opcional/None para retrocompat; o fetch unificado passa o valor.

    NÃO commita — o caller controla a transação.
    """
    cnpj_digits = "".join(ch for ch in (cnpj or "") if ch.isdigit())
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "unidade_administrativa_id": unidade_administrativa_id,
        "raw_id": raw_id,
        "cnpj": cnpj_digits,
        "razao_social": fields.official_name,
        "nome_fantasia": fields.trade_name,
        "situacao_cadastral": fields.tax_status,
        "data_fundacao": fields.founding_date,
        "capital_social": fields.capital_social,
        "cnae_principal": _cnae_principal(fields.cnaes),
        "cnaes": fields.cnaes or None,
        "source_type": SourceType.BUREAU_BDC,
        "source_id": cnpj_digits,
        "source_updated_at": source_updated_at,
        "ingested_by_version": ingested_by_version,
        "hash_origem": hash_origem,
        "trust_level": TrustLevel.HIGH,
    }
    stmt = pg_insert(PjCadastro).values(**values)
    update_set = {col: stmt.excluded[col] for col in _UPSERT_COLS}
    update_set["ingested_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        constraint="uq_wh_pj_cadastro", set_=update_set
    )
    await db.execute(stmt)
