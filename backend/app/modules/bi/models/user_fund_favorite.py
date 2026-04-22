"""UserFundFavorite: per-user list of favorite CVM funds (by CNPJ).

Scope: per tenant + per user. CLAUDE.md §10 requires `tenant_id` NOT NULL on
every domain table (defense in depth), even though user_id already implies a
tenant through the users FK. Keeping `tenant_id` also enables tenant-scoped
aggregate queries (e.g. most-favorited funds per tenant).

CNPJ is stored digits-only (VARCHAR(14)) for consistency with
`cvm_remote.tab_i.cnpj_fundo_classe`.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class UserFundFavorite(Base):
    """A fund (CNPJ) marked as favorite by a user inside a tenant."""

    __tablename__ = "user_fund_favorite"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "cnpj", name="pk_user_fund_favorite"),
        Index("ix_user_fund_favorite_tenant_user", "tenant_id", "user_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<UserFundFavorite tenant={self.tenant_id} "
            f"user={self.user_id} cnpj={self.cnpj}>"
        )
