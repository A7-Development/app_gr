"""ResolvedAgent — composto resolvido em runtime (CLAUDE.md §19.12).

Resultado do `AgentRegistry.get()`: combina row do DB (`agent_definition`
+ persona + expertises + prompt) com metadados em codigo (output_schema,
inputs, allowed_tools do CATALOG). E o que `runtime.py` consome.

Diferente de `AgentDefinition` (SQLAlchemy model — row em DB):

    AgentDefinition   = row em `agent_definition` (texto editavel)
    ResolvedAgent     = composto Python pronto pra ser invocado em runtime

Audit:
    `audit_version` retorna string composta que vai em
    `decision_log.rule_or_model_version` — uma chave conta toda a
    historia: agente@versao + persona@versao + expertises@versao +
    prompt@versao.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.agentic.engine.catalog import SpecialistAgentSpec
    from app.agentic.engine.prompts._base import Prompt
    from app.core.enums import Module
    from app.shared.ai.models.agent_expertise import AgentExpertise
    from app.shared.ai.models.agent_persona import AgentPersona


@dataclass(frozen=True, slots=True)
class ResolvedAgent:
    """Composto resolvido — entrega ao runtime."""

    # ─── Identidade ────────────────────────────────────────────────────
    name: str           # canonical: "credito.financial_analyst"
    raw_name: str       # spec.name no CATALOG: "financial_analyst"
    module: Module
    version: int
    tenant_id: UUID | None  # None = global; preenchido = custom de tenant
    definition_id: UUID | None  # None quando veio do fallback CATALOG

    # ─── Texto editavel (DB) ───────────────────────────────────────────
    # persona None quando fallback CATALOG sem entry persona ainda; runtime
    # gera system_text sem bloco <persona>.
    persona: AgentPersona | None
    expertises: tuple[AgentExpertise, ...]
    prompt: Prompt

    # ─── Estrutura tipada (CATALOG, codigo) ───────────────────────────
    spec: SpecialistAgentSpec  # output_schema, inputs, allowed_tools, defaults

    # ─── Modelo resolvido (override chain: DB > agent_config > catalog) ──
    model: str
    fallback_model: str | None
    temperature: float | None
    max_tokens: int | None
    thinking_budget_tokens: int

    # ─── Governance ────────────────────────────────────────────────────
    cross_module: bool
    credit_hint: int | None

    # Override de tools (DB). None = usa `spec.tools` do CATALOG (default
    # curado em codigo); tupla (mesmo vazia) = override explicito da UI.
    # Resolvido pelo runtime em `_build_tools_for_agent`.
    allowed_tools: tuple[str, ...] | None = None

    # Toolsets de MCP concedidos (spec copiloto-mcp §5.1). Cada item:
    # {"mcp_server_name": "bigdatacorp", "tools": [...] | None} — tools None
    # = usa a allowlist do proprio servidor. Tupla vazia = sem MCP.
    mcp_toolsets: tuple[dict, ...] = ()

    @property
    def full_id(self) -> str:
        """Identifier do agente (paralelo a Prompt.full_id)."""
        return f"{self.name}@v{self.version}"

    @property
    def audit_version(self) -> str:
        """Composto para `decision_log.rule_or_model_version`.

        Formato:
            <agent.full_id>+<persona.full_id>+<expertise1.full_id>+...+<prompt.full_id>

        Quando persona/expertises sao vazios (fallback CATALOG sem seed),
        omite o componente correspondente — string fica mais curta mas
        consistentemente legivel.
        """
        parts = [self.full_id]
        if self.persona is not None:
            parts.append(self.persona.full_id)
        for exp in self.expertises:
            parts.append(exp.full_id)
        parts.append(self.prompt.full_id)
        return "+".join(parts)
