"""UserModulePermission: per-user per-module RBAC."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import Module, Permission


class UserModulePermission(Base):
    """Permission level a user has inside a given module.

    Checked by `require_module` after subscription check.
    Insufficient permission -> HTTP 403 Forbidden.
    """

    __tablename__ = "user_module_permission"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    module: Mapped[Module] = mapped_column(
        SAEnum(Module, name="module", native_enum=False, length=32),
        primary_key=True,
    )
    permission: Mapped[Permission] = mapped_column(
        SAEnum(Permission, name="permission", native_enum=False, length=16),
        nullable=False,
        default=Permission.NONE,
        server_default=Permission.NONE.value,
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

    user: Mapped["User"] = relationship(back_populates="module_permissions")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<UserPerm user={self.user_id} "
            f"module={self.module.value} perm={self.permission.value}>"
        )
