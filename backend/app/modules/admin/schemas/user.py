"""Pydantic schemas for user management inside a tenant (Owner)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.core.enums import Module, Permission, TenantRole


class UserPermissionRead(BaseModel):
    """One row of `user_module_permission`."""

    module: Module
    permission: Permission


class UserRead(BaseModel):
    """A user row + summary of module permissions."""

    id: UUID
    tenant_id: UUID
    email: EmailStr
    name: str
    tenant_role: TenantRole
    ativo: bool
    last_login_at: datetime | None
    email_verified_at: datetime | None
    invited_by_id: UUID | None
    created_at: datetime
    permissions: list[UserPermissionRead] = []


class UserUpdate(BaseModel):
    """PATCH /admin/users/{id} payload — all fields optional."""

    name: str | None = None
    ativo: bool | None = None
    tenant_role: TenantRole | None = None


class UserPermissionUpdate(BaseModel):
    """PUT /admin/users/{id}/permissions/{module} payload (Owner override)."""

    permission: Permission
