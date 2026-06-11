"""Manage prompts (DB-backed) — system maintainer only.

Endpoints:
    GET    /api/v1/admin/ai/prompts             — lista todas as versoes (todas as
                                                   familias `name`).
    GET    /api/v1/admin/ai/prompts/{id}        — detalhe de uma versao (texto
                                                   completo do prompt).
    POST   /api/v1/admin/ai/prompts             — cria nova familia (vira v1).
    PUT    /api/v1/admin/ai/prompts/{id}        — cria nova VERSAO copiando
                                                   `id` + aplicando patches.
    PUT    /api/v1/admin/ai/prompts/{name}/active — ativa uma versao especifica.
    POST   /api/v1/admin/ai/prompts/{id}/preview — render com contexto fake
                                                   (sem chamar LLM).
    POST   /api/v1/admin/ai/prompts/{id}/archive — soft-delete (nao pode ser ativada).

Versoes sao IMUTAVEIS apos criadas. "Editar" sempre cria uma nova versao;
historico e preservado para auditoria + rollback de 1 click.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.engine.prompts import repository
from app.agentic.engine.prompts._base import Prompt as PromptDTO
from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.models.prompt import AIPrompt, CacheStrategy
from app.shared.ai.models.prompt_active import AIPromptActive
from app.shared.ai.schemas import (
    PromptActivate,
    PromptCreate,
    PromptDetail,
    PromptPreviewRequest,
    PromptPreviewResponse,
    PromptUpdate,
    PromptVersionInfo,
)

router = APIRouter(prefix="/ai/prompts", tags=["admin:ai-prompts"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


# ─── Helpers ──────────────────────────────────────────────────────────────


def _to_version_info(row: AIPrompt, active_map: dict[str, str]) -> PromptVersionInfo:
    return PromptVersionInfo(
        id=row.id,
        name=row.name,
        version=row.version,
        is_active=active_map.get(row.name) == row.version,
        model=row.model,
        fallback_model=row.fallback_model,
        temperature=float(row.temperature),
        max_tokens=row.max_tokens,
        description=row.description,
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


def _to_detail(row: AIPrompt, active_map: dict[str, str]) -> PromptDetail:
    cache = row.cache_strategy.value if hasattr(row.cache_strategy, "value") else str(row.cache_strategy)
    return PromptDetail(
        id=row.id,
        name=row.name,
        version=row.version,
        is_active=active_map.get(row.name) == row.version,
        system_text=row.system_text,
        user_context_template=row.user_context_template,
        assistant_prime=row.assistant_prime,
        model=row.model,
        fallback_model=row.fallback_model,
        temperature=float(row.temperature),
        max_tokens=row.max_tokens,
        cache_strategy=cache.lower(),
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
    )


async def _load_active_map(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(select(AIPromptActive))).scalars().all()
    return {r.name: r.active_version for r in rows}


async def _get_or_404(db: AsyncSession, prompt_id: UUID) -> AIPrompt:
    row = await db.get(AIPrompt, prompt_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt nao encontrado."
        )
    return row


# ─── Endpoints ────────────────────────────────────────────────────────────


@router.get("", response_model=list[PromptVersionInfo], dependencies=_GUARD)
async def list_prompts(
    db: Annotated[AsyncSession, Depends(get_db)],
    include_archived: bool = False,
) -> list[PromptVersionInfo]:
    """List all prompts and versions, marking the active one per name."""
    stmt = select(AIPrompt).order_by(AIPrompt.name.asc(), AIPrompt.created_at.desc())
    if not include_archived:
        stmt = stmt.where(AIPrompt.archived_at.is_(None))
    rows = (await db.execute(stmt)).scalars().all()
    active_map = await _load_active_map(db)
    return [_to_version_info(r, active_map) for r in rows]


@router.get("/{prompt_id}", response_model=PromptDetail, dependencies=_GUARD)
async def get_prompt(
    prompt_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptDetail:
    """Get full detail of one prompt version (text included)."""
    row = await _get_or_404(db, prompt_id)
    active_map = await _load_active_map(db)
    return _to_detail(row, active_map)


@router.post(
    "",
    response_model=PromptDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=_GUARD,
)
async def create_prompt(
    payload: PromptCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptDetail:
    """Create a new prompt family (becomes v1).

    Fails with 409 if `name` already exists — use PUT /{id} to add a version.
    """
    existing = (
        await db.execute(select(AIPrompt).where(AIPrompt.name == payload.name).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Prompt '{payload.name}' ja existe — use PUT para criar nova versao.",
        )

    row = AIPrompt(
        name=payload.name,
        version="v1",
        system_text=payload.system_text,
        user_context_template=payload.user_context_template,
        assistant_prime=payload.assistant_prime,
        model=payload.model,
        fallback_model=payload.fallback_model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        cache_strategy=CacheStrategy(payload.cache_strategy),
        description=payload.description,
        created_by=principal.user_id,
    )
    db.add(row)

    # Marca v1 como ativa automaticamente.
    await db.execute(
        pg_insert(AIPromptActive)
        .values(
            name=payload.name, active_version="v1", changed_by=principal.user_id
        )
        .on_conflict_do_update(
            index_elements=["name"],
            set_={"active_version": "v1", "changed_by": principal.user_id},
        )
    )
    await db.commit()
    await db.refresh(row)
    active_map = await _load_active_map(db)
    return _to_detail(row, active_map)


@router.put("/{prompt_id}", response_model=PromptDetail, dependencies=_GUARD)
async def update_prompt(
    prompt_id: UUID,
    payload: PromptUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptDetail:
    """Create new version copying `prompt_id` + applying patches.

    Versao base e imutavel — esta operacao SEMPRE cria uma nova linha
    `v(N+1)`. A nova versao NAO e ativada automaticamente; chame
    PUT /{name}/active para promover.
    """
    base = await _get_or_404(db, prompt_id)

    # Calcula proxima versao olhando todas as linhas do mesmo nome.
    existing = await repository.list_versions(db, name=base.name)
    next_version = repository.next_version_for(existing)

    new_row = AIPrompt(
        name=base.name,
        version=next_version,
        system_text=payload.system_text if payload.system_text is not None else base.system_text,
        user_context_template=(
            payload.user_context_template
            if payload.user_context_template is not None
            else base.user_context_template
        ),
        assistant_prime=(
            payload.assistant_prime
            if payload.assistant_prime is not None
            else base.assistant_prime
        ),
        model=payload.model if payload.model is not None else base.model,
        fallback_model=(
            payload.fallback_model
            if payload.fallback_model is not None
            else base.fallback_model
        ),
        temperature=(
            payload.temperature if payload.temperature is not None else base.temperature
        ),
        max_tokens=(
            payload.max_tokens if payload.max_tokens is not None else base.max_tokens
        ),
        cache_strategy=(
            CacheStrategy(payload.cache_strategy)
            if payload.cache_strategy is not None
            else base.cache_strategy
        ),
        description=(
            payload.description if payload.description is not None else base.description
        ),
        created_by=principal.user_id,
    )
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)
    active_map = await _load_active_map(db)
    return _to_detail(new_row, active_map)


@router.put(
    "/{name}/active", response_model=PromptVersionInfo, dependencies=_GUARD
)
async def activate_version(
    name: str,
    payload: PromptActivate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptVersionInfo:
    """Promote a specific version to active for `name`."""
    target = await _get_or_404(db, payload.version_id)
    if target.name != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"version_id pertence a '{target.name}', nao a '{name}'.",
        )
    if target.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Versao arquivada nao pode ser ativada — desarquive primeiro.",
        )

    await db.execute(
        pg_insert(AIPromptActive)
        .values(
            name=name,
            active_version=target.version,
            changed_by=principal.user_id,
        )
        .on_conflict_do_update(
            index_elements=["name"],
            set_={
                "active_version": target.version,
                "changed_by": principal.user_id,
            },
        )
    )
    await db.commit()
    active_map = await _load_active_map(db)
    return _to_version_info(target, active_map)


@router.post(
    "/{prompt_id}/archive",
    response_model=PromptDetail,
    dependencies=_GUARD,
)
async def archive_version(
    prompt_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptDetail:
    """Soft-delete uma versao. Nao pode arquivar a versao ativa."""
    row = await _get_or_404(db, prompt_id)
    active_version = await repository.get_active_version(db, name=row.name)
    if active_version == row.version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Nao e possivel arquivar a versao ativa de '{row.name}'. "
                "Ative outra versao primeiro."
            ),
        )

    from datetime import UTC, datetime

    row.archived_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    active_map = await _load_active_map(db)
    return _to_detail(row, active_map)


@router.post(
    "/{prompt_id}/preview",
    response_model=PromptPreviewResponse,
    dependencies=_GUARD,
)
async def preview_prompt(
    prompt_id: UUID,
    payload: PromptPreviewRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptPreviewResponse:
    """Renderiza o prompt com contexto fake — sem chamar o LLM.

    Util pra inspecionar exatamente o que vai virar payload do adapter.
    """
    row = await _get_or_404(db, prompt_id)
    prompt: PromptDTO = repository._row_to_prompt(row)
    try:
        msgs = prompt.render(payload.context)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    return PromptPreviewResponse(
        name=prompt.name,
        version=prompt.version,
        model=prompt.model_default,
        temperature=prompt.temperature,
        max_tokens=prompt.max_tokens,
        messages=[m.model_dump() for m in msgs],
    )
