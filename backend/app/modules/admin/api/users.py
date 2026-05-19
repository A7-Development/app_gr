"""Gestao de usuarios DENTRO de um tenant (Owner only).

Listar/convidar/desativar/editar role e permissoes dos users do proprio
tenant do principal. Endpoints isolam por `tenant_id = principal.tenant_id` —
o Owner nao consegue ver/mexer em users de outro tenant (mesmo que o tenant
seja system_maintainer, ele continua scoped ao seu proprio tenant aqui;
gerencia cross-tenant fica em /admin/tenants e endpoints futuros).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.enums import Module, Permission, TenantRole
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.admin.schemas.invitation import (
    InvitationCreate,
    InvitationCreateResponse,
    InvitationRead,
)
from app.modules.admin.schemas.user import (
    UserPermissionRead,
    UserPermissionUpdate,
    UserRead,
    UserUpdate,
)
from app.shared.identity.invitation import UserInvitation
from app.shared.identity.invitations_service import (
    create_invitation,
)
from app.shared.identity.invitations_service import (
    revoke as revoke_invitation,
)
from app.shared.identity.role_defaults import (
    LastOwnerError,
    apply_role_defaults,
    assert_not_last_owner,
)
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission

router = APIRouter(tags=["admin:users"])

# Gestao de users do proprio tenant requer Module.ADMIN/ADMIN. O check
# adicional de tenant_role=OWNER e feito por dependencia inline (ver
# _assert_owner) — separa "tenant tem ADMIN.ADMIN no user" de "este user e
# Owner do tenant", duas dimensoes diferentes.
_BASE_GUARD = [Depends(require_module(Module.ADMIN, Permission.ADMIN))]

_settings = get_settings()


async def _assert_owner(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Reject the request if the principal is not Owner of their tenant."""
    user = await db.get(User, principal.user_id)
    if user is None or user.tenant_role != TenantRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas Owners do tenant podem gerenciar usuarios.",
        )


_OWNER_GUARD = [*_BASE_GUARD, Depends(_assert_owner)]


async def _user_with_perms(db: AsyncSession, user: User) -> UserRead:
    perms = (
        await db.execute(
            select(UserModulePermission).where(
                UserModulePermission.user_id == user.id
            )
        )
    ).scalars().all()
    return UserRead(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        tenant_role=user.tenant_role,
        ativo=user.ativo,
        last_login_at=user.last_login_at,
        email_verified_at=user.email_verified_at,
        invited_by_id=user.invited_by_id,
        created_at=user.created_at,
        permissions=[
            UserPermissionRead(module=p.module, permission=p.permission)
            for p in perms
        ],
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserRead], dependencies=_OWNER_GUARD)
async def list_users(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserRead]:
    rows = (
        await db.execute(
            select(User)
            .where(User.tenant_id == principal.tenant_id)
            .order_by(User.created_at.desc())
        )
    ).scalars().all()
    return [await _user_with_perms(db, u) for u in rows]


@router.get(
    "/users/{user_id}", response_model=UserRead, dependencies=_OWNER_GUARD
)
async def get_user(
    user_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserRead:
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado."
        )
    return await _user_with_perms(db, user)


@router.patch(
    "/users/{user_id}", response_model=UserRead, dependencies=_OWNER_GUARD
)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserRead:
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado."
        )

    # If we are about to take this user out of the Owner pool (demote or
    # deactivate), block when it is the last active Owner.
    will_demote = (
        payload.tenant_role is not None
        and payload.tenant_role != TenantRole.OWNER
        and user.tenant_role == TenantRole.OWNER
    )
    will_deactivate = payload.ativo is False and user.ativo
    if will_demote or will_deactivate:
        try:
            await assert_not_last_owner(db, user=user)
        except LastOwnerError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            ) from e

    role_changed = (
        payload.tenant_role is not None and payload.tenant_role != user.tenant_role
    )

    if payload.name is not None:
        user.name = payload.name
    if payload.ativo is not None:
        user.ativo = payload.ativo
    if payload.tenant_role is not None:
        user.tenant_role = payload.tenant_role

    # Role change re-materializes the user_module_permission rows from the
    # new role x current subscriptions. Manual overrides made by Owner are
    # intentionally clobbered — that is the price of changing the role.
    if role_changed:
        await apply_role_defaults(db, user=user, overwrite=True)

    await db.commit()
    await db.refresh(user)
    return await _user_with_perms(db, user)


@router.put(
    "/users/{user_id}/permissions/{module}",
    response_model=UserPermissionRead,
    dependencies=_OWNER_GUARD,
)
async def upsert_user_permission(
    user_id: UUID,
    module: Module,
    payload: UserPermissionUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPermissionRead:
    """Manually override one (user, module) permission level.

    This is the escape hatch above the role-default matrix. Use sparingly —
    "Member" + sprinkle of overrides is the typical pattern when a single
    user needs WRITE in a module Members don't get.
    """
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado."
        )

    # If we are about to NONE-out a module on an Owner -> not blocked, but
    # weird (Owner with no perm). UI should warn; we don't enforce here.

    stmt = (
        pg_insert(UserModulePermission)
        .values(user_id=user.id, module=module, permission=payload.permission)
        .on_conflict_do_update(
            index_elements=["user_id", "module"],
            set_={"permission": payload.permission},
        )
    )
    await db.execute(stmt)
    await db.commit()
    return UserPermissionRead(module=module, permission=payload.permission)


# ---------------------------------------------------------------------------
# Invitations (gerenciamento pelo Owner do tenant)
# ---------------------------------------------------------------------------


@router.get(
    "/users/invitations",
    response_model=list[InvitationRead],
    dependencies=_OWNER_GUARD,
)
async def list_invitations(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InvitationRead]:
    """List invitations of the principal's tenant (open + historical)."""
    rows = (
        await db.execute(
            select(UserInvitation)
            .where(UserInvitation.tenant_id == principal.tenant_id)
            .order_by(UserInvitation.created_at.desc())
        )
    ).scalars().all()
    return [
        InvitationRead(
            id=r.id,
            tenant_id=r.tenant_id,
            email=r.email,
            role=r.role,
            invited_by_id=r.invited_by_id,
            expires_at=r.expires_at,
            accepted_at=r.accepted_at,
            revoked_at=r.revoked_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post(
    "/users/invitations",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_OWNER_GUARD,
)
async def invite_user(
    payload: InvitationCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationCreateResponse:
    """Invite a new user to the Owner's tenant.

    If an active user with this email already exists in the tenant, returns
    409 — the Owner should edit the existing user instead.
    """
    existing = (
        await db.execute(
            select(User).where(
                User.tenant_id == principal.tenant_id,
                User.email == payload.email,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ja existe um usuario com este email no tenant.",
        )

    invitation, plaintext_token = await create_invitation(
        db,
        tenant_id=principal.tenant_id,
        email=payload.email,
        role=payload.role,
        invited_by_id=principal.user_id,
    )
    await db.commit()
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


@router.delete(
    "/users/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_OWNER_GUARD,
)
async def cancel_invitation(
    invitation_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke a pending invitation."""
    invitation = await db.get(UserInvitation, invitation_id)
    if invitation is None or invitation.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Convite nao encontrado."
        )
    if invitation.accepted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Convite ja aceito — nao pode ser cancelado.",
        )
    await revoke_invitation(db, invitation)
    await db.commit()
