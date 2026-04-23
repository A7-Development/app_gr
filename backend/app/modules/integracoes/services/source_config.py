"""CRUD de `tenant_source_config` + envelope encryption para o campo `config`.

A cifragem e envelope (Fernet KEK + DEK por registro, `app.shared.crypto.envelope`).
Call sites continuam passando/recebendo dicts em claro — a camada de persistencia
cifra/decifra em `encrypt_config`/`decrypt_config`.

`environment` permite que o mesmo tenant mantenha sandbox e producao coexistindo
para a mesma fonte.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Environment, SourceType
from app.modules.integracoes.models.tenant_source_config import TenantSourceConfig
from app.shared.crypto import decrypt_envelope, encrypt_envelope, is_envelope


def encrypt_config(config: dict) -> dict:
    """Serializa e cifra o dict como envelope (v1)."""
    return encrypt_envelope(config)


def decrypt_config(config: dict) -> dict:
    """Decifra o envelope lido do banco. Tolera dicts legacy plaintext (sem `v`)."""
    if not is_envelope(config):
        # Legacy plaintext (pre-envelope). Migration `encrypt_existing_source_configs`
        # cifra tudo em rest; este fallback so protege hot-read durante upgrade.
        return config
    return decrypt_envelope(config)


async def get_config(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment = Environment.PRODUCTION,
) -> TenantSourceConfig | None:
    """Retorna o registro `TenantSourceConfig` (ou None) para (tenant, source, env)."""
    stmt = select(TenantSourceConfig).where(
        TenantSourceConfig.tenant_id == tenant_id,
        TenantSourceConfig.source_type == source_type,
        TenantSourceConfig.environment == environment,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_decrypted_config(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment = Environment.PRODUCTION,
) -> dict | None:
    """Retorna apenas o dict de config ja decifrado. None se nao existe."""
    row = await get_config(db, tenant_id, source_type, environment)
    if row is None:
        return None
    return decrypt_config(row.config)


async def upsert_config(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    config: dict,
    *,
    environment: Environment = Environment.PRODUCTION,
    enabled: bool = True,
    sync_frequency_minutes: int | None = None,
) -> None:
    """Cria ou atualiza config de fonte para um tenant + ambiente. Commita a transacao."""
    encrypted = encrypt_config(config)
    stmt = pg_insert(TenantSourceConfig).values(
        tenant_id=tenant_id,
        source_type=source_type,
        environment=environment,
        enabled=enabled,
        config=encrypted,
        sync_frequency_minutes=sync_frequency_minutes,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "source_type", "environment"],
        set_={
            "enabled": enabled,
            "config": encrypted,
            "sync_frequency_minutes": sync_frequency_minutes,
        },
    )
    await db.execute(stmt)
    await db.commit()


async def merge_config(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    partial: dict,
    *,
    environment: Environment = Environment.PRODUCTION,
    enabled: bool | None = None,
    sync_frequency_minutes: int | None = None,
) -> None:
    """Update parcial: campos ausentes em `partial` preservam o valor anterior.

    Usado pelo endpoint PUT /integracoes/sources/{source_type}/config para permitir
    alterar um subset de campos (ex.: rotacionar so uma API key) sem re-enviar
    secrets que ja estao persistidos.
    """
    row = await get_config(db, tenant_id, source_type, environment)
    current = decrypt_config(row.config) if row else {}
    merged = {**current, **partial}
    await upsert_config(
        db,
        tenant_id,
        source_type,
        merged,
        environment=environment,
        enabled=enabled if enabled is not None else (row.enabled if row else False),
        sync_frequency_minutes=(
            sync_frequency_minutes
            if sync_frequency_minutes is not None
            else (row.sync_frequency_minutes if row else None)
        ),
    )


async def set_enabled(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    enabled: bool,
    *,
    environment: Environment = Environment.PRODUCTION,
) -> bool:
    """Flipa apenas `enabled`. Retorna True se o registro existia."""
    row = await get_config(db, tenant_id, source_type, environment)
    if row is None:
        return False
    row.enabled = enabled
    await db.commit()
    return True
