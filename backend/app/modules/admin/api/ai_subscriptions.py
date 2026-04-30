"""Manage AI subscription tier and per-user permissions for each tenant.

System maintainer only. Endpoints here let the maintainer set:
    - Whether the tenant has AI enabled.
    - Which plan (`plan_ref`).
    - Monthly credit quota.
    - Hard cap in BRL/day.
    - Which users in the tenant get READ vs ADMIN AI permission.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import AICapability, Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.shared.ai.models.credit_balance import AICreditBalance
from app.shared.ai.models.permission import UserAIPermission
from app.shared.ai.models.subscription import TenantAISubscription
from app.shared.ai.schemas import (
    TenantAISubscriptionRead,
    TenantAISubscriptionUpdate,
    TopupRequest,
)
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User

router = APIRouter(prefix="/ai/subscriptions", tags=["admin:ai-subscriptions"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


@router.get(
    "/{tenant_id}",
    response_model=TenantAISubscriptionRead,
    dependencies=_GUARD,
)
async def get_subscription(
    tenant_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantAISubscriptionRead:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nao encontrado."
        )

    sub = (
        await db.execute(
            select(TenantAISubscription).where(
                TenantAISubscription.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()

    user_perms = (
        await db.execute(
            select(UserAIPermission, User)
            .join(User, User.id == UserAIPermission.user_id)
            .where(User.tenant_id == tenant_id)
        )
    ).all()

    return TenantAISubscriptionRead(
        tenant_id=tenant_id,
        enabled=sub.enabled if sub else False,
        plan_ref=sub.plan_ref if sub else None,
        monthly_credit_quota=sub.monthly_credit_quota if sub else 0,
        hard_cap_brl=sub.hard_cap_brl if sub else None,
        enabled_since=sub.enabled_since if sub else None,
        enabled_until=sub.enabled_until if sub else None,
        user_permissions={str(perm.user_id): perm.permission for perm, _ in user_perms},
    )


@router.put(
    "/{tenant_id}",
    response_model=TenantAISubscriptionRead,
    dependencies=_GUARD,
)
async def upsert_subscription(
    tenant_id: UUID,
    payload: TenantAISubscriptionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantAISubscriptionRead:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nao encontrado."
        )

    now = datetime.now(UTC)
    stmt = pg_insert(TenantAISubscription).values(
        tenant_id=tenant_id,
        enabled=payload.enabled,
        plan_ref=payload.plan_ref,
        monthly_credit_quota=payload.monthly_credit_quota,
        hard_cap_brl=payload.hard_cap_brl,
        enabled_since=now if payload.enabled else None,
        enabled_until=payload.enabled_until,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id"],
        set_={
            "enabled": payload.enabled,
            "plan_ref": payload.plan_ref,
            "monthly_credit_quota": payload.monthly_credit_quota,
            "hard_cap_brl": payload.hard_cap_brl,
            "enabled_until": payload.enabled_until,
        },
    )
    await db.execute(stmt)

    # Apply per-user permissions (additive — doesn't downgrade users not listed).
    await _grant_permissions(
        db, tenant_id, payload.grant_user_admin_to, AICapability.ADMIN
    )
    await _grant_permissions(
        db, tenant_id, payload.grant_user_read_to, AICapability.READ
    )

    await db.commit()
    return await get_subscription(tenant_id, db)  # re-read


async def _grant_permissions(
    db: AsyncSession, tenant_id: UUID, user_ids: list[UUID], cap: AICapability
) -> None:
    if not user_ids:
        return
    rows = (
        await db.execute(
            select(User.id).where(User.tenant_id == tenant_id, User.id.in_(user_ids))
        )
    ).scalars().all()
    valid_ids = set(rows)
    for uid in valid_ids:
        stmt = pg_insert(UserAIPermission).values(user_id=uid, permission=cap)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"], set_={"permission": cap}
        )
        await db.execute(stmt)


@router.post(
    "/{tenant_id}/topup",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_GUARD,
)
async def topup_credits(
    tenant_id: UUID,
    payload: TopupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nao encontrado."
        )

    period = datetime.now(UTC).strftime("%Y-%m")
    stmt = pg_insert(AICreditBalance).values(
        tenant_id=tenant_id,
        period_yyyymm=period,
        granted=0,
        topup=payload.credits,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "period_yyyymm"],
        set_={"topup": AICreditBalance.topup + payload.credits},
    )
    await db.execute(stmt)
    await db.commit()
