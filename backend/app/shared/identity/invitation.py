"""UserInvitation: pending invite to join a tenant.

A user is never "created with a password" by an admin. The Owner of a tenant
(or a system maintainer creating the first Owner) generates an invitation;
the invited person opens the link, sets their own name + password and the
invitation is accepted — at which point the `User` row is created and the
default permissions of the chosen role are materialized.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import TenantRole


class UserInvitation(Base):
    """A pending invitation to join a tenant.

    Token is stored as a bcrypt hash so a leak of the table does not allow
    accepting invitations. The plaintext token is only ever returned to the
    inviter (or sent by email) at creation time.
    """

    __tablename__ = "user_invitation"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[TenantRole] = mapped_column(
        SAEnum(TenantRole, name="tenant_role", native_enum=False, length=16),
        nullable=False,
    )

    # Bcrypt hash of the URL token. Plaintext token is only ever returned at
    # creation time (or sent by email).
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    invited_by_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
        return (
            f"<UserInvitation tenant={self.tenant_id} email={self.email!r} "
            f"role={self.role.value} accepted={self.accepted_at is not None}>"
        )
