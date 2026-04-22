"""CRUD de `tenant_source_config` + wrapper de encrypt/decrypt para o campo `config`.

MVP: encrypt/decrypt sao no-op (passthrough). O ponto de injecao existe para que
credenciais possam ser cifradas em disco no futuro (Fernet, KMS, secret manager)
sem mudar call sites.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SourceType
from app.modules.integracoes.models.tenant_source_config import TenantSourceConfig


def encrypt_config(config: dict) -> dict:
    """Cifra o dicionario de config antes de persistir.

    MVP: passthrough. Substituir por implementacao real (ex.: Fernet com
    chave em `.env` ou secret manager) sem tocar nos call sites.
    """
    return config


def decrypt_config(config: dict) -> dict:
    """Decifra o dicionario lido do banco."""
    return config


async def get_config(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
) -> TenantSourceConfig | None:
    """Retorna o registro `TenantSourceConfig` (ou None) para (tenant, source)."""
    stmt = select(TenantSourceConfig).where(
        TenantSourceConfig.tenant_id == tenant_id,
        TenantSourceConfig.source_type == source_type,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_decrypted_config(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
) -> dict | None:
    """Retorna apenas o dict de config ja decifrado. None se nao existe."""
    row = await get_config(db, tenant_id, source_type)
    if row is None:
        return None
    return decrypt_config(row.config)


async def upsert_config(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    config: dict,
    *,
    enabled: bool = True,
    sync_frequency_minutes: int | None = None,
) -> None:
    """Cria ou atualiza config de fonte para um tenant. Commita a transacao."""
    encrypted = encrypt_config(config)
    stmt = pg_insert(TenantSourceConfig).values(
        tenant_id=tenant_id,
        source_type=source_type,
        enabled=enabled,
        config=encrypted,
        sync_frequency_minutes=sync_frequency_minutes,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "source_type"],
        set_={
            "enabled": enabled,
            "config": encrypted,
            "sync_frequency_minutes": sync_frequency_minutes,
        },
    )
    await db.execute(stmt)
    await db.commit()
