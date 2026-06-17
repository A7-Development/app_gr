"""Mappers (BDC) -> silver canonico do Quadro Societario.

A camada `integracoes` popula o warehouse (§11.3). Materializa, vendor-neutro:

    map_relationships()   -> replace_pj_vinculos()       -> wh_pj_vinculo
    map_economic_group()  -> upsert_pj_grupo_indicador()  -> wh_pj_grupo_indicador

Reconciliacao por `(tenant, cnpj, source_type)`:
- vinculos: DELETE-INSERT (o conjunto de arestas muda entre consultas; substitui
  apenas o que veio DESTA fonte, preservando arestas de outra fonte futura).
- grupo: UPSERT (1 linha por cnpj+source_type).

Frescor (§14): cada aresta carrega seu `source_updated_at` (LastUpdateDate da
fonte); o grupo e derivado -> `source_updated_at=None` (idade = consulta).

Nenhuma funcao commita — o caller controla a transacao.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.societario import (
    GrupoIndicadorFields,
    VinculoFields,
    VinculosResumo,
)
from app.warehouse.pj_cadastro import PjCadastro
from app.warehouse.pj_grupo_indicador import PjGrupoIndicador
from app.warehouse.pj_vinculo import PjVinculo


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


async def replace_pj_vinculos(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj: str,
    vinculos: list[VinculoFields],
    raw_id: UUID | None,
    hash_origem: str | None,
    ingested_by_version: str,
    unidade_administrativa_id: UUID | None = None,
    source_type: SourceType = SourceType.BUREAU_BDC,
) -> int:
    """Substitui o conjunto de arestas de (tenant, cnpj, source_type).

    DELETE das arestas existentes desta fonte + INSERT do novo conjunto.
    Preserva arestas de outras fontes (reconciliacao por source_type).
    Retorna o numero de arestas inseridas.
    """
    cnpj_digits = _digits(cnpj)

    await db.execute(
        delete(PjVinculo).where(
            PjVinculo.tenant_id == tenant_id,
            PjVinculo.cnpj == cnpj_digits,
            PjVinculo.source_type == source_type,
        )
    )

    rows = [
        PjVinculo(
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
            raw_id=raw_id,
            cnpj=cnpj_digits,
            documento_relacionado=v.documento_relacionado,
            tipo_pessoa=v.tipo_pessoa,
            nome=v.nome,
            relationship_type=v.relationship_type,
            relationship_name=v.relationship_name,
            percentual=v.percentual,
            ativo=v.ativo,
            data_inicio=v.data_inicio,
            data_fim=v.data_fim,
            source_type=source_type,
            source_id=(
                f"{cnpj_digits}:{v.documento_relacionado or '?'}:"
                f"{v.relationship_type or '?'}:{v.data_inicio or '?'}"
            )[:255],
            source_updated_at=v.source_updated_at,
            ingested_by_version=ingested_by_version,
            hash_origem=hash_origem,
            trust_level=TrustLevel.HIGH,
        )
        for v in vinculos
    ]
    db.add_all(rows)
    return len(rows)


_GRUPO_UPSERT_COLS = (
    "unidade_administrativa_id",
    "raw_id",
    "total_companies",
    "total_active",
    "total_inactive",
    "total_people",
    "total_owners",
    "total_sanctioned",
    "total_peps",
    "total_lawsuits",
    "total_bad_passages",
    "avg_activity_level",
    "min_company_age",
    "max_company_age",
    "avg_company_age",
    "first_passage_date",
    "last_passage_date",
    "last_12m_passages",
    "faturamento_faixa",
    "faturamento_faixa_min",
    "faturamento_faixa_max",
    "faturamento_faixa_media",
    "funcionarios_faixa",
    "funcionarios_faixa_min",
    "funcionarios_faixa_max",
    "funcionarios_faixa_media",
    "cnaes",
    "source_id",
    "source_updated_at",
    "ingested_by_version",
    "hash_origem",
    "trust_level",
)


async def upsert_pj_grupo_indicador(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj: str,
    fields: GrupoIndicadorFields,
    raw_id: UUID | None,
    hash_origem: str | None,
    ingested_by_version: str,
    unidade_administrativa_id: UUID | None = None,
    source_type: SourceType = SourceType.BUREAU_BDC,
) -> None:
    """Upsert dos indicadores do grupo (por tenant+cnpj+source_type)."""
    cnpj_digits = _digits(cnpj)
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "unidade_administrativa_id": unidade_administrativa_id,
        "raw_id": raw_id,
        "cnpj": cnpj_digits,
        "total_companies": fields.total_companies,
        "total_active": fields.total_active,
        "total_inactive": fields.total_inactive,
        "total_people": fields.total_people,
        "total_owners": fields.total_owners,
        "total_sanctioned": fields.total_sanctioned,
        "total_peps": fields.total_peps,
        "total_lawsuits": fields.total_lawsuits,
        "total_bad_passages": fields.total_bad_passages,
        "avg_activity_level": fields.avg_activity_level,
        "min_company_age": fields.min_company_age,
        "max_company_age": fields.max_company_age,
        "avg_company_age": fields.avg_company_age,
        "first_passage_date": fields.first_passage_date,
        "last_passage_date": fields.last_passage_date,
        "last_12m_passages": fields.last_12m_passages,
        "faturamento_faixa": fields.faturamento_faixa,
        "faturamento_faixa_min": fields.faturamento_faixa_min,
        "faturamento_faixa_max": fields.faturamento_faixa_max,
        "faturamento_faixa_media": fields.faturamento_faixa_media,
        "funcionarios_faixa": fields.funcionarios_faixa,
        "funcionarios_faixa_min": fields.funcionarios_faixa_min,
        "funcionarios_faixa_max": fields.funcionarios_faixa_max,
        "funcionarios_faixa_media": fields.funcionarios_faixa_media,
        "cnaes": fields.cnaes,
        "source_type": source_type,
        "source_id": cnpj_digits,
        # Dataset DERIVADO: sem LastUpdateDate -> idade = data da consulta.
        "source_updated_at": None,
        "ingested_by_version": ingested_by_version,
        "hash_origem": hash_origem,
        "trust_level": TrustLevel.HIGH,
    }
    stmt = pg_insert(PjGrupoIndicador).values(**values)
    update_set = {col: stmt.excluded[col] for col in _GRUPO_UPSERT_COLS}
    update_set["ingested_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        constraint="uq_wh_pj_grupo_indicador", set_=update_set
    )
    await db.execute(stmt)


async def set_cadastro_vinculos_resumo(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj: str,
    resumo: VinculosResumo,
) -> None:
    """Grava o resumo do `relationships` (qtd_socios, familiar...) na wh_pj_cadastro.

    UPDATE da linha existente — no fetch unificado o upsert cadastral roda antes,
    entao a linha existe. Sem linha = 0 rows (silencioso). Nao commita.
    """
    await db.execute(
        update(PjCadastro)
        .where(
            PjCadastro.tenant_id == tenant_id,
            PjCadastro.cnpj == _digits(cnpj),
        )
        .values(
            qtd_socios=resumo.qtd_socios,
            qtd_empresas_possuidas=resumo.qtd_empresas_possuidas,
            empresa_familiar=resumo.empresa_familiar,
            operada_pela_familia=resumo.operada_pela_familia,
        )
    )
