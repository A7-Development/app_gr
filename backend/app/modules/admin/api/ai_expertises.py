"""Manage agent expertises (DB-backed) — system maintainer only.

Endpoints:
    GET    /api/v1/admin/ia/expertises             lista todas as versoes
    GET    /api/v1/admin/ia/expertises/{id}        detalhe de uma versao
    POST   /api/v1/admin/ia/expertises             cria familia (vira v1, ativa)
    PUT    /api/v1/admin/ia/expertises/{id}        cria nova versao copiando + patches
    PUT    /api/v1/admin/ia/expertises/{name}/active  promove versao
    POST   /api/v1/admin/ia/expertises/{id}/archive   soft-delete (nao pode ativar)

Versoes sao IMUTAVEIS apos criadas. Espelha pattern de
`ai_personas.py` (CLAUDE.md §19.12).
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
from app.shared.ai.models.agent_expertise import AgentExpertise, AgentExpertiseActive
from app.shared.ai.schemas.expertise import (
    ExpertiseActivate,
    ExpertiseCreate,
    ExpertiseDetail,
    ExpertiseReference,
    ExpertiseUpdate,
    ExpertiseVersionInfo,
)

router = APIRouter(prefix="/ia/expertises", tags=["admin:ia-expertises"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


# ─── Helpers ──────────────────────────────────────────────────────────────


async def _load_active_map(db: AsyncSession) -> dict[str, UUID]:
    """Retorna {expertise_name: active_expertise_id}."""
    rows = (await db.execute(select(AgentExpertiseActive))).scalars().all()
    return {r.name: r.expertise_id for r in rows}


async def _load_usage_map(db: AsyncSession) -> dict[UUID, int]:
    """Retorna {expertise_id: count} — quantos agent_definition usam.

    Contagem feita expandindo o array `expertise_ids` via UNNEST. Cada
    agent_definition que TEM essa expertise no array conta 1 vez (mesmo
    que o array tenha duplicatas).
    """
    # PostgreSQL-specific: unnest the expertise_ids array and aggregate.
    stmt = (
        select(
            func.unnest(AgentDefinition.expertise_ids).label("expertise_id"),
            func.count().label("cnt"),
        )
        .where(AgentDefinition.expertise_ids.is_not(None))
        .where(AgentDefinition.archived_at.is_(None))
        .group_by("expertise_id")
    )
    return {row[0]: row[1] for row in (await db.execute(stmt)).all()}


def _refs_from_db(raw: list[dict] | None) -> list[ExpertiseReference] | None:
    if not raw:
        return None
    out: list[ExpertiseReference] = []
    for item in raw:
        try:
            out.append(ExpertiseReference(**item))
        except Exception:
            # Pular linha invalida — protege contra dado legado mal-formado.
            continue
    return out or None


def _refs_to_db(refs: list[ExpertiseReference] | None) -> list[dict] | None:
    if not refs:
        return None
    return [r.model_dump(exclude_none=True) for r in refs]


def _to_version_info(
    row: AgentExpertise,
    active_map: dict[str, UUID],
    usage_map: dict[UUID, int],
) -> ExpertiseVersionInfo:
    return ExpertiseVersionInfo(
        id=row.id,
        name=row.name,
        version=row.version,
        display_name=row.display_name,
        domain=row.domain,
        is_active=active_map.get(row.name) == row.id,
        usage_count=usage_map.get(row.id, 0),
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


def _to_detail(
    row: AgentExpertise,
    active_map: dict[str, UUID],
    usage_map: dict[UUID, int],
) -> ExpertiseDetail:
    return ExpertiseDetail(
        id=row.id,
        name=row.name,
        version=row.version,
        display_name=row.display_name,
        domain=row.domain,
        knowledge_text=row.knowledge_text,
        reference_urls=_refs_from_db(row.reference_urls),
        is_active=active_map.get(row.name) == row.id,
        usage_count=usage_map.get(row.id, 0),
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


async def _get_or_404(db: AsyncSession, expertise_id: UUID) -> AgentExpertise:
    row = await db.get(AgentExpertise, expertise_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Expertise nao encontrada."
        )
    return row


async def _next_version_for(db: AsyncSession, name: str) -> int:
    """Maior version+1 entre as rows com `name` (incluindo arquivadas)."""
    stmt = select(func.max(AgentExpertise.version)).where(
        AgentExpertise.name == name
    )
    current = (await db.execute(stmt)).scalar()
    return (current or 0) + 1


# ─── Endpoints ────────────────────────────────────────────────────────────


@router.get("", response_model=list[ExpertiseVersionInfo], dependencies=_GUARD)
async def list_expertises(
    db: Annotated[AsyncSession, Depends(get_db)],
    include_archived: bool = False,
    domain: str | None = None,
) -> list[ExpertiseVersionInfo]:
    """Lista todas as expertises + versoes, marcando a ativa por nome.

    Filtro `domain` opcional — agrupa por dominio (contabilidade, credito,
    risco, regulatorio, etc).
    """
    stmt = select(AgentExpertise).order_by(
        AgentExpertise.domain.asc(),
        AgentExpertise.name.asc(),
        AgentExpertise.version.desc(),
    )
    if not include_archived:
        stmt = stmt.where(AgentExpertise.archived_at.is_(None))
    if domain:
        stmt = stmt.where(AgentExpertise.domain == domain)
    rows = (await db.execute(stmt)).scalars().all()
    active_map = await _load_active_map(db)
    usage_map = await _load_usage_map(db)
    return [_to_version_info(r, active_map, usage_map) for r in rows]


@router.get("/{expertise_id}", response_model=ExpertiseDetail, dependencies=_GUARD)
async def get_expertise(
    expertise_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExpertiseDetail:
    """Detalhe completo de uma versao (knowledge_text markdown included)."""
    row = await _get_or_404(db, expertise_id)
    active_map = await _load_active_map(db)
    usage_map = await _load_usage_map(db)
    return _to_detail(row, active_map, usage_map)


@router.post(
    "",
    response_model=ExpertiseDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=_GUARD,
)
async def create_expertise(
    payload: ExpertiseCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExpertiseDetail:
    """Cria nova familia de expertise (vira v1). Falha 409 se `name` existe."""
    existing = (
        await db.execute(
            select(AgentExpertise).where(AgentExpertise.name == payload.name).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Expertise '{payload.name}' ja existe — use PUT para criar "
                "nova versao."
            ),
        )

    row = AgentExpertise(
        name=payload.name,
        version=1,
        display_name=payload.display_name,
        domain=payload.domain,
        knowledge_text=payload.knowledge_text,
        reference_urls=_refs_to_db(payload.reference_urls),
        created_by_user_id=principal.user_id,
    )
    db.add(row)
    await db.flush()

    await db.execute(
        pg_insert(AgentExpertiseActive)
        .values(
            name=payload.name,
            expertise_id=row.id,
            activated_by_user_id=principal.user_id,
        )
        .on_conflict_do_update(
            index_elements=["name"],
            set_={
                "expertise_id": row.id,
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


@router.put("/{expertise_id}", response_model=ExpertiseDetail, dependencies=_GUARD)
async def update_expertise(
    expertise_id: UUID,
    payload: ExpertiseUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExpertiseDetail:
    """Cria nova versao copiando `expertise_id` + aplicando patches.

    Versao base e imutavel. Nova versao NAO e ativada — chame
    PUT /{name}/active.
    """
    base = await _get_or_404(db, expertise_id)
    next_version = await _next_version_for(db, base.name)

    new_row = AgentExpertise(
        name=base.name,
        version=next_version,
        display_name=payload.display_name or base.display_name,
        domain=payload.domain or base.domain,
        knowledge_text=(
            payload.knowledge_text
            if payload.knowledge_text is not None
            else base.knowledge_text
        ),
        reference_urls=(
            _refs_to_db(payload.reference_urls)
            if payload.reference_urls is not None
            else base.reference_urls
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
    response_model=ExpertiseVersionInfo,
    dependencies=_GUARD,
)
async def activate_version(
    name: str,
    payload: ExpertiseActivate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExpertiseVersionInfo:
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
        pg_insert(AgentExpertiseActive)
        .values(
            name=name,
            expertise_id=target.id,
            activated_by_user_id=principal.user_id,
        )
        .on_conflict_do_update(
            index_elements=["name"],
            set_={
                "expertise_id": target.id,
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
    "/{expertise_id}/archive",
    response_model=ExpertiseDetail,
    dependencies=_GUARD,
)
async def archive_version(
    expertise_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExpertiseDetail:
    """Soft-delete uma versao. Nao pode arquivar a versao ativa."""
    row = await _get_or_404(db, expertise_id)

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
