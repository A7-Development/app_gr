"""Pydantic schemas for tenant management (system maintainer)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import Module, TenantStatus


class TenantSubscriptionRead(BaseModel):
    """One tenant_module_subscription row, returned inside TenantRead."""

    module: Module
    enabled: bool
    enabled_since: datetime | None
    enabled_until: datetime | None
    plan_ref: str | None


class TenantRead(BaseModel):
    """A tenant row + summary of subscriptions."""

    id: UUID
    slug: str
    name: str
    subdomain: str | None
    status: TenantStatus
    trial_ends_at: datetime | None
    is_system_maintainer: bool
    ativo: bool
    created_at: datetime
    updated_at: datetime
    subscriptions: list[TenantSubscriptionRead] = Field(default_factory=list)
    user_count: int = 0


class TenantCreate(BaseModel):
    """POST /admin/tenants payload.

    Creates a tenant AND immediately generates an invitation for the first
    Owner (email-based). The invitation token is returned in the response
    so the maintainer can hand it over to the invitee.
    """

    slug: str = Field(
        ..., min_length=2, max_length=100, pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$"
    )
    name: str = Field(..., min_length=2, max_length=255)
    subdomain: str | None = Field(default=None, max_length=100)
    status: TenantStatus = TenantStatus.ACTIVE
    trial_ends_at: datetime | None = None
    owner_email: EmailStr
    enabled_modules: list[Module] = Field(default_factory=list)


class TenantUpdate(BaseModel):
    """PATCH /admin/tenants/{id} payload — all fields optional."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    subdomain: str | None = Field(default=None, max_length=100)
    status: TenantStatus | None = None
    trial_ends_at: datetime | None = None
    ativo: bool | None = None


class TenantSubscriptionUpdate(BaseModel):
    """PUT /admin/tenants/{id}/subscriptions/{module} payload."""

    enabled: bool
    plan_ref: str | None = None
    enabled_until: datetime | None = None
