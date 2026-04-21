"""Authentication endpoints (cross-cutting, not module-specific)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    TenantInfo,
    UserInfo,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.identity.subscription import TenantModuleSubscription
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission

router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    """Authenticate user by email+password and return a JWT."""
    # Note: MVP login nao e tenant-scoped — usa o primeiro match por email.
    # Em Etapa G (spinoff multi-tenant), adicionar tenant_slug ao payload e filtrar.
    stmt = select(User).where(User.email == payload.email, User.ativo.is_(True))
    user = (await db.execute(stmt)).scalars().first()

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha invalidos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.last_login_at = datetime.now(UTC)
    await db.commit()

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
    )
    return LoginResponse(
        access_token=token,
        expires_in_minutes=_settings.JWT_EXPIRE_MINUTES,
    )


@router.get("/me", response_model=MeResponse)
async def me(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeResponse:
    """Return authenticated user + tenant + enabled_modules + user_permissions.

    Frontend uses this to render the sidebar and enforce module visibility.
    Backend also validates on every request (defense in depth).
    """
    user_stmt = select(User).where(User.id == principal.user_id)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario nao encontrado",
        )

    tenant_stmt = select(Tenant).where(Tenant.id == principal.tenant_id)
    tenant = (await db.execute(tenant_stmt)).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant nao encontrado",
        )

    sub_stmt = select(TenantModuleSubscription).where(
        TenantModuleSubscription.tenant_id == principal.tenant_id,
        TenantModuleSubscription.enabled.is_(True),
    )
    enabled_modules = [s.module.value for s in (await db.execute(sub_stmt)).scalars().all()]

    perm_stmt = select(UserModulePermission).where(
        UserModulePermission.user_id == principal.user_id
    )
    user_permissions = {
        p.module.value: p.permission.value for p in (await db.execute(perm_stmt)).scalars().all()
    }

    return MeResponse(
        user=UserInfo(id=user.id, email=user.email, name=user.name),
        tenant=TenantInfo(id=tenant.id, slug=tenant.slug, name=tenant.name),
        enabled_modules=enabled_modules,
        user_permissions=user_permissions,
    )
