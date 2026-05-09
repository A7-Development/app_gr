"""AIProviderCredential: globally-managed LLM provider keys.

This is a GLOBAL table (no tenant_id) — exception to CLAUDE.md sec 10.
Only the single tenant marked `is_system_maintainer=true` can manage rows
here, gated by `core/system_maintainer_guard.py::require_system_maintainer`.

Encryption reuses `app.shared.crypto.envelope` (Fernet KEK + DEK), same
pattern as `tenant_source_config.config`.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import AIProvider


class AIProviderCredential(Base):
    """A single API key for an LLM provider, encrypted at rest.

    Multiple credentials per provider are allowed (e.g. one for prod, one for EU,
    one with ZDR contract). The adapter picks an active one at call time.
    """

    __tablename__ = "ai_provider_credential"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    provider: Mapped[AIProvider] = mapped_column(
        SAEnum(AIProvider, name="ai_provider", native_enum=False, length=32),
        nullable=False,
        index=True,
    )
    alias: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # Envelope-encrypted JSON dict like {"api_key": "sk-...", "org_id": "..."}
    encrypted_key: Mapped[dict] = mapped_column(JSONB, nullable=False)

    zdr_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )

    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<AIProviderCredential id={self.id} provider={self.provider.value} "
            f"alias={self.alias!r} active={self.active}>"
        )
