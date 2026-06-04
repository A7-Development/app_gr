"""Pydantic schemas for data-provider credentials (system-maintainer admin).

The `secret` is vendor-specific and **opaque** (encrypted as-is into
`provedor_dados_credencial.encrypted_payload`). Examples:
    BigDataCorp: {"access_token": "...", "token_id": "..."}
    Infosimples: {"api_key": "..."}
The plaintext secret is NEVER returned by Read schemas.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DataProviderRead(BaseModel):
    """A registered data provider (for the credential UI to pick from)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    enabled: bool


class DataProviderCredentialCreate(BaseModel):
    provider_id: UUID
    alias: str = Field(min_length=1, max_length=64)
    # Vendor-specific secret dict (ex.: BDC -> access_token + token_id).
    secret: dict[str, str]
    zdr_enabled: bool = False
    notes: str | None = None


class DataProviderCredentialUpdate(BaseModel):
    # When present, re-ciphers (merge over current). Other fields rotate flags.
    secret: dict[str, str] | None = None
    zdr_enabled: bool | None = None
    active: bool | None = None
    notes: str | None = None


class DataProviderCredentialRead(BaseModel):
    """Credential metadata — the plaintext secret is intentionally omitted."""

    id: UUID
    provider_id: UUID
    alias: str
    zdr_enabled: bool
    active: bool
    rotated_at: datetime | None
    notes: str | None
    created_at: datetime
