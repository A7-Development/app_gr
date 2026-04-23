"""Quais tenants estao elegiveis para sincronizar cada fonte externa.

Regra: tenant precisa estar `ativo=true` E ter `tenant_source_config.enabled=true`
para a fonte em questao. Fontes sem config explicito NAO sincronizam — zero
ambiguidade, zero fallback para credenciais globais.

`environment` escopa ainda mais — cada (tenant, source_type, environment) e um
registro independente. Syncs automaticos processam por padrao so production.
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
    """Retorna configs habilitadas de `source_type` + `environment` para tenants ativos."""
    stmt = (
        select(TenantSourceConfig)
        .join(Tenant, Tenant.id == TenantSourceConfig.tenant_id)
        .where(
            TenantSourceConfig.source_type == source_type,
            TenantSourceConfig.environment == environment,
            TenantSourceConfig.enabled.is_(True),
            Tenant.ativo.is_(True),
        )
        .order_by(TenantSourceConfig.tenant_id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def is_source_enabled(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment = Environment.PRODUCTION,
) -> bool:
    """True se o tenant tem `enabled=true` para a fonte + ambiente."""
    stmt = select(TenantSourceConfig.enabled).where(
        TenantSourceConfig.tenant_id == tenant_id,
        TenantSourceConfig.source_type == source_type,
        TenantSourceConfig.environment == environment,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    return bool(row)
