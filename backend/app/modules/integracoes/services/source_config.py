"""CRUD de `tenant_source_config` + envelope encryption para o campo `config`.

A cifragem e envelope (Fernet KEK + DEK por registro, `app.shared.crypto.envelope`).
Call sites continuam passando/recebendo dicts em claro — a camada de persistencia
cifra/decifra em `encrypt_config`/`decrypt_config`.

`environment` permite que o mesmo tenant mantenha sandbox e producao coexistindo
para a mesma fonte.

Multi-UA (CLAUDE.md secao 13, 2026-04-25): cada tupla
(tenant, source_type, environment) pode ter N linhas, uma por UA. As funcoes
de leitura aceitam `unidade_administrativa_id` opcional — quando ausente,
operam em modo de compatibilidade (assumem a UA "default" da config legacy,
i.e. linha sem UA preenchida ou unica linha do tenant).
"""

from __future__ import annotations

from collections.abc import Sequence
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
    *,
    unidade_administrativa_id: UUID | None = None,
) -> TenantSourceConfig | None:
    """Retorna o registro `TenantSourceConfig` (ou None) para a tupla pedida.

    Quando `unidade_administrativa_id` e fornecido, casa exatamente. Quando
    None, casa a linha onde `unidade_administrativa_id IS NULL` (config
    legacy / pre-multi-UA). Para listar todas as linhas de um tenant numa
    fonte, use `list_configs`.
    """
    stmt = select(TenantSourceConfig).where(
        TenantSourceConfig.tenant_id == tenant_id,
        TenantSourceConfig.source_type == source_type,
        TenantSourceConfig.environment == environment,
    )
    if unidade_administrativa_id is None:
        stmt = stmt.where(TenantSourceConfig.unidade_administrativa_id.is_(None))
    else:
        stmt = stmt.where(
            TenantSourceConfig.unidade_administrativa_id == unidade_administrativa_id
        )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_configs(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment = Environment.PRODUCTION,
) -> Sequence[TenantSourceConfig]:
    """Lista TODAS as linhas (uma por UA) do tenant para a fonte/ambiente.

    Pos-multi-UA: pode haver N linhas por (tenant, source, env), uma por UA.
    Linhas com `unidade_administrativa_id IS NULL` (legacy) tambem entram.
    Ordem estavel: NULL primeiro (legacy), depois por UA id.
    """
    stmt = (
        select(TenantSourceConfig)
        .where(
            TenantSourceConfig.tenant_id == tenant_id,
            TenantSourceConfig.source_type == source_type,
            TenantSourceConfig.environment == environment,
        )
        .order_by(
            TenantSourceConfig.unidade_administrativa_id.asc().nulls_first(),
        )
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_config_by_ua(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    unidade_administrativa_id: UUID,
    environment: Environment = Environment.PRODUCTION,
) -> TenantSourceConfig | None:
    """Atalho explicit: busca exatamente a linha de uma UA. Nao casa NULL."""
    return await get_config(
        db,
        tenant_id,
        source_type,
        environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def get_decrypted_config(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment = Environment.PRODUCTION,
    *,
    unidade_administrativa_id: UUID | None = None,
) -> dict | None:
    """Retorna apenas o dict de config ja decifrado. None se nao existe."""
    row = await get_config(
        db,
        tenant_id,
        source_type,
        environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )
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
    unidade_administrativa_id: UUID | None = None,
) -> None:
    """Cria ou atualiza config de fonte para um tenant + ambiente + UA.

    `unidade_administrativa_id=None` mantem retrocompat (linha legacy sem UA).
    Pos-Phase-F, callers devem informar UA explicitamente — UI nova exige isso;
    paths legacy continuam funcionando ate serem migrados.

    Commita a transacao.
    """
    encrypted = encrypt_config(config)
    stmt = pg_insert(TenantSourceConfig).values(
        tenant_id=tenant_id,
        source_type=source_type,
        environment=environment,
        unidade_administrativa_id=unidade_administrativa_id,
        enabled=enabled,
        config=encrypted,
        sync_frequency_minutes=sync_frequency_minutes,
    )
    # UQ `uq_tenant_source_env_ua` e UNIQUE NULLS NOT DISTINCT (migration
    # f9b08c7d4a52) — entao ON CONFLICT casa tanto linhas com UA preenchida
    # quanto a linha legacy unica com UA=NULL.
    stmt = stmt.on_conflict_do_update(
        constraint="uq_tenant_source_env_ua",
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
    unidade_administrativa_id: UUID | None = None,
) -> None:
    """Update parcial: campos ausentes em `partial` preservam o valor anterior.

    Usado pelo endpoint PUT /integracoes/sources/{source_type}/config para permitir
    alterar um subset de campos (ex.: rotacionar so uma API key) sem re-enviar
    secrets que ja estao persistidos.
    """
    row = await get_config(
        db,
        tenant_id,
        source_type,
        environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )
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
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def set_enabled(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    enabled: bool,
    *,
    environment: Environment = Environment.PRODUCTION,
    unidade_administrativa_id: UUID | None = None,
) -> bool:
    """Flipa apenas `enabled`. Retorna True se o registro existia."""
    row = await get_config(
        db,
        tenant_id,
        source_type,
        environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )
    if row is None:
        return False
    row.enabled = enabled
    await db.commit()
    return True
