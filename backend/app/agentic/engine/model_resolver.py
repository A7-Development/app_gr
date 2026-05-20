"""Resolve qual modelo usar para um Specialist Agent.

Em runtime, o agente le o override definido em `agent_config` (editavel via
`/admin/ia/agents`). Se nao houver linha, cai no `preferred_model` /
`fallback_model` definidos no CATALOG (default em codigo).

Tambem expoe `AVAILABLE_MODELS`: lista curada de modelos Anthropic
oferecidos no dropdown do admin. Editar aqui = editar a lista exposta na
UI. Provider fica fixo em Anthropic na etapa 1.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.engine.catalog import CATALOG, SpecialistAgentSpec
from app.shared.ai.models.agent_config import AgentConfig


@dataclass(frozen=True, slots=True)
class ModelOption:
    """Uma entrada no dropdown de modelos Anthropic."""

    id: str           # API model id (ex.: "claude-opus-4-7")
    label: str        # Human label (ex.: "Opus 4.7")
    tier: str         # "opus" | "sonnet" | "haiku" — informativo para UI
    description: str  # 1-line about capability/cost tradeoff


# Lista curada — provider fixo em Anthropic na etapa 1. Para adicionar OpenAI
# (etapa 2), trocar para uma estrutura com provider e fazer o resolver
# devolver tambem o provider. A ordem aqui e a ordem do dropdown.
AVAILABLE_MODELS: tuple[ModelOption, ...] = (
    ModelOption(
        id="claude-opus-4-7",
        label="Opus 4.7",
        tier="opus",
        description="Mais capaz da familia Claude 4. Melhor para analises densas e raciocinio longo.",
    ),
    ModelOption(
        id="claude-opus-4-6",
        label="Opus 4.6",
        tier="opus",
        description="Geracao anterior do Opus. Equilibrio capacidade/custo similar ao 4.7.",
    ),
    ModelOption(
        id="claude-opus-4-5",
        label="Opus 4.5",
        tier="opus",
        description="Default historico do CATALOG. Mantido para retrocompatibilidade.",
    ),
    ModelOption(
        id="claude-sonnet-4-6",
        label="Sonnet 4.6",
        tier="sonnet",
        description="Balanceado: ~3x mais barato que Opus, qualidade prox. para tarefas estruturadas.",
    ),
    ModelOption(
        id="claude-sonnet-4-5",
        label="Sonnet 4.5",
        tier="sonnet",
        description="Sonnet anterior. Bom fallback de Opus para reduzir custo em retry.",
    ),
    ModelOption(
        id="claude-haiku-4-5-20251001",
        label="Haiku 4.5",
        tier="haiku",
        description="Rapido e barato. Ideal para extracoes simples (ex.: pleito_extractor).",
    ),
)

_AVAILABLE_IDS = frozenset(m.id for m in AVAILABLE_MODELS)


def is_supported_model(model_id: str) -> bool:
    """True se `model_id` esta na lista curada do dropdown."""
    return model_id in _AVAILABLE_IDS


@dataclass(frozen=True, slots=True)
class ResolvedModels:
    """Modelos efetivos para uma execucao de agente."""

    model: str
    fallback_model: str | None
    source: str  # "db_override" | "catalog_default"


async def resolve_models_for_agent(
    db: AsyncSession,
    spec: SpecialistAgentSpec,
) -> ResolvedModels:
    """Devolve o modelo+fallback efetivos para `spec`.

    Prefere a linha em `agent_config`; caso contrario, retorna os defaults
    de codigo (`spec.preferred_model`, `spec.fallback_model`).
    """
    row = await db.get(AgentConfig, spec.name)
    if row is not None:
        return ResolvedModels(
            model=row.model,
            fallback_model=row.fallback_model,
            source="db_override",
        )
    return ResolvedModels(
        model=spec.preferred_model,
        fallback_model=spec.fallback_model,
        source="catalog_default",
    )


def list_agents_with_defaults() -> list[dict]:
    """Snapshot do CATALOG para o endpoint admin de listagem.

    Cada entrada inclui o default de codigo (para a UI mostrar "padrao do
    sistema") sem precisar inspecionar Python em runtime do frontend.
    """
    return [
        {
            "agent_name": spec.name,
            "description": spec.description,
            "prompt_name": spec.prompt_name,
            "default_model": spec.preferred_model,
            "default_fallback_model": spec.fallback_model,
            "multimodal": spec.multimodal,
            "section_id": spec.section_id,
        }
        for spec in CATALOG.values()
    ]
