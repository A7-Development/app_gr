"""AgentConfig: model override per specialist agent.

Each row maps `agent_name` (key in `app.shared.agents.catalog.CATALOG`) to
the Anthropic model picked by the system maintainer. Lets the maintainer
swap an agent's model without touching code (etapa 1 — provider locked to
Anthropic).

When the runtime finds no row for an agent, it falls back to the
`preferred_model` / `fallback_model` defined in the catalog (the code
default). Backward-compat: agents with no DB config keep running.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AgentConfig(Base):
    """Per-agent model override.

    `agent_name` is PK and references a key in `CATALOG`. No physical FK
    because CATALOG lives in code (Pydantic schemas + tools); validation
    happens at the API layer before the PUT lands here.
    """

    __tablename__ = "agent_config"

    agent_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    fallback_model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<AgentConfig {self.agent_name} model={self.model!r}>"
