"""Public invitation endpoints (no auth).

GET  /invitations/{token}          -> retorna contexto pra renderizar a pagina
POST /invitations/{token}/accept   -> cria User, aceita invitation, retorna JWT

The accept endpoint is rate-limited at the gateway in prod (10 req/min/IP);
in dev no rate limit. Brute-forcing the token is also bound by bcrypt cost.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import LoginResponse
from app.core.config import get_settings
from app.core.database import get_db
from app.core.enums import TenantStatus
from app.core.security import create_access_token, hash_password
from app.modules.admin.schemas.invitation import (
    InvitationAcceptRequest,
    InvitationContext,
)
from app.shared.identity.invitations_service import (
    InvitationAlreadyConsumed,
    InvitationExpired,
    InvitationNotFound,
    find_open_by_token,
    mark_accepted,
)
from app.shared.identity.role_defaults import apply_role_defaults
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User

router = APIRouter(prefix="/invitations", tags=["invitations"])

_settings = get_settings()


def _map_invitation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvitationNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Convite nao encontrado."
        )
    if isinstance(exc, InvitationExpired):
        return HTTPException(
            status_code=status.HTTP_410_GONE, detail="Convite expirado."
        )
    if isinstance(exc, InvitationAlreadyConsumed):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este convite ja foi aceito ou cancelado.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Falha ao processar convite.",
    )


@router.get("/{token}", response_model=InvitationContext)
async def get_invitation_context(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationContext:
    """Return non-sensitive context for rendering the accept page."""
    try:
        invitation = await find_open_by_token(db, token)
    except (InvitationNotFound, InvitationExpired, InvitationAlreadyConsumed) as e:
        raise _map_invitation_error(e) from e

    tenant = await db.get(Tenant, invitation.tenant_id)
    if tenant is None:  # tenant deletado entre o convite e o aceite
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="O tenant deste convite nao existe mais.",
        )

    return InvitationContext(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
    )


@router.post(
    "/{token}/accept",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_invitation(
    token: str,
    payload: InvitationAcceptRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    """Accept an invitation: create the user and return a session token."""
    try:
        invitation = await find_open_by_token(db, token)
    except (InvitationNotFound, InvitationExpired, InvitationAlreadyConsumed) as e:
        raise _map_invitation_error(e) from e

    tenant = await db.get(Tenant, invitation.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="O tenant deste convite nao existe mais.",
        )
    if tenant.status in {TenantStatus.SUSPENDED, TenantStatus.CANCELLED}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant esta {tenant.status.value} — convite nao pode ser aceito.",
        )

    # Guard: email collision inside the tenant (someone else accepted faster
    # or the same email got invited twice and one of them already accepted).
    existing = (
        await db.execute(
            select(User).where(
                User.tenant_id == invitation.tenant_id,
                User.email == invitation.email,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Mark invitation accepted (so it stops being valid) and fail.
        await mark_accepted(db, invitation)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ja existe um usuario com este email no tenant.",
        )

    user = User(
        tenant_id=invitation.tenant_id,
        email=invitation.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        tenant_role=invitation.role,
        invited_by_id=invitation.invited_by_id,
        email_verified_at=datetime.now(UTC),  # email proof = aceitou o convite
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    await db.flush()

    # Materialize permissions from role x enabled subscriptions.
    await apply_role_defaults(db, user=user, overwrite=True)

    await mark_accepted(db, invitation)
    await db.commit()
    await db.refresh(user)

    token_str = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
    )
    return LoginResponse(
        access_token=token_str,
        expires_in_minutes=_settings.JWT_EXPIRE_MINUTES,
    )
