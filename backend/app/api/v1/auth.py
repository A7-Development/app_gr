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
from app.core.enums import AICapability, TenantStatus
from app.core.security import create_access_token, verify_password
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.models.permission import UserAIPermission
from app.shared.ai.models.subscription import TenantAISubscription
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
    """Authenticate user by email+password and return a JWT.

    Multi-tenant resolution:
        - email + tenant_slug -> filtra pelo tenant especifico.
        - email so -> se houver match unico, autentica direto. Se houver N
          matches em N tenants distintos, retorna HTTP 409 com a lista de
          slugs disponiveis pra o cliente reenviar com tenant_slug.
    """
    base_stmt = (
        select(User, Tenant)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(User.email == payload.email, User.ativo.is_(True))
    )
    if payload.tenant_slug:
        base_stmt = base_stmt.where(Tenant.slug == payload.tenant_slug)

    rows = (await db.execute(base_stmt)).all()

    if len(rows) > 1:
        slugs = sorted({t.slug for _, t in rows})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Este email pertence a varios tenants. Informe `tenant_slug`.",
                "tenant_slugs": slugs,
            },
        )

    pair = rows[0] if rows else None
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha invalidos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, tenant = pair

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha invalidos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if tenant.status in {TenantStatus.SUSPENDED, TenantStatus.CANCELLED} or not tenant.ativo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant '{tenant.slug}' esta {tenant.status.value}.",
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

    # AI capability — transversal, lives outside the closed Module enum.
    ai_sub = (
        await db.execute(
            select(TenantAISubscription).where(
                TenantAISubscription.tenant_id == principal.tenant_id
            )
        )
    ).scalar_one_or_none()
    ai_enabled = bool(ai_sub and ai_sub.enabled)

    ai_perm = (
        await db.execute(
            select(UserAIPermission).where(UserAIPermission.user_id == principal.user_id)
        )
    ).scalar_one_or_none()
    ai_permission = (ai_perm.permission if ai_perm else AICapability.NONE).value

    return MeResponse(
        user=UserInfo(
            id=user.id,
            email=user.email,
            name=user.name,
            tenant_role=user.tenant_role.value,
        ),
        tenant=TenantInfo(
            id=tenant.id,
            slug=tenant.slug,
            name=tenant.name,
            status=tenant.status.value,
            is_system_maintainer=tenant.is_system_maintainer,
        ),
        enabled_modules=enabled_modules,
        user_permissions=user_permissions,
        ai_enabled=ai_enabled,
        ai_permission=ai_permission,
    )
