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
    """POST /auth/login payload."""

    email: EmailStr
    password: str = Field(..., min_length=1)


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


class UserInfo(BaseModel):
    """User summary returned by /auth/me."""

    id: UUID
    email: str
    name: str


class MeResponse(BaseModel):
    """GET /auth/me response. Frontend uses this to render the sidebar."""

    user: UserInfo
    tenant: TenantInfo
    enabled_modules: list[str]
    user_permissions: dict[str, str]


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
