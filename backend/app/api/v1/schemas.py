"""Pydantic schemas for cross-cutting endpoints (auth, audit, health)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class HealthResponse(BaseModel):
    """GET /health response."""

    status: str = "ok"
    version: str
    environment: str


class LoginRequest(BaseModel):
    """POST /auth/login payload.

    `tenant_slug` is optional. Omitted: server picks the unique match by
    email; if the email exists in N tenants, server returns 409 listing the
    slugs so the client can resubmit with the chosen one.
    """

    email: EmailStr
    password: str = Field(..., min_length=1)
    tenant_slug: str | None = Field(default=None, max_length=100)


class LoginResponse(BaseModel):
    """POST /auth/login response."""

    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class TenantInfo(BaseModel):
    """Tenant summary returned by /auth/me."""

    id: UUID
    slug: str
    name: str
    status: str = "active"
    is_system_maintainer: bool = False


class UserInfo(BaseModel):
    """User summary returned by /auth/me."""

    id: UUID
    email: str
    name: str
    tenant_role: str = "member"


class MeResponse(BaseModel):
    """GET /auth/me response. Frontend uses this to render the sidebar.

    AI capability fields (`ai_enabled`, `ai_permission`) are independent of
    `enabled_modules` / `user_permissions` because AI is a transversal capability,
    not a module (CLAUDE.md sec 19).
    """

    user: UserInfo
    tenant: TenantInfo
    enabled_modules: list[str]
    user_permissions: dict[str, str]
    ai_enabled: bool = False
    ai_permission: str = "none"


class AuditPingResponse(BaseModel):
    """GET /audit/ping response — template showing the provenance pattern.

    Every analytical endpoint should follow this shape: data + metadata on origin.
    """

    value: float
    label: str
    # Proveniencia (this is the template for how BI endpoints will look)
    source_type: str
    source_id: str
    ingested_at: datetime
    source_updated_at: datetime | None
    trust_level: str
    ingested_by_version: str
