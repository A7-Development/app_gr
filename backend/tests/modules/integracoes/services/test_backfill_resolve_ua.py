"""resolve_backfill_ua — fix do bug ua=None no re-sync em lote (2026-05-27).

Garante que backfill sem UA explicita resolve a config habilitada em vez de
disparar job com ua=None (que falhava 100% silenciosamente).
"""

from __future__ import annotations

from uuid import UUID

import pytest

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.cadastros.models.unidade_administrativa import (
    TipoUnidadeAdministrativa,
    UnidadeAdministrativa,
)
from app.modules.integracoes.models.tenant_source_config import TenantSourceConfig
from app.modules.integracoes.services.backfill_service import resolve_backfill_ua
from app.shared.identity.tenant import Tenant

_SRC = SourceType.ADMIN_QITECH
_ENV = Environment.PRODUCTION


async def _make_ua(tenant_id: UUID, nome: str) -> UUID:
    async with AsyncSessionLocal() as db:
        ua = UnidadeAdministrativa(
            tenant_id=tenant_id, nome=nome, tipo=TipoUnidadeAdministrativa.FIDC
        )
        db.add(ua)
        await db.commit()
        await db.refresh(ua)
        return ua.id


async def _add_config(
    tenant_id: UUID,
    ua_id: UUID | None,
    *,
    enabled: bool = True,
) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            TenantSourceConfig(
                tenant_id=tenant_id,
                source_type=_SRC,
                environment=_ENV,
                unidade_administrativa_id=ua_id,
                enabled=enabled,
                config={},
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_single_enabled_ua_resolves(tenant_a: Tenant):
    ua_id = await _make_ua(tenant_a.id, "REALINVEST FIDC")
    await _add_config(tenant_a.id, ua_id)
    async with AsyncSessionLocal() as db:
        got = await resolve_backfill_ua(
            db, tenant_id=tenant_a.id, source_type=_SRC, environment=_ENV
        )
    assert got == ua_id


@pytest.mark.asyncio
async def test_disabled_config_ignored(tenant_a: Tenant):
    ua_ok = await _make_ua(tenant_a.id, "FUNDO ATIVO")
    ua_off = await _make_ua(tenant_a.id, "FUNDO DESLIGADO")
    await _add_config(tenant_a.id, ua_ok, enabled=True)
    await _add_config(tenant_a.id, ua_off, enabled=False)
    async with AsyncSessionLocal() as db:
        got = await resolve_backfill_ua(
            db, tenant_id=tenant_a.id, source_type=_SRC, environment=_ENV
        )
    assert got == ua_ok


@pytest.mark.asyncio
async def test_multiple_enabled_uas_raises(tenant_a: Tenant):
    ua1 = await _make_ua(tenant_a.id, "FUNDO 1")
    ua2 = await _make_ua(tenant_a.id, "FUNDO 2")
    await _add_config(tenant_a.id, ua1)
    await _add_config(tenant_a.id, ua2)
    async with AsyncSessionLocal() as db:
        with pytest.raises(ValueError, match=r"[Mm]ultiplas UAs"):
            await resolve_backfill_ua(
                db, tenant_id=tenant_a.id, source_type=_SRC, environment=_ENV
            )


@pytest.mark.asyncio
async def test_no_config_raises(tenant_a: Tenant):
    async with AsyncSessionLocal() as db:
        with pytest.raises(ValueError, match="Nenhuma config habilitada"):
            await resolve_backfill_ua(
                db, tenant_id=tenant_a.id, source_type=_SRC, environment=_ENV
            )


@pytest.mark.asyncio
async def test_legacy_null_ua_config_returns_none(tenant_a: Tenant):
    # Config legacy (UA NULL) habilitada -> sync funciona com ua=None.
    await _add_config(tenant_a.id, None)
    async with AsyncSessionLocal() as db:
        got = await resolve_backfill_ua(
            db, tenant_id=tenant_a.id, source_type=_SRC, environment=_ENV
        )
    assert got is None


@pytest.mark.asyncio
async def test_tenant_isolation(tenant_a: Tenant, tenant_b: Tenant):
    # config so do tenant_a; tenant_b nao deve resolver nada.
    ua_a = await _make_ua(tenant_a.id, "UA A")
    await _add_config(tenant_a.id, ua_a)
    async with AsyncSessionLocal() as db:
        with pytest.raises(ValueError, match="Nenhuma config habilitada"):
            await resolve_backfill_ua(
                db, tenant_id=tenant_b.id, source_type=_SRC, environment=_ENV
            )
