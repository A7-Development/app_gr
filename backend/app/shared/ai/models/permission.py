"""UserAIPermission: per-user permission within the AI capability.

Parallel to `user_module_permission` but for AI. Checked by
`core/ai_guard.py::require_ai` after the tenant subscription check.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import AICapability


class UserAIPermission(Base):
    """Permission level a user has for the AI capability."""

    __tablename__ = "user_ai_permission"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission: Mapped[AICapability] = mapped_column(
        SAEnum(AICapability, name="ai_capability", native_enum=False, length=16),
        nullable=False,
        default=AICapability.NONE,
        server_default=AICapability.NONE.value,
    )

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
        return f"<UserAIPermission user={self.user_id} perm={self.permission.value}>"
