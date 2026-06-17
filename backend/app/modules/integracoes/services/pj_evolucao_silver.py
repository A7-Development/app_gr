"""Mapper (BDC company_evolution) -> silver wh_pj_evolucao (+ mensal).

    upsert_pj_evolucao()          -> wh_pj_evolucao (header, upsert por cnpj)
    replace_pj_evolucao_mensal()  -> wh_pj_evolucao_mensal (serie, delete-insert)

Dataset DERIVADO -> source_updated_at NULL (idade = consulta). Nao commita.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.evolucao import (
    EvolucaoHeaderFields,
    EvolucaoMensalFields,
)
from app.warehouse.pj_evolucao import PjEvolucao, PjEvolucaoMensal


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


_HEADER_COLS = (
    "unidade_administrativa_id", "raw_id",
    "funcionarios_atual", "funcionarios_max", "funcionarios_min",
    "funcionarios_media", "funcionarios_distintos",
    "funcionarios_media_1a", "funcionarios_media_3a", "funcionarios_media_5a",
    "crescimento_yoy_1a", "crescimento_yoy_3a", "crescimento_yoy_5a",
    "qsa_mudou", "faturamento_faixa_atual",
    "socios_max", "socios_min", "socios_media", "socios_distintos",
    "socios_media_1a", "socios_media_3a", "socios_media_5a",
    "atividade_max", "atividade_min", "atividade_media",
    "source_id", "source_updated_at", "ingested_by_version", "hash_origem",
    "trust_level",
)


async def upsert_pj_evolucao(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj: str,
    header: EvolucaoHeaderFields,
    raw_id: UUID | None,
    hash_origem: str | None,
    ingested_by_version: str,
    unidade_administrativa_id: UUID | None = None,
    source_type: SourceType = SourceType.BUREAU_BDC,
) -> None:
    """Upsert do header de evolucao (por tenant+cnpj+source_type)."""
    cnpj_digits = _digits(cnpj)
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "unidade_administrativa_id": unidade_administrativa_id,
        "raw_id": raw_id,
        "cnpj": cnpj_digits,
        "funcionarios_atual": header.funcionarios_atual,
        "funcionarios_max": header.funcionarios_max,
        "funcionarios_min": header.funcionarios_min,
        "funcionarios_media": header.funcionarios_media,
        "funcionarios_distintos": header.funcionarios_distintos,
        "funcionarios_media_1a": header.funcionarios_media_1a,
        "funcionarios_media_3a": header.funcionarios_media_3a,
        "funcionarios_media_5a": header.funcionarios_media_5a,
        "crescimento_yoy_1a": header.crescimento_yoy_1a,
        "crescimento_yoy_3a": header.crescimento_yoy_3a,
        "crescimento_yoy_5a": header.crescimento_yoy_5a,
        "qsa_mudou": header.qsa_mudou,
        "faturamento_faixa_atual": header.faturamento_faixa_atual,
        "socios_max": header.socios_max,
        "socios_min": header.socios_min,
        "socios_media": header.socios_media,
        "socios_distintos": header.socios_distintos,
        "socios_media_1a": header.socios_media_1a,
        "socios_media_3a": header.socios_media_3a,
        "socios_media_5a": header.socios_media_5a,
        "atividade_max": header.atividade_max,
        "atividade_min": header.atividade_min,
        "atividade_media": header.atividade_media,
        "source_type": source_type,
        "source_id": cnpj_digits,
        "source_updated_at": None,
        "ingested_by_version": ingested_by_version,
        "hash_origem": hash_origem,
        "trust_level": TrustLevel.HIGH,
    }
    stmt = pg_insert(PjEvolucao).values(**values)
    update_set = {col: stmt.excluded[col] for col in _HEADER_COLS}
    update_set["ingested_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        constraint="uq_wh_pj_evolucao", set_=update_set
    )
    await db.execute(stmt)


async def replace_pj_evolucao_mensal(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj: str,
    serie: list[EvolucaoMensalFields],
    raw_id: UUID | None,
    hash_origem: str | None,
    ingested_by_version: str,
    unidade_administrativa_id: UUID | None = None,
    source_type: SourceType = SourceType.BUREAU_BDC,
) -> int:
    """Substitui a serie mensal de (tenant, cnpj, source_type). Retorna nº pontos."""
    cnpj_digits = _digits(cnpj)
    await db.execute(
        delete(PjEvolucaoMensal).where(
            PjEvolucaoMensal.tenant_id == tenant_id,
            PjEvolucaoMensal.cnpj == cnpj_digits,
            PjEvolucaoMensal.source_type == source_type,
        )
    )
    rows = [
        PjEvolucaoMensal(
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
            raw_id=raw_id,
            cnpj=cnpj_digits,
            mes=p.mes,
            funcionarios=p.funcionarios,
            faturamento_faixa=p.faturamento_faixa,
            source_type=source_type,
            source_id=f"{cnpj_digits}:{p.mes}"[:255],
            source_updated_at=None,
            ingested_by_version=ingested_by_version,
            hash_origem=hash_origem,
            trust_level=TrustLevel.HIGH,
        )
        for p in serie
        if p.mes is not None
    ]
    db.add_all(rows)
    return len(rows)
