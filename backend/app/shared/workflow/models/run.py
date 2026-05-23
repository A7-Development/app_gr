"""PlaybookRun + PlaybookRunStep.

`PlaybookRun` represents one execution of a `PlaybookDefinition`. It carries
the accumulated context (outputs from completed nodes) plus the lifecycle
status (running, paused on human_review, completed, failed).

`PlaybookRunStep` is one row per node executed in this run. It captures
input, output, timing, tokens consumed, and errors. Append-only — re-runs
of the same node create a new row with attempt_number incremented.

Multi-tenant: every row has `tenant_id` and queries MUST scope by it.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import NodeRunStatus, PlaybookRunStatus


class PlaybookRun(Base):
    """One execution of a workflow definition."""

    __tablename__ = "workflow_run"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_definition.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Free-form trigger metadata (e.g. the dossier_id that initiated, the
    # API call payload, schedule info, etc).
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'manual', 'api', 'schedule'
    trigger_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[PlaybookRunStatus] = mapped_column(
        SAEnum(
            PlaybookRunStatus,
            name="workflow_run_status",
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=PlaybookRunStatus.PENDING,
        index=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Accumulated context: { "<node_id>": { "output": {...}, "duration_ms": ... } }
    # Used by the resolver to evaluate `{{node.X.output.field}}` references.
    context_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    initiated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<PlaybookRun id={self.id} status={self.status.value}>"


class PlaybookRunStep(Base):
    """Execution of a single node within a workflow run."""

    __tablename__ = "workflow_node_run"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Node identifier within the graph (e.g. "social_analysis", "bureaus").
    # NOT a foreign key — refers to a node id in the graph JSON.
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[NodeRunStatus] = mapped_column(
        SAEnum(
            NodeRunStatus,
            name="node_run_status",
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=NodeRunStatus.PENDING,
        index=True,
    )

    input_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Cost tracking (when node calls a LLM — specialist agents, document_extractor).
    tokens_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tokens_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    cost_brl: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=6), nullable=False, default=0, server_default="0"
    )

    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    def __repr__(self) -> str:
        return (
            f"<PlaybookRunStep id={self.id} node={self.node_id} "
            f"type={self.node_type} status={self.status.value}>"
        )
