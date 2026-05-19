"""Pydantic schemas for admin endpoints (tenants, users, invitations)."""

from app.modules.admin.schemas.invitation import (
    InvitationAcceptRequest,
    InvitationContext,
    InvitationCreate,
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
from app.modules.admin.schemas.user import (
    UserPermissionRead,
    UserPermissionUpdate,
    UserRead,
    UserUpdate,
)

__all__ = [
    # invitation
    "InvitationAcceptRequest",
    "InvitationContext",
    "InvitationCreate",
    "InvitationCreateResponse",
    "InvitationRead",
    # tenant
    "TenantCreate",
    "TenantRead",
    "TenantSubscriptionRead",
    "TenantSubscriptionUpdate",
    "TenantUpdate",
    # user
    "UserPermissionRead",
    "UserPermissionUpdate",
    "UserRead",
    "UserUpdate",
]
