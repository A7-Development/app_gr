"""Manage agent personas (DB-backed) — system maintainer only.

Endpoints:
    GET    /api/v1/admin/ia/personas             lista todas as versoes
    GET    /api/v1/admin/ia/personas/{id}        detalhe de uma versao
    POST   /api/v1/admin/ia/personas             cria nova familia (vira v1, ativa)
    PUT    /api/v1/admin/ia/personas/{id}        cria nova versao copiando + patches
    PUT    /api/v1/admin/ia/personas/{name}/active  promove versao
    POST   /api/v1/admin/ia/personas/{id}/archive   soft-delete (nao pode ativar)

Versoes sao IMUTAVEIS apos criadas. "Editar" sempre cria uma nova versao;
historico e preservado para auditoria + rollback de 1 click. Espelha o
pattern de `ai_prompts.py` (CLAUDE.md §19.4).

Auditoria: alteracoes futuras devem gravar em `decision_log`
(`decision_type=CONFIGURATION_CHANGE`). Hoje (F2.c.1) so logamos via
`changed_by` na proxima fase — manter MVP enxuto.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.models.agent_definition import AgentDefinition
from app.shared.ai.models.agent_persona import AgentPersona, AgentPersonaActive
from app.shared.ai.schemas.persona import (
    PersonaActivate,
    PersonaCreate,
    PersonaDetail,
    PersonaUpdate,
    PersonaVersionInfo,
)

router = APIRouter(prefix="/ia/personas", tags=["admin:ia-personas"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


# ─── Helpers ──────────────────────────────────────────────────────────────


async def _load_active_map(db: AsyncSession) -> dict[str, UUID]:
    """Retorna {persona_name: active_persona_id}."""
    rows = (await db.execute(select(AgentPersonaActive))).scalars().all()
    return {r.name: r.persona_id for r in rows}


async def _load_usage_map(db: AsyncSession) -> dict[UUID, int]:
    """Retorna {persona_id: count} — quantos agent_definition usam cada persona.

    Conta por persona_id (UUID exato — versao especifica). Nao agrupa
    por nome pra que o curador veja "usado em N agentes que ainda
    apontam pra ESTA versao" — util pra impacto de promover nova versao.
    """
    stmt = (
        select(AgentDefinition.persona_id, func.count(AgentDefinition.id))
        .where(AgentDefinition.persona_id.isnot(None))
        .where(AgentDefinition.archived_at.is_(None))
        .group_by(AgentDefinition.persona_id)
    )
    return {row[0]: row[1] for row in (await db.execute(stmt)).all()}


def _to_version_info(
    row: AgentPersona,
    active_map: dict[str, UUID],
    usage_map: dict[UUID, int],
) -> PersonaVersionInfo:
    return PersonaVersionInfo(
        id=row.id,
        name=row.name,
        version=row.version,
        display_name=row.display_name,
        is_active=active_map.get(row.name) == row.id,
        expertise_domains=row.expertise_domains,
        description=row.description,
        usage_count=usage_map.get(row.id, 0),
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


def _to_detail(
    row: AgentPersona,
    active_map: dict[str, UUID],
    usage_map: dict[UUID, int],
) -> PersonaDetail:
    return PersonaDetail(
        id=row.id,
        name=row.name,
        version=row.version,
        display_name=row.display_name,
        role_block=row.role_block,
        description=row.description,
        expertise_domains=row.expertise_domains,
        is_active=active_map.get(row.name) == row.id,
        usage_count=usage_map.get(row.id, 0),
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


async def _get_or_404(db: AsyncSession, persona_id: UUID) -> AgentPersona:
    row = await db.get(AgentPersona, persona_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Persona nao encontrada."
        )
    return row


async def _next_version_for(db: AsyncSession, name: str) -> int:
    """Maior version+1 entre as rows com `name` (incluindo arquivadas)."""
    stmt = select(func.max(AgentPersona.version)).where(AgentPersona.name == name)
    current = (await db.execute(stmt)).scalar()
    return (current or 0) + 1


# ─── Endpoints ────────────────────────────────────────────────────────────


@router.get("", response_model=list[PersonaVersionInfo], dependencies=_GUARD)
async def list_personas(
    db: Annotated[AsyncSession, Depends(get_db)],
    include_archived: bool = False,
) -> list[PersonaVersionInfo]:
    """List all personas + versions, marking the active one per name."""
    stmt = select(AgentPersona).order_by(
        AgentPersona.name.asc(), AgentPersona.version.desc()
    )
    if not include_archived:
        stmt = stmt.where(AgentPersona.archived_at.is_(None))
    rows = (await db.execute(stmt)).scalars().all()
    active_map = await _load_active_map(db)
    usage_map = await _load_usage_map(db)
    return [_to_version_info(r, active_map, usage_map) for r in rows]


@router.get("/{persona_id}", response_model=PersonaDetail, dependencies=_GUARD)
async def get_persona(
    persona_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PersonaDetail:
    """Full detail of one persona version (markdown text included)."""
    row = await _get_or_404(db, persona_id)
    active_map = await _load_active_map(db)
    usage_map = await _load_usage_map(db)
    return _to_detail(row, active_map, usage_map)


@router.post(
    "",
    response_model=PersonaDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=_GUARD,
)
async def create_persona(
    payload: PersonaCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PersonaDetail:
    """Cria nova familia de persona (vira v1). Falha 409 se `name` existe."""
    existing = (
        await db.execute(
            select(AgentPersona).where(AgentPersona.name == payload.name).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Persona '{payload.name}' ja existe — use PUT para criar nova versao."
            ),
        )

    row = AgentPersona(
        name=payload.name,
        version=1,
        display_name=payload.display_name,
        role_block=payload.role_block,
        description=payload.description,
        expertise_domains=payload.expertise_domains,
        created_by_user_id=principal.user_id,
    )
    db.add(row)
    await db.flush()  # atribui row.id antes do insert do active pointer

    # Marca v1 como ativa.
    await db.execute(
        pg_insert(AgentPersonaActive)
        .values(
            name=payload.name,
            persona_id=row.id,
            activated_by_user_id=principal.user_id,
        )
        .on_conflict_do_update(
            index_elements=["name"],
            set_={
                "persona_id": row.id,
                "activated_by_user_id": principal.user_id,
                "activated_at": datetime.now(UTC),
            },
        )
    )
    await db.commit()
    await db.refresh(row)
    active_map = await _load_active_map(db)
    usage_map = await _load_usage_map(db)
    return _to_detail(row, active_map, usage_map)


@router.put("/{persona_id}", response_model=PersonaDetail, dependencies=_GUARD)
async def update_persona(
    persona_id: UUID,
    payload: PersonaUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PersonaDetail:
    """Cria nova versao copiando `persona_id` + aplicando patches.

    Versao base e imutavel. A nova versao NAO e ativada — chame
    PUT /{name}/active pra promover.
    """
    base = await _get_or_404(db, persona_id)
    next_version = await _next_version_for(db, base.name)

    new_row = AgentPersona(
        name=base.name,
        version=next_version,
        display_name=payload.display_name or base.display_name,
        role_block=payload.role_block if payload.role_block is not None else base.role_block,
        description=(
            payload.description if payload.description is not None else base.description
        ),
        expertise_domains=(
            payload.expertise_domains
            if payload.expertise_domains is not None
            else base.expertise_domains
        ),
        created_by_user_id=principal.user_id,
    )
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)
    active_map = await _load_active_map(db)
    usage_map = await _load_usage_map(db)
    return _to_detail(new_row, active_map, usage_map)


@router.put(
    "/{name}/active",
    response_model=PersonaVersionInfo,
    dependencies=_GUARD,
)
async def activate_version(
    name: str,
    payload: PersonaActivate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PersonaVersionInfo:
    """Promove `version_id` a versao ativa pra `name`."""
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
        pg_insert(AgentPersonaActive)
        .values(
            name=name,
            persona_id=target.id,
            activated_by_user_id=principal.user_id,
        )
        .on_conflict_do_update(
            index_elements=["name"],
            set_={
                "persona_id": target.id,
                "activated_by_user_id": principal.user_id,
                "activated_at": datetime.now(UTC),
            },
        )
    )
    await db.commit()
    active_map = await _load_active_map(db)
    usage_map = await _load_usage_map(db)
    return _to_version_info(target, active_map, usage_map)


@router.post(
    "/{persona_id}/archive",
    response_model=PersonaDetail,
    dependencies=_GUARD,
)
async def archive_version(
    persona_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PersonaDetail:
    """Soft-delete uma versao. Nao pode arquivar a versao ativa."""
    row = await _get_or_404(db, persona_id)

    active_map = await _load_active_map(db)
    if active_map.get(row.name) == row.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Nao e possivel arquivar a versao ativa de '{row.name}'. "
                "Ative outra versao primeiro."
            ),
        )

    row.archived_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    active_map = await _load_active_map(db)
    usage_map = await _load_usage_map(db)
    return _to_detail(row, active_map, usage_map)
