"""AgentDefinition — catalogo central de agentes (CLAUDE.md §19.12).

Cada agente Strata e composto de:
    persona + expertises + prompt_task + tools (allowed) + modelo + memoria

Persona/expertises/prompt vivem em DB versionados (rollback 1-click);
tools sao registradas via @register_tool no codigo (referenciadas por
nome em `allowed_tools_pattern`); output_schema (Pydantic class) fica em
codigo (nao da pra editar em DB).

`tenant_id NULL` = agente global (curado pela Strata). `tenant_id NOT
NULL` = custom de tenant (futuro F5, marketplace). Hoje no MVP so
globais — coluna existe pra reservar a forma.

Layout fisico em `app/agentic/agents/catalog/<modulo>_<agente>.py`
(stub-only no F2.b.1; F2.b.2 cria o AgentRegistry que le do DB e
combina com o stub).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AgentDefinition(Base):
    """Definicao versionada de agente.

    `name` segue convencao `<modulo>.<agente>` (ex.: `credito.analista_dossie`,
    `controladoria.variacao_cota`). `module` e tag (nao pasta) — determina
    scope default de tools/workflows + RBAC + billing + metricas.

    `expertise_ids` e array de UUIDs (sem FK constraint — Postgres ARRAY
    nao trigga FK; validacao na camada de aplicacao). Order-preserving:
    expertises sao concatenadas ao system prompt na ordem do array.

    `prompt_name` referencia `ai_prompt.name` (sem FK fisica porque
    `ai_prompt` e por `(name, version)` e o active pointer vive em
    `ai_prompt_active`).
    """

    __tablename__ = "agent_definition"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", "version",
            name="uq_agent_definition_tenant_name_version",
        ),
        # Index pra lookup por (tenant_id, name) — joga com active pointer.
        Index("ix_agent_definition_tenant_name", "tenant_id", "name"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # NULL = agente global da Strata; preenchido = custom de tenant (futuro).
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    module: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    persona_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_persona.id"), nullable=True
    )
    expertise_ids: Mapped[list[UUID] | None] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=True
    )
    prompt_name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Subset de tools que o agente pode chamar, por nome (ou wildcard de
    # modulo, ex.: "controladoria.*"). Resolvido em runtime via
    # `ToolRegistry.get_available(scope, allowed=...)`. Semantica do valor:
    #   NULL  -> usa o default do CATALOG (`SpecialistAgentSpec.tools`) —
    #            preserva o comportamento dos agentes curados em codigo.
    #   []    -> agente SEM tools (conversacional puro / explicito).
    #   [...] -> override explicito (editavel pela UI, sem deploy).
    # Sem FK (lista de strings); validacao na camada de aplicacao + registry.
    allowed_tools: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )

    # Overrides opcionais — quando None, runtime usa o default do
    # SpecialistAgentSpec (catalog) ou do prompt template.
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # cross_module=True libera invocacao por agente de outro modulo.
    # Default false: F2.b enforced isolation; futuras delegacoes
    # cross-modulo precisam justificativa + auditoria.
    cross_module: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credit_hint: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        scope = f"tenant={self.tenant_id}" if self.tenant_id else "global"
        return f"<AgentDefinition {self.name}@v{self.version} module={self.module} {scope}>"

    @property
    def full_id(self) -> str:
        return f"{self.name}@v{self.version}"


class AgentDefinitionActive(Base):
    """Aponta para a versao ativa de cada `(tenant_id, name)`.

    Globais tem `tenant_id IS NULL`. Custom de tenant tem
    `tenant_id NOT NULL`. PK composta cobre os dois casos.
    """

    __tablename__ = "agent_definition_active"
    __table_args__ = (
        # Active pointer e por (tenant_id, name) — uma versao ativa
        # por agente em cada escopo.
        UniqueConstraint(
            "tenant_id", "name",
            name="uq_agent_definition_active_tenant_name",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_definition.id"),
        nullable=False,
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    activated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        scope = f"tenant={self.tenant_id}" if self.tenant_id else "global"
        return f"<AgentDefinitionActive {scope} {self.name} -> {self.definition_id}>"
