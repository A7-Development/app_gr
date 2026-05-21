"""AgentRegistry — resolve ResolvedAgent (DB-first, CATALOG fallback).

Pipeline:
    1. Lookup `agent_definition_active` for (tenant_id, name). Tenant
       especifico ganha de global (tenant_id IS NULL).
    2. Carrega `agent_definition` apontada pelo active pointer.
    3. JOIN `agent_persona` + `agent_persona_active` (versao ativa).
    4. JOIN `agent_expertise` (em ANY(expertise_ids)) preservando ordem.
    5. Resolve `ai_prompt` via repository (versao ativa).
    6. Lookup CATALOG (codigo) por raw_name pra pegar estrutura tipada
       (output_schema, inputs, allowed_tools, thinking_budget).
    7. Resolve modelo via chain: agent_definition.model > agent_config >
       spec.preferred_model.
    8. Retorna ResolvedAgent.

Fallback CATALOG:
    Quando NAO ha row em `agent_definition_active` (dev sem migration
    aplicada, testes, agente em codigo que ainda nao foi seedado), o
    registry monta ResolvedAgent diretamente do CATALOG + prompt resolvido,
    com `persona=None`, `expertises=()`, `definition_id=None`. Garante
    backward compat — nada quebra.

Convencao de nome (CLAUDE.md §19.0):
    Aceita simple name ("financial_analyst") ou canonical name
    ("credito.financial_analyst"). Simple = prefixo derivado do
    `scope.module`; canonical = usado direto.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from app.agentic._scope import ScopedContext
from app.agentic.agents._base import ResolvedAgent
from app.agentic.engine.catalog import CATALOG
from app.agentic.engine.model_resolver import resolve_models_for_agent
from app.agentic.engine.prompts import repository as prompt_repo
from app.shared.ai.models.agent_definition import (
    AgentDefinition,
    AgentDefinitionActive,
)
from app.shared.ai.models.agent_expertise import (
    AgentExpertise,
    AgentExpertiseActive,
)
from app.shared.ai.models.agent_persona import (
    AgentPersona,
    AgentPersonaActive,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AgentNotFoundError(LookupError):
    """Agente nao encontrado em DB nem em CATALOG."""


class AgentRegistry:
    """Singleton-style namespace; metodos sao staticmethod por design."""

    @staticmethod
    async def get(
        db: AsyncSession,
        *,
        name: str,
        scope: ScopedContext,
    ) -> ResolvedAgent:
        """Resolve ResolvedAgent pra `name` no scope dado.

        Args:
            db: AsyncSession SQLAlchemy.
            name: simple name (`"financial_analyst"`) ou canonical
                (`"credito.financial_analyst"`). Simple e prefixado com
                `scope.module.value`; canonical e usado direto.
            scope: ScopedContext do invocador (define tenant_id + module).

        Returns:
            ResolvedAgent pronto pra runtime.

        Raises:
            AgentNotFoundError: agente nao existe em DB nem em CATALOG.
        """
        canonical_name, raw_name = _normalize_names(name, scope)

        # ── 1. agent_definition_active (tenant especifico > global) ────
        stmt = (
            select(AgentDefinitionActive)
            .where(AgentDefinitionActive.name == canonical_name)
            .where(
                or_(
                    AgentDefinitionActive.tenant_id == scope.tenant_id,
                    AgentDefinitionActive.tenant_id.is_(None),
                )
            )
            .order_by(AgentDefinitionActive.tenant_id.nulls_last())
            .limit(1)
        )
        active = (await db.execute(stmt)).scalar_one_or_none()

        if active is None:
            # Fallback CATALOG — agente ainda nao seedado em DB.
            logger.debug(
                "Agent '%s' not in agent_definition_active; falling back to CATALOG",
                canonical_name,
            )
            return await _resolve_from_catalog(
                db=db, raw_name=raw_name, canonical_name=canonical_name, scope=scope
            )

        # ── 2. agent_definition (row do agente versionado) ─────────────
        definition = await db.get(AgentDefinition, active.definition_id)
        if definition is None:
            raise AgentNotFoundError(
                f"agent_definition_active aponta para id={active.definition_id} "
                f"mas a row nao existe em agent_definition. DB inconsistente."
            )

        # ── 3. persona (active version) ────────────────────────────────
        persona: AgentPersona | None = None
        if definition.persona_id is not None:
            persona_stmt = (
                select(AgentPersona)
                .join(
                    AgentPersonaActive,
                    AgentPersonaActive.persona_id == AgentPersona.id,
                )
                .where(AgentPersona.id == definition.persona_id)
            )
            persona = (await db.execute(persona_stmt)).scalar_one_or_none()
            # Se persona_id existe mas active nao aponta pra essa versao,
            # cai em None. Aceitavel — sera tratado como "sem persona"
            # pelo composer. UI futura sempre deveria garantir consistencia.

        # ── 4. expertises (active versions, preservando ordem) ──────────
        expertises: tuple[AgentExpertise, ...] = ()
        if definition.expertise_ids:
            exp_stmt = (
                select(AgentExpertise)
                .join(
                    AgentExpertiseActive,
                    AgentExpertiseActive.expertise_id == AgentExpertise.id,
                )
                .where(AgentExpertise.id.in_(definition.expertise_ids))
            )
            rows = (await db.execute(exp_stmt)).scalars().all()
            by_id = {r.id: r for r in rows}
            # Preserva ordem do array `expertise_ids` (defensivo:
            # ids que nao tem active pointer sao omitidos).
            expertises = tuple(
                by_id[eid] for eid in definition.expertise_ids if eid in by_id
            )

        # ── 5. prompt (via repository) ──────────────────────────────────
        prompt = await prompt_repo.resolve(db, name=definition.prompt_name)

        # ── 6. CATALOG metadata (estrutura tipada) ──────────────────────
        spec = CATALOG.get(raw_name)
        if spec is None:
            raise AgentNotFoundError(
                f"DB tem agent_definition '{canonical_name}' mas CATALOG nao tem "
                f"entry '{raw_name}'. Adicione ao CATALOG ou ajuste o seed."
            )

        # ── 7. Modelo: chain override ──────────────────────────────────
        resolved_models = await resolve_models_for_agent(db, spec)
        model = definition.model or resolved_models.model
        fallback_model = (
            definition.fallback_model
            if definition.fallback_model is not None
            else resolved_models.fallback_model
        )

        # ── 8. ResolvedAgent ──────────────────────────────────────────
        return ResolvedAgent(
            name=canonical_name,
            raw_name=raw_name,
            module=scope.module,
            version=definition.version,
            tenant_id=definition.tenant_id,
            definition_id=definition.id,
            persona=persona,
            expertises=expertises,
            prompt=prompt,
            spec=spec,
            model=model,
            fallback_model=fallback_model,
            temperature=(
                float(definition.temperature)
                if definition.temperature is not None
                else None
            ),
            max_tokens=definition.max_tokens,
            thinking_budget_tokens=spec.thinking_budget_tokens,
            cross_module=definition.cross_module,
            credit_hint=definition.credit_hint,
        )


# ─── Helpers ─────────────────────────────────────────────────────────────


def _normalize_names(name: str, scope: ScopedContext) -> tuple[str, str]:
    """Retorna (canonical_name, raw_name).

    Aceita ambas as formas:
    - simple: "financial_analyst" -> canonical "credito.financial_analyst"
    - canonical: "credito.financial_analyst" -> usado direto

    raw_name e o lookup key no CATALOG (sem prefixo de modulo).
    """
    if "." in name:
        canonical = name
        raw = name.split(".", 1)[1]
    else:
        canonical = f"{scope.module.value}.{name}"
        raw = name
    return canonical, raw


async def _resolve_from_catalog(
    *,
    db: AsyncSession,
    raw_name: str,
    canonical_name: str,
    scope: ScopedContext,
) -> ResolvedAgent:
    """Fallback: monta ResolvedAgent direto do CATALOG sem persona/expertise.

    Usado quando agent_definition_active nao tem entry pra esse name —
    dev sem migration aplicada, testes, agente novo em codigo ainda nao
    seedado em DB. Garante backward compat — runtime nao quebra.
    """
    spec = CATALOG.get(raw_name)
    if spec is None:
        raise AgentNotFoundError(
            f"Agente '{canonical_name}' (raw='{raw_name}') nao existe em DB "
            f"(agent_definition_active) nem em CATALOG (codigo)."
        )

    prompt = await prompt_repo.resolve(db, name=spec.prompt_name)
    resolved_models = await resolve_models_for_agent(db, spec)

    return ResolvedAgent(
        name=canonical_name,
        raw_name=raw_name,
        module=scope.module,
        version=1,  # CATALOG nao versiona, assume v1
        tenant_id=None,
        definition_id=None,  # marca explicito que veio do fallback
        persona=None,
        expertises=(),
        prompt=prompt,
        spec=spec,
        model=resolved_models.model,
        fallback_model=resolved_models.fallback_model,
        temperature=None,
        max_tokens=None,
        thinking_budget_tokens=spec.thinking_budget_tokens,
        cross_module=False,
        credit_hint=None,
    )
