"""CRUD of tenants (system maintainer only).

Onboarding flow (handheld B2B, per CLAUDE.md decision 2026-05-18):

    POST /admin/tenants
        body: { slug, name, owner_email, enabled_modules: [...] }
        ->  cria tenant + N tenant_module_subscription(enabled=true)
        ->  cria invitation pro owner_email com role=OWNER
        ->  retorna TenantRead + invitation_url

A7 (maintainer) repassa o invitation_url pro 1o Owner do tenant; ele aceita
e ja entra como Owner. Owner convida o resto do time dele.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.enums import Module, Permission, TenantRole
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.admin.schemas.invitation import (
    InvitationCreateResponse,
    InvitationRead,
)
from app.modules.admin.schemas.tenant import (
    TenantCreate,
    TenantRead,
    TenantSubscriptionRead,
    TenantSubscriptionUpdate,
    TenantUpdate,
)
from app.shared.identity.invitations_service import create_invitation
from app.shared.identity.subscription import TenantModuleSubscription
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User

router = APIRouter(prefix="/tenants", tags=["admin:tenants"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]

_settings = get_settings()


async def _serialize(db: AsyncSession, tenant: Tenant) -> TenantRead:
    """Hydrate a tenant row into the response shape (with subs + user count)."""
    subs = (
        await db.execute(
            select(TenantModuleSubscription).where(
                TenantModuleSubscription.tenant_id == tenant.id
            )
        )
    ).scalars().all()

    user_count = (
        await db.execute(
            select(func.count(User.id)).where(User.tenant_id == tenant.id)
        )
    ).scalar_one()

    return TenantRead(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        subdomain=tenant.subdomain,
        status=tenant.status,
        trial_ends_at=tenant.trial_ends_at,
        is_system_maintainer=tenant.is_system_maintainer,
        ativo=tenant.ativo,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        subscriptions=[
            TenantSubscriptionRead(
                module=s.module,
                enabled=s.enabled,
                enabled_since=s.enabled_since,
                enabled_until=s.enabled_until,
                plan_ref=s.plan_ref,
            )
            for s in subs
        ],
        user_count=int(user_count),
    )


# ---------------------------------------------------------------------------
# LIST / GET
# ---------------------------------------------------------------------------


@router.get("", response_model=list[TenantRead], dependencies=_GUARD)
async def list_tenants(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TenantRead]:
    """List all tenants — system maintainer only."""
    rows = (
        await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    ).scalars().all()
    return [await _serialize(db, t) for t in rows]


@router.get("/{tenant_id}", response_model=TenantRead, dependencies=_GUARD)
async def get_tenant(
    tenant_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantRead:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nao encontrado."
        )
    return await _serialize(db, tenant)


# ---------------------------------------------------------------------------
# CREATE — tenant + initial Owner invitation
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_GUARD,
)
async def create_tenant(
    payload: TenantCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationCreateResponse:
    """Create a tenant + first Owner invitation.

    Returns the invitation token + accept URL. The maintainer is responsible
    for forwarding the URL to the invitee (email integration comes later).
    """
    # 1. Tenant row
    tenant = Tenant(
        slug=payload.slug,
        name=payload.name,
        subdomain=payload.subdomain,
        status=payload.status,
        trial_ends_at=payload.trial_ends_at,
    )
    db.add(tenant)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug '{payload.slug}' ou subdomain ja existe.",
        ) from e

    # 2. Subscriptions
    now = datetime.now(UTC)
    for module in payload.enabled_modules:
        db.add(
            TenantModuleSubscription(
                tenant_id=tenant.id,
                module=module,
                enabled=True,
                enabled_since=now,
            )
        )

    # 3. Owner invitation
    invitation, plaintext_token = await create_invitation(
        db,
        tenant_id=tenant.id,
        email=payload.owner_email,
        role=TenantRole.OWNER,
        invited_by_id=principal.user_id,
    )

    await db.commit()
    await db.refresh(tenant)
    await db.refresh(invitation)

    accept_url = f"{_settings.APP_BASE_URL.rstrip('/')}/invitations/{plaintext_token}"

    return InvitationCreateResponse(
        invitation=InvitationRead(
            id=invitation.id,
            tenant_id=invitation.tenant_id,
            email=invitation.email,
            role=invitation.role,
            invited_by_id=invitation.invited_by_id,
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
            revoked_at=invitation.revoked_at,
            created_at=invitation.created_at,
        ),
        token=plaintext_token,
        accept_url=accept_url,
    )


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


@router.patch("/{tenant_id}", response_model=TenantRead, dependencies=_GUARD)
async def update_tenant(
    tenant_id: UUID,
    payload: TenantUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantRead:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nao encontrado."
        )
    # Block neutering the maintainer accidentally — that flag is one-way.
    if tenant.is_system_maintainer and payload.status is not None and payload.status.value in {"suspended", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nao e possivel suspender/cancelar o tenant mantenedor.",
        )

    if payload.name is not None:
        tenant.name = payload.name
    if payload.subdomain is not None:
        tenant.subdomain = payload.subdomain
    if payload.status is not None:
        tenant.status = payload.status
    if payload.trial_ends_at is not None:
        tenant.trial_ends_at = payload.trial_ends_at
    if payload.ativo is not None:
        tenant.ativo = payload.ativo

    await db.commit()
    await db.refresh(tenant)
    return await _serialize(db, tenant)


# ---------------------------------------------------------------------------
# SUBSCRIPTIONS — toggle module enabled/disabled
# ---------------------------------------------------------------------------


@router.put(
    "/{tenant_id}/subscriptions/{module}",
    response_model=TenantSubscriptionRead,
    dependencies=_GUARD,
)
async def upsert_subscription(
    tenant_id: UUID,
    module: Module,
    payload: TenantSubscriptionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantSubscriptionRead:
    """Enable/disable a module for a tenant.

    Idempotent. Updates `enabled_since` only when transitioning false->true.
    Does NOT touch existing `user_module_permission` rows — those need to be
    granted explicitly via the Owner UI (or apply_role_defaults on user
    creation).
    """
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant nao encontrado."
        )

    sub = (
        await db.execute(
            select(TenantModuleSubscription).where(
                TenantModuleSubscription.tenant_id == tenant_id,
                TenantModuleSubscription.module == module,
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if sub is None:
        sub = TenantModuleSubscription(
            tenant_id=tenant_id,
            module=module,
            enabled=payload.enabled,
            enabled_since=now if payload.enabled else None,
            enabled_until=payload.enabled_until,
            plan_ref=payload.plan_ref,
        )
        db.add(sub)
    else:
        was_enabled = sub.enabled
        sub.enabled = payload.enabled
        if payload.enabled and not was_enabled:
            sub.enabled_since = now
        sub.enabled_until = payload.enabled_until
        sub.plan_ref = payload.plan_ref

    await db.commit()
    await db.refresh(sub)

    return TenantSubscriptionRead(
        module=sub.module,
        enabled=sub.enabled,
        enabled_since=sub.enabled_since,
        enabled_until=sub.enabled_until,
        plan_ref=sub.plan_ref,
    )
