"""AIPromptActive: which version of each prompt template is currently active.

The prompt library lives in code (`app/shared/ai/prompts/<category>/<name>_vN.py`).
Multiple versions coexist; this table picks one as active per `name`. Admin UI
toggles the row to roll forward / roll back without redeploying.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AIPromptActive(Base):
    """One row per prompt name; points to the version code path to load.

    Example row:
        name='chat.fidc_carteira', active_version='v2', changed_by=<uuid>
    """

    __tablename__ = "ai_prompt_active"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    active_version: Mapped[str] = mapped_column(String(32), nullable=False)

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    changed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<AIPromptActive name={self.name!r} version={self.active_version!r}>"
