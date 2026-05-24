"""PlaybookDefinition + PlaybookDefinitionActive.

A `PlaybookDefinition` is an immutable versioned record of a workflow graph
(nodes + edges) stored as JSONB. Every edit creates a new version (new row)
preserving full audit trail. The currently-active version per (name, tenant)
is pointed to by `PlaybookDefinitionActive` — a single UPDATE flips the
active version (1-click rollback, no deploy needed).

Multi-tenant model:
- `tenant_id` NULL = template provided by Strata (e.g. A7 standard) that any
  tenant can clone.
- `tenant_id` not NULL = workflow owned by that tenant; only that tenant
  can see/edit/run.

Naming: `category.name` (e.g. `credit.a7_standard`, `risk.fraud_baseline`).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import PlaybookStatus


class PlaybookDefinition(Base):
    """One immutable version of a workflow graph (nodes + edges in JSONB)."""

    __tablename__ = "workflow_definition"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Tenant scope: NULL = Strata template, otherwise tenant-owned.
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)  # 'credit', 'risk', etc.

    # The graph: { "nodes": [...], "edges": [...] }
    # See `app/shared/workflow/schemas/definition.py` for the exact shape.
    graph: Mapped[dict] = mapped_column(JSONB, nullable=False)

    status: Mapped[PlaybookStatus] = mapped_column(
        SAEnum(
            PlaybookStatus,
            name="workflow_status",
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=PlaybookStatus.DRAFT,
    )

    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "version", name="uq_workflow_definition_name_version"),
    )

    def __repr__(self) -> str:
        scope = f"tenant={self.tenant_id}" if self.tenant_id else "template"
        return f"<PlaybookDefinition {self.name}@v{self.version} ({scope})>"


class PlaybookDefinitionActive(Base):
    """Pointer to the currently-active version of a workflow per (name, tenant).

    Updating this row is the only way to "publish" a new version — atomic
    1-click rollback, no deploy needed.

    Uniqueness on (name, tenant_id) uses NULLS NOT DISTINCT (Postgres 15+)
    so a single Strata template (`tenant_id IS NULL`) for a given name is
    enforced.
    """

    __tablename__ = "workflow_definition_active"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )

    active_definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    activated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "name",
            "tenant_id",
            name="uq_workflow_definition_active_name_tenant",
            postgresql_nulls_not_distinct=True,
        ),
    )

    def __repr__(self) -> str:
        scope = f"tenant={self.tenant_id}" if self.tenant_id else "template"
        return f"<PlaybookDefinitionActive {self.name} ({scope}) -> {self.active_definition_id}>"
