"""Quais tenants/UAs estao elegiveis para sincronizar cada fonte externa.

Regra: tenant precisa estar `ativo=true` E ter `tenant_source_config.enabled=true`
para a fonte em questao. Fontes sem config explicito NAO sincronizam — zero
ambiguidade, zero fallback para credenciais globais.

`environment` escopa ainda mais — cada (tenant, source_type, environment, UA)
e um registro independente. Syncs automaticos processam por padrao so production.

Multi-UA (CLAUDE.md secao 13, 2026-04-25): `list_enabled_configs` retorna
TODAS as linhas habilitadas — incluindo varias por tenant quando ele tem N
UAs no QiTech. Sync_runner itera por linha, nao por tenant.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Environment, SourceType
from app.modules.integracoes.models.tenant_source_config import TenantSourceConfig
from app.shared.identity.tenant import Tenant


async def list_enabled_configs(
    db: AsyncSession,
    source_type: SourceType,
    environment: Environment = Environment.PRODUCTION,
) -> list[TenantSourceConfig]:
    """Retorna configs habilitadas de `source_type` + `environment` para tenants ativos.

    Pos-multi-UA, pode retornar N linhas por tenant (uma por UA). Caller
    (sync_runner) itera por linha — cada uma vira 1 sync independente com
    suas proprias credenciais.
    """
    stmt = (
        select(TenantSourceConfig)
        .join(Tenant, Tenant.id == TenantSourceConfig.tenant_id)
        .where(
            TenantSourceConfig.source_type == source_type,
            TenantSourceConfig.environment == environment,
            TenantSourceConfig.enabled.is_(True),
            Tenant.ativo.is_(True),
        )
        .order_by(
            TenantSourceConfig.tenant_id,
            TenantSourceConfig.unidade_administrativa_id.asc().nulls_first(),
        )
    )
    return list((await db.execute(stmt)).scalars().all())


async def is_source_enabled(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment = Environment.PRODUCTION,
    *,
    unidade_administrativa_id: UUID | None = None,
) -> bool:
    """True se o tenant tem `enabled=true` para a fonte + ambiente.

    Pos-multi-UA: quando `unidade_administrativa_id` for fornecido, escopa
    a verificacao a essa UA. Sem UA, considera habilitado se QUALQUER linha
    do tenant para essa fonte/ambiente estiver enabled — uso tipico em
    empty-states de BI ("o tenant ja conectou QiTech?").
    """
    stmt = select(TenantSourceConfig.enabled).where(
        TenantSourceConfig.tenant_id == tenant_id,
        TenantSourceConfig.source_type == source_type,
        TenantSourceConfig.environment == environment,
    )
    if unidade_administrativa_id is not None:
        stmt = stmt.where(
            TenantSourceConfig.unidade_administrativa_id == unidade_administrativa_id
        )
    rows = (await db.execute(stmt)).scalars().all()
    return any(rows)
