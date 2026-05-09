"""Tests da logica de scheduling per-endpoint.

Foco em `list_due_endpoints` — os helpers `_is_due_interval`/`_is_due_daily_at`
sao testados via casos integrados (fixture grava TSEC, query roda, asseroes
batem).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Environment, SourceType
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
)
from app.modules.integracoes.services.endpoint_scheduling import (
    list_due_endpoints,
)

SP_TZ = ZoneInfo("America/Sao_Paulo")


def _make_row(
    *,
    tenant_id: UUID,
    endpoint_name: str,
    schedule_kind: str,
    schedule_value: str | None,
    enabled: bool = True,
    last_started_at: datetime | None = None,
    last_status: str | None = None,
    source_type: SourceType = SourceType.ADMIN_QITECH,
    environment: Environment = Environment.PRODUCTION,
) -> TenantSourceEndpointConfig:
    return TenantSourceEndpointConfig(
        tenant_id=tenant_id,
        source_type=source_type,
        environment=environment,
        unidade_administrativa_id=None,
        endpoint_name=endpoint_name,
        enabled=enabled,
        schedule_kind=schedule_kind,
        schedule_value=schedule_value,
        last_sync_started_at=last_started_at,
        last_sync_status=last_status,
    )


@pytest.fixture
async def db(seed_tenant: UUID) -> AsyncSession:
    """Override do conftest? Usa a sessao real do AsyncSessionLocal."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def seed_tenant() -> UUID:
    """Tenant minimo pra FKs do TSEC. Cria + cleanup."""
    from sqlalchemy import delete

    from app.core.database import AsyncSessionLocal
    from app.modules.integracoes.models.tenant_source_endpoint_config import (
        TenantSourceEndpointConfig,
    )
    from app.shared.identity.tenant import Tenant

    tid = uuid4()
    async with AsyncSessionLocal() as session:
        session.add(
            Tenant(
                id=tid,
                slug=f"test-{tid.hex[:8]}",
                name="Test Tenant",
            )
        )
        await session.commit()
    yield tid
    # cleanup TSEC + tenant
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(TenantSourceEndpointConfig).where(
                TenantSourceEndpointConfig.tenant_id == tid
            )
        )
        await session.execute(delete(Tenant).where(Tenant.id == tid))
        await session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# interval
# ─────────────────────────────────────────────────────────────────────────────


async def test_interval_never_ran_is_due(db: AsyncSession, seed_tenant: UUID):
    db.add(
        _make_row(
            tenant_id=seed_tenant,
            endpoint_name="market.outros_fundos",
            schedule_kind="interval",
            schedule_value="60",
            last_started_at=None,
        )
    )
    await db.commit()

    rows = await list_due_endpoints(db, now=datetime.now(UTC))
    names = {r.endpoint_name for r in rows if r.tenant_id == seed_tenant}
    assert "market.outros_fundos" in names


async def test_interval_recent_not_due(db: AsyncSession, seed_tenant: UUID):
    now = datetime.now(UTC)
    db.add(
        _make_row(
            tenant_id=seed_tenant,
            endpoint_name="market.cpr",
            schedule_kind="interval",
            schedule_value="60",
            last_started_at=now - timedelta(minutes=30),  # 30 min < 60
        )
    )
    await db.commit()

    rows = await list_due_endpoints(db, now=now)
    names = {r.endpoint_name for r in rows if r.tenant_id == seed_tenant}
    assert "market.cpr" not in names


async def test_interval_passed_threshold_is_due(
    db: AsyncSession, seed_tenant: UUID
):
    now = datetime.now(UTC)
    db.add(
        _make_row(
            tenant_id=seed_tenant,
            endpoint_name="market.mec",
            schedule_kind="interval",
            schedule_value="60",
            last_started_at=now - timedelta(minutes=90),  # 90 > 60
        )
    )
    await db.commit()

    rows = await list_due_endpoints(db, now=now)
    names = {r.endpoint_name for r in rows if r.tenant_id == seed_tenant}
    assert "market.mec" in names


# ─────────────────────────────────────────────────────────────────────────────
# daily_at
# ─────────────────────────────────────────────────────────────────────────────


async def test_daily_at_before_target_not_due(
    db: AsyncSession, seed_tenant: UUID
):
    """Hoje SP eh 06:00 e target eh 07:00 — ainda nao chegou."""
    today_sp = datetime.now(SP_TZ).date()
    now_sp_06h = datetime.combine(
        today_sp, datetime.min.time().replace(hour=6), tzinfo=SP_TZ
    )

    db.add(
        _make_row(
            tenant_id=seed_tenant,
            endpoint_name="market.rentabilidade",
            schedule_kind="daily_at",
            schedule_value="07:00",
            last_started_at=None,
        )
    )
    await db.commit()

    rows = await list_due_endpoints(db, now=now_sp_06h.astimezone(UTC))
    names = {r.endpoint_name for r in rows if r.tenant_id == seed_tenant}
    assert "market.rentabilidade" not in names


