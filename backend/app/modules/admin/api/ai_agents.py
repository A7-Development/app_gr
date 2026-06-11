"""Admin API: per-agent model override (system maintainer only).

Endpoints (CLAUDE.md §19 — capability transversal de IA):
    GET  /api/v1/admin/ai/agents          → list catalog + DB overrides
    PUT  /api/v1/admin/ai/agents/{name}   → upsert override row
    GET  /api/v1/admin/ai/agents/models   → curated dropdown of models

Etapa 1: provider fixo em Anthropic. A escolha aqui muda apenas o `model`
e o `fallback_model` que o runtime do Specialist Agent vai usar
(`app.agentic.engine.runtime._invoke_with_validation`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.engine.catalog import CATALOG
from app.agentic.engine.model_resolver import (
    AVAILABLE_MODELS,
    is_supported_model,
    list_agents_with_defaults,
)
from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.models.agent_config import AgentConfig
from app.shared.ai.schemas import (
    AgentConfigRead,
    AgentConfigUpdate,
    AgentModelOption,
)

router = APIRouter(prefix="/ai/agents", tags=["admin:ai-agents"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


@router.get("/models", response_model=list[AgentModelOption], dependencies=_GUARD)
async def list_available_models() -> list[AgentModelOption]:
    """Lista curada de modelos Anthropic oferecidos no dropdown."""
    return [
        AgentModelOption(
            id=m.id, label=m.label, tier=m.tier, description=m.description
        )
        for m in AVAILABLE_MODELS
    ]


@router.get("", response_model=list[AgentConfigRead], dependencies=_GUARD)
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AgentConfigRead]:
    """Lista agentes do CATALOG juntando override em `agent_config` (se houver)."""
    overrides_by_name = {
        row.agent_name: row
        for row in (await db.execute(_select_all_overrides())).scalars().all()
    }

    out: list[AgentConfigRead] = []
    for spec_dict in list_agents_with_defaults():
        name = spec_dict["agent_name"]
        row = overrides_by_name.get(name)
        if row is not None:
            out.append(
                AgentConfigRead(
                    agent_name=name,
                    description=spec_dict["description"],
                    prompt_name=spec_dict["prompt_name"],
                    multimodal=spec_dict["multimodal"],
                    section_id=spec_dict["section_id"],
                    default_model=spec_dict["default_model"],
                    default_fallback_model=spec_dict["default_fallback_model"],
                    model=row.model,
                    fallback_model=row.fallback_model,
                    source="db_override",
                    updated_at=row.updated_at,
                    updated_by_user_id=row.updated_by_user_id,
                )
            )
        else:
            out.append(
                AgentConfigRead(
                    agent_name=name,
                    description=spec_dict["description"],
                    prompt_name=spec_dict["prompt_name"],
                    multimodal=spec_dict["multimodal"],
                    section_id=spec_dict["section_id"],
                    default_model=spec_dict["default_model"],
                    default_fallback_model=spec_dict["default_fallback_model"],
                    model=spec_dict["default_model"],
                    fallback_model=spec_dict["default_fallback_model"],
                    source="catalog_default",
                    updated_at=None,
                    updated_by_user_id=None,
                )
            )
    return out


@router.put(
    "/{agent_name}",
    response_model=AgentConfigRead,
    dependencies=_GUARD,
)
async def update_agent(
    agent_name: str,
    payload: AgentConfigUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentConfigRead:
    """Upsert do override de modelo para um agente do CATALOG."""
    spec = CATALOG.get(agent_name)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Agente '{agent_name}' nao registrado. "
                f"Disponiveis: {sorted(CATALOG.keys())}."
            ),
        )

    if not is_supported_model(payload.model):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Modelo '{payload.model}' nao esta na lista permitida. "
                "Veja GET /api/v1/admin/ai/agents/models."
            ),
        )
    if payload.fallback_model is not None and not is_supported_model(
        payload.fallback_model
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Fallback '{payload.fallback_model}' nao esta na lista permitida."
            ),
        )

    row = await db.get(AgentConfig, agent_name)
    if row is None:
        row = AgentConfig(
            agent_name=agent_name,
            model=payload.model,
            fallback_model=payload.fallback_model,
            updated_at=datetime.now(UTC),
            updated_by_user_id=principal.user_id,
        )
        db.add(row)
    else:
        row.model = payload.model
        row.fallback_model = payload.fallback_model
        row.updated_at = datetime.now(UTC)
        row.updated_by_user_id = principal.user_id

    await db.commit()
    await db.refresh(row)

    return AgentConfigRead(
        agent_name=spec.name,
        description=spec.description,
        prompt_name=spec.prompt_name,
        multimodal=spec.multimodal,
        section_id=spec.section_id,
        default_model=spec.preferred_model,
        default_fallback_model=spec.fallback_model,
        model=row.model,
        fallback_model=row.fallback_model,
        source="db_override",
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
    )


def _select_all_overrides():
    """Late import wrapper for SELECT — keeps module-level imports tidy."""
    from sqlalchemy import select

    return select(AgentConfig)
