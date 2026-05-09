"""AIPrompt: prompts versionados gerenciados em DB.

Substitui o registry em codigo (CLAUDE.md sec 19.4 — atualizado em 2026-04-30).
Cada (name, version) e imutavel apos criado. Editar = criar nova versao.

Workflow:
    1. Maintainer cria prompt 'chat.fidc_geral' v1 via admin UI
    2. ai_prompt_active aponta para v1
    3. Maintainer edita -> sistema cria v2 (v1 fica intacto)
    4. Maintainer ativa v2 -> ai_prompt_active.active_version = 'v2'
    5. Proximas chamadas usam v2; v1 vira historico
    6. Rollback: maintainer ativa v1 de novo (1 click, sem deploy)

Soft-delete:
    `archived_at` marca a versao como nao-utilizavel. Historico preservado;
    nao pode ser ativada. Versao ativa nao pode ser archived (constraint).
"""

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class CacheStrategy(enum.StrEnum):
    """Onde colocar o cache breakpoint Anthropic."""

    NONE = "none"
    AFTER_SYSTEM = "after_system"


class AIPrompt(Base):
    """Uma versao de um prompt template.

    Nome (`name`) agrupa versoes — ex.: 'chat.fidc_geral' tem v1, v2, v3.
    Versao ativa por nome vive em `ai_prompt_active`.
    """

    __tablename__ = "ai_prompt"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_ai_prompt_name_version"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)

    # Conteudo do prompt — editavel via admin UI.
    system_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Template opcional do bloco de contexto que vai como user message ANTES
    # do historico. Aceita interpolacao Python str.format: {page}, {period}, etc.
    user_context_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Resposta canned do assistente que entra como assistant message DEPOIS
    # do user_context, pra "primar" o LLM no tom esperado.
    assistant_prime: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Parametros de chamada.
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    fallback_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperature: Mapped[Decimal] = mapped_column(
        Numeric(precision=3, scale=2), nullable=False, default=Decimal("0.30")
    )
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    cache_strategy: Mapped[CacheStrategy] = mapped_column(
        SAEnum(
            CacheStrategy,
            name="ai_prompt_cache_strategy",
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=CacheStrategy.AFTER_SYSTEM,
    )

    # Descricao humana — explica o que o prompt faz, quando se aplica,
    # decisoes de design. Aparece no admin UI.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Origem editorial.
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
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

    # Soft-delete (LGPD-aware + preserva audit).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def full_id(self) -> str:
        """Identificador usado em audit (`rule_or_model_version`)."""
        return f"{self.name}@{self.version}"

    def __repr__(self) -> str:
        return f"<AIPrompt {self.full_id} model={self.model!r}>"