async def test_daily_at_after_target_never_ran_is_due(
    db: AsyncSession, seed_tenant: UUID
):
    """Hoje SP eh 09:00 e target eh 07:00 — passou + nunca rodou hoje."""
    today_sp = datetime.now(SP_TZ).date()
    now_sp_09h = datetime.combine(
        today_sp, datetime.min.time().replace(hour=9), tzinfo=SP_TZ
    )

    db.add(
        _make_row(
            tenant_id=seed_tenant,
            endpoint_name="market.rf",
            schedule_kind="daily_at",
            schedule_value="07:00",
            last_started_at=None,
        )
    )
    await db.commit()

    rows = await list_due_endpoints(db, now=now_sp_09h.astimezone(UTC))
    names = {r.endpoint_name for r in rows if r.tenant_id == seed_tenant}
    assert "market.rf" in names


async def test_daily_at_already_ran_today_not_due(
    db: AsyncSession, seed_tenant: UUID
):
    """Passou do horario, mas ja rodou hoje SP — nao deve disparar."""
    today_sp = datetime.now(SP_TZ).date()
    # Now SP 09:00; rodou hoje SP 07:30 (apos target 07:00)
    now_sp = datetime.combine(
        today_sp, datetime.min.time().replace(hour=9), tzinfo=SP_TZ
    )
    last_sp = datetime.combine(
        today_sp,
        datetime.min.time().replace(hour=7, minute=30),
        tzinfo=SP_TZ,
    )

    db.add(
        _make_row(
            tenant_id=seed_tenant,
            endpoint_name="market.tesouraria",
            schedule_kind="daily_at",
            schedule_value="07:00",
            last_started_at=last_sp.astimezone(UTC),
        )
    )
    await db.commit()

    rows = await list_due_endpoints(db, now=now_sp.astimezone(UTC))
    names = {r.endpoint_name for r in rows if r.tenant_id == seed_tenant}
    assert "market.tesouraria" not in names


# ─────────────────────────────────────────────────────────────────────────────
# on_demand + disabled
# ─────────────────────────────────────────────────────────────────────────────


async def test_on_demand_never_appears(db: AsyncSession, seed_tenant: UUID):
    db.add(
        _make_row(
            tenant_id=seed_tenant,
            endpoint_name="market.outros_ativos",
            schedule_kind="on_demand",
            schedule_value=None,
            last_started_at=None,
        )
    )
    await db.commit()

    rows = await list_due_endpoints(db, now=datetime.now(UTC))
    names = {r.endpoint_name for r in rows if r.tenant_id == seed_tenant}
    assert "market.outros_ativos" not in names


async def test_disabled_never_appears(db: AsyncSession, seed_tenant: UUID):
    db.add(
        _make_row(
            tenant_id=seed_tenant,
            endpoint_name="market.demonstrativo_caixa",
            schedule_kind="interval",
            schedule_value="60",
            enabled=False,
            last_started_at=None,
        )
    )
    await db.commit()

    rows = await list_due_endpoints(db, now=datetime.now(UTC))
    names = {r.endpoint_name for r in rows if r.tenant_id == seed_tenant}
    assert "market.demonstrativo_caixa" not in names


# ─────────────────────────────────────────────────────────────────────────────
# Zombie / em_progresso
# ─────────────────────────────────────────────────────────────────────────────


async def test_em_progresso_recente_pula(db: AsyncSession, seed_tenant: UUID):
    """Sync ainda em curso ha 30min — nao dispara (zombie tolerance 2h)."""
    now = datetime.now(UTC)
    db.add(
        _make_row(
            tenant_id=seed_tenant,
            endpoint_name="market.conta_corrente",
            schedule_kind="interval",
            schedule_value="60",
            last_started_at=now - timedelta(minutes=30),
            last_status="em_progresso",
        )
    )
    await db.commit()

    rows = await list_due_endpoints(db, now=now)
    names = {r.endpoint_name for r in rows if r.tenant_id == seed_tenant}
    assert "market.conta_corrente" not in names


async def test_em_progresso_velho_dispara_novo(
    db: AsyncSession, seed_tenant: UUID
):
    """Em progresso ha mais de 2h e zombi — pode disparar de novo."""
    now = datetime.now(UTC)
    db.add(
        _make_row(
            tenant_id=seed_tenant,
            endpoint_name="bank_account.statement",
            schedule_kind="interval",
            schedule_value="60",
            last_started_at=now - timedelta(hours=3),
            last_status="em_progresso",
        )
    )
    await db.commit()

    rows = await list_due_endpoints(db, now=now)
    names = {r.endpoint_name for r in rows if r.tenant_id == seed_tenant}
    assert "bank_account.statement" in names
