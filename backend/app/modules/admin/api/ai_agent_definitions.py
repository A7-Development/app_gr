"""Manage agent definitions (DB-backed) — system maintainer only.

Endpoints (F2.c.3 — CLAUDE.md §19.12):
    GET    /api/v1/admin/ia/agents             lista
    GET    /api/v1/admin/ia/agents/{id}        detalhe (persona/expertises/prompt expandidos)
    POST   /api/v1/admin/ia/agents             cria familia (vira v1, ativa)
    PUT    /api/v1/admin/ia/agents/{id}        cria nova versao
    PUT    /api/v1/admin/ia/agents/{name}/active  promove versao
    POST   /api/v1/admin/ia/agents/{id}/archive   soft-delete
    POST   /api/v1/admin/ia/agents/{id}/preview   renderiza system_text composto

Espelha pattern de ai_personas + ai_expertises mas com 3 sub-tabelas
relacionadas (persona, expertise[], prompt) resolvidas no detail/preview.

NAO confunde com `ai_agents.py` (legado): este novo arquivo serve em
`/ia/agents` (portugues), o legado em `/ai/agents` (ingles) continua de
pe pra agent_config (override de modelo legado) ate deprecation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.agents._compose import compose_system_text
from app.agentic.engine.prompts import repository as prompt_repo
from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.agent_code import derive_agent_code
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
from app.shared.ai.models.prompt import AIPrompt
from app.shared.ai.models.prompt_active import AIPromptActive
from app.shared.ai.schemas.agent_definition import (
    AgentDefinitionActivate,
    AgentDefinitionCreate,
    AgentDefinitionDetail,
    AgentDefinitionPreviewResponse,
    AgentDefinitionUpdate,
    AgentDefinitionVersionInfo,
    AgentExpertiseRef,
    AgentPersonaRef,
    AgentPromptRef,
    AgentRunRecent,
    AgentStatsByModel,
    AgentStatsResponse,
    AgentUsageOverviewRow,
)

router = APIRouter(prefix="/ia/agents", tags=["admin:ia-agents"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


# ─── Helpers ──────────────────────────────────────────────────────────────


async def _load_active_map(
    db: AsyncSession,
) -> dict[tuple[UUID | None, str], UUID]:
    """Retorna {(tenant_id, name): active_definition_id}."""
    rows = (await db.execute(select(AgentDefinitionActive))).scalars().all()
    return {(r.tenant_id, r.name): r.definition_id for r in rows}


async def _load_persona_map(db: AsyncSession) -> dict[UUID, AgentPersona]:
    """Carrega personas usadas (uma SELECT global — populacao pequena)."""
    rows = (await db.execute(select(AgentPersona))).scalars().all()
    return {r.id: r for r in rows}


async def _load_expertise_map(db: AsyncSession) -> dict[UUID, AgentExpertise]:
    rows = (await db.execute(select(AgentExpertise))).scalars().all()
    return {r.id: r for r in rows}


def _to_version_info(
    row: AgentDefinition,
    active_map: dict[tuple[UUID | None, str], UUID],
    persona_map: dict[UUID, AgentPersona],
    version_count: int = 1,
) -> AgentDefinitionVersionInfo:
    persona_name = None
    if row.persona_id is not None:
        p = persona_map.get(row.persona_id)
        if p is not None:
            persona_name = p.display_name
    return AgentDefinitionVersionInfo(
        id=row.id,
        code=derive_agent_code(row.name),
        name=row.name,
        version=row.version,
        version_count=version_count,
        module=row.module,
        persona_name=persona_name,
        expertise_count=len(row.expertise_ids or []),
        prompt_name=row.prompt_name,
        model=row.model,
        is_active=active_map.get((row.tenant_id, row.name)) == row.id,
        cross_module=row.cross_module,
        tenant_id=row.tenant_id,
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


async def _to_detail(
    db: AsyncSession,
    row: AgentDefinition,
    active_map: dict[tuple[UUID | None, str], UUID],
    persona_map: dict[UUID, AgentPersona],
    expertise_map: dict[UUID, AgentExpertise],
) -> AgentDefinitionDetail:
    persona_ref: AgentPersonaRef | None = None
    if row.persona_id is not None:
        p = persona_map.get(row.persona_id)
        if p is not None:
            persona_ref = AgentPersonaRef(
                id=p.id,
                name=p.name,
                display_name=p.display_name,
                version=p.version,
            )

    expertise_refs: list[AgentExpertiseRef] = []
    for eid in row.expertise_ids or []:
        e = expertise_map.get(eid)
        if e is not None:
            expertise_refs.append(
                AgentExpertiseRef(
                    id=e.id,
                    name=e.name,
                    display_name=e.display_name,
                    domain=e.domain,
                    version=e.version,
                )
            )

    # Prompt: resolve via repository pra pegar versao ativa
    prompt_ref: AgentPromptRef | None = None
    try:
        # Resolve so pra disparar PromptNotFoundError quando o prompt nao
        # existe (capturado abaixo). O `Prompt` dataclass nao carrega o id da
        # row; pra isso fazemos a query separada logo em seguida.
        await prompt_repo.resolve(db, name=row.prompt_name)
        prompt_row_stmt = (
            select(AIPrompt)
            .join(AIPromptActive, AIPromptActive.name == AIPrompt.name)
            .where(AIPrompt.name == row.prompt_name)
            .where(AIPrompt.version == AIPromptActive.active_version)
            .limit(1)
        )
        prow = (await db.execute(prompt_row_stmt)).scalar_one_or_none()
        if prow is not None:
            prompt_ref = AgentPromptRef(
                id=prow.id, name=prow.name, version=prow.version
            )
    except prompt_repo.PromptNotFoundError:
        # Prompt nao encontrado — editor mostra o name como texto, sem ref
        pass

    return AgentDefinitionDetail(
        id=row.id,
        code=derive_agent_code(row.name),
        name=row.name,
        version=row.version,
        module=row.module,
        persona=persona_ref,
        expertises=expertise_refs,
        prompt=prompt_ref,
        prompt_name=row.prompt_name,
        model=row.model,
        fallback_model=row.fallback_model,
        temperature=float(row.temperature) if row.temperature is not None else None,
        max_tokens=row.max_tokens,
        cross_module=row.cross_module,
        allowed_tools=row.allowed_tools,
        credit_hint=row.credit_hint,
        tenant_id=row.tenant_id,
        is_active=active_map.get((row.tenant_id, row.name)) == row.id,
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


async def _get_or_404(db: AsyncSession, definition_id: UUID) -> AgentDefinition:
    row = await db.get(AgentDefinition, definition_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agente nao encontrado."
        )
    return row


async def _next_version_for(
    db: AsyncSession, tenant_id: UUID | None, name: str
) -> int:
    stmt = (
        select(func.max(AgentDefinition.version))
        .where(AgentDefinition.name == name)
        .where(
            or_(
                AgentDefinition.tenant_id == tenant_id,
                # NULL == NULL fica False em SQL — comparacao explicita.
                (AgentDefinition.tenant_id.is_(None) if tenant_id is None else False),
            )
        )
    )
    current = (await db.execute(stmt)).scalar()
    return (current or 0) + 1


# ─── Endpoints ────────────────────────────────────────────────────────────


@router.get("", response_model=list[AgentDefinitionVersionInfo], dependencies=_GUARD)
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db)],
    include_archived: bool = False,
    module: str | None = None,
) -> list[AgentDefinitionVersionInfo]:
    """Lista 1 linha por AGENTE (familia name), nao por versao.

    Representante da familia = versao ATIVA (fallback: ultima nao-arquivada,
    senao a ultima). `version_count` = total de versoes da familia. Versoes
    sao detalhe da aba Versoes do cockpit — a lista nao incha quando se cria
    uma versao nova. `include_archived` mostra familias totalmente arquivadas.
    """
    stmt = select(AgentDefinition)
    if module:
        stmt = stmt.where(AgentDefinition.module == module)
    rows = (await db.execute(stmt)).scalars().all()
    active_map = await _load_active_map(db)
    persona_map = await _load_persona_map(db)

    # Agrupa por familia (tenant_id, name).
    families: dict[tuple[UUID | None, str], list[AgentDefinition]] = {}
    for r in rows:
        families.setdefault((r.tenant_id, r.name), []).append(r)

    out: list[AgentDefinitionVersionInfo] = []
    for (tenant_id, name), versions in families.items():
        active_id = active_map.get((tenant_id, name))
        live = [v for v in versions if v.archived_at is None]
        # Representante: ativa > ultima viva > ultima qualquer.
        rep = next((v for v in versions if v.id == active_id), None)
        if rep is None:
            pool = live or versions
            rep = max(pool, key=lambda v: v.version)
        family_archived = not live
        if family_archived and not include_archived:
            continue
        out.append(
            _to_version_info(rep, active_map, persona_map, version_count=len(versions))
        )

    out.sort(key=lambda x: (x.module, x.name))
    return out


@router.get(
    "/{definition_id}", response_model=AgentDefinitionDetail, dependencies=_GUARD
)
async def get_agent(
    definition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentDefinitionDetail:
    """Detalhe completo (persona/expertises/prompt expandidos pra editor)."""
    row = await _get_or_404(db, definition_id)
    active_map = await _load_active_map(db)
    persona_map = await _load_persona_map(db)
    expertise_map = await _load_expertise_map(db)
    return await _to_detail(db, row, active_map, persona_map, expertise_map)


@router.get(
    "/{definition_id}/versions",
    response_model=list[AgentDefinitionVersionInfo],
    dependencies=_GUARD,
)
async def list_agent_versions(
    definition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AgentDefinitionVersionInfo]:
    """Todas as versoes da familia a que `definition_id` pertence.

    A lista principal (GET "") colapsa 1 linha por agente; a aba Versoes do
    cockpit usa este endpoint pra ver/gerir as versoes individuais.
    """
    row = await _get_or_404(db, definition_id)
    stmt = (
        select(AgentDefinition)
        .where(AgentDefinition.name == row.name)
        .where(_tenant_cond(AgentDefinition.tenant_id, row.tenant_id))
        .order_by(AgentDefinition.version.desc())
    )
    versions = (await db.execute(stmt)).scalars().all()
    active_map = await _load_active_map(db)
    persona_map = await _load_persona_map(db)
    n = len(versions)
    return [
        _to_version_info(v, active_map, persona_map, version_count=n)
        for v in versions
    ]


@router.post(
    "",
    response_model=AgentDefinitionDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=_GUARD,
)
async def create_agent(
    payload: AgentDefinitionCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentDefinitionDetail:
    """Cria nova familia de agente (tenant_id=NULL — global). Falha 409 se
    name existe globalmente."""
    existing = (
        await db.execute(
            select(AgentDefinition)
            .where(AgentDefinition.name == payload.name)
            .where(AgentDefinition.tenant_id.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Agente '{payload.name}' ja existe — use PUT para criar nova versao."
            ),
        )

    row = AgentDefinition(
        tenant_id=None,  # globais no MVP; custom de tenant em F5
        name=payload.name,
        version=1,
        module=payload.module,
        persona_id=payload.persona_id,
        expertise_ids=payload.expertise_ids,
        prompt_name=payload.prompt_name,
        model=payload.model,
        fallback_model=payload.fallback_model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        cross_module=payload.cross_module,
        allowed_tools=payload.allowed_tools,
        credit_hint=payload.credit_hint,
        created_by_user_id=principal.user_id,
    )
    db.add(row)
    await db.flush()

    # Marca v1 como ativa.
    await db.execute(
        pg_insert(AgentDefinitionActive)
        .values(
            tenant_id=None,
            name=payload.name,
            definition_id=row.id,
            activated_by_user_id=principal.user_id,
        )
        .on_conflict_do_update(
            constraint="uq_agent_definition_active_tenant_name",
            set_={
                "definition_id": row.id,
                "activated_by_user_id": principal.user_id,
                "activated_at": datetime.now(UTC),
            },
        )
    )
    await db.commit()
    await db.refresh(row)
    active_map = await _load_active_map(db)
    persona_map = await _load_persona_map(db)
    expertise_map = await _load_expertise_map(db)
    return await _to_detail(db, row, active_map, persona_map, expertise_map)


@router.put(
    "/{definition_id}", response_model=AgentDefinitionDetail, dependencies=_GUARD
)
async def update_agent(
    definition_id: UUID,
    payload: AgentDefinitionUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentDefinitionDetail:
    """Cria nova versao copiando `definition_id` + aplicando patches.

    Versao base e imutavel. Nova versao NAO e ativada — chame
    PUT /{name}/active.
    """
    base = await _get_or_404(db, definition_id)
    next_version = await _next_version_for(db, base.tenant_id, base.name)

    def _coalesce(new_v, base_v):  # type: ignore[no-untyped-def]
        return new_v if new_v is not None else base_v

    new_row = AgentDefinition(
        tenant_id=base.tenant_id,
        name=base.name,
        version=next_version,
        module=base.module,
        persona_id=_coalesce(payload.persona_id, base.persona_id),
        expertise_ids=_coalesce(payload.expertise_ids, base.expertise_ids),
        prompt_name=_coalesce(payload.prompt_name, base.prompt_name),
        model=_coalesce(payload.model, base.model),
        fallback_model=_coalesce(payload.fallback_model, base.fallback_model),
        temperature=_coalesce(payload.temperature, base.temperature),
        max_tokens=_coalesce(payload.max_tokens, base.max_tokens),
        cross_module=_coalesce(payload.cross_module, base.cross_module),
        # None no payload herda a base; [] zera; [...] sobrescreve (mesma
        # semantica de expertise_ids).
        allowed_tools=_coalesce(payload.allowed_tools, base.allowed_tools),
        credit_hint=_coalesce(payload.credit_hint, base.credit_hint),
        created_by_user_id=principal.user_id,
    )
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)
    active_map = await _load_active_map(db)
    persona_map = await _load_persona_map(db)
    expertise_map = await _load_expertise_map(db)
    return await _to_detail(db, new_row, active_map, persona_map, expertise_map)


@router.put(
    "/{name}/active",
    response_model=AgentDefinitionVersionInfo,
    dependencies=_GUARD,
)
async def activate_version(
    name: str,
    payload: AgentDefinitionActivate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentDefinitionVersionInfo:
    """Promove `version_id` a versao ativa pra `name` global."""
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

    # Delete-then-insert NULL-safe. NAO usar ON CONFLICT (tenant_id, name): pra
    # agentes globais (tenant_id NULL) o Postgres trata NULL como distinto, o
    # conflito nao dispara e cada ativacao INSERE um ponteiro novo (duplica).
    # Removemos o ponteiro vigente de (tenant_id, name) — com `is_(None)` quando
    # global — e inserimos o novo.
    tenant_cond = (
        AgentDefinitionActive.tenant_id.is_(None)
        if target.tenant_id is None
        else AgentDefinitionActive.tenant_id == target.tenant_id
    )
    await db.execute(
        delete(AgentDefinitionActive).where(
            AgentDefinitionActive.name == name,
            tenant_cond,
        )
    )
    db.add(
        AgentDefinitionActive(
            tenant_id=target.tenant_id,
            name=name,
            definition_id=target.id,
            activated_by_user_id=principal.user_id,
        )
    )
    await db.commit()
    active_map = await _load_active_map(db)
    persona_map = await _load_persona_map(db)
    return _to_version_info(target, active_map, persona_map)


@router.post(
    "/{definition_id}/archive",
    response_model=AgentDefinitionDetail,
    dependencies=_GUARD,
)
async def archive_version(
    definition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentDefinitionDetail:
    """Soft-delete uma versao. Nao pode arquivar a versao ativa."""
    row = await _get_or_404(db, definition_id)
    active_map = await _load_active_map(db)
    if active_map.get((row.tenant_id, row.name)) == row.id:
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
    persona_map = await _load_persona_map(db)
    expertise_map = await _load_expertise_map(db)
    return await _to_detail(db, row, active_map, persona_map, expertise_map)


def _tenant_cond(col, tenant_id: UUID | None):
    """Comparacao NULL-safe de tenant_id (global = IS NULL)."""
    return col.is_(None) if tenant_id is None else col == tenant_id


@router.delete(
    "/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_GUARD,
)
async def delete_agent_version(
    definition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Exclui (hard-delete) UMA versao do agente.

    Guarda: se for a versao ATIVA e houver outras versoes, bloqueia (ative
    outra antes). Se for a unica versao, remove tambem o ponteiro ativo
    (equivale a excluir o agente). Agentes que vivem no CATALOG voltam a rodar
    pelo fallback do codigo — a tela nao quebra.
    """
    row = await _get_or_404(db, definition_id)
    active_map = await _load_active_map(db)
    is_active = active_map.get((row.tenant_id, row.name)) == row.id
    others = (
        await db.execute(
            select(func.count(AgentDefinition.id))
            .where(AgentDefinition.name == row.name)
            .where(AgentDefinition.id != row.id)
            .where(_tenant_cond(AgentDefinition.tenant_id, row.tenant_id))
        )
    ).scalar() or 0
    if is_active and others > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{row.name}' v{row.version} e a versao ativa. Ative outra "
                "versao antes de excluir, ou exclua o agente inteiro."
            ),
        )
    if is_active:
        await db.execute(
            delete(AgentDefinitionActive).where(
                AgentDefinitionActive.name == row.name,
                _tenant_cond(AgentDefinitionActive.tenant_id, row.tenant_id),
            )
        )
    await db.execute(delete(AgentDefinition).where(AgentDefinition.id == row.id))
    await db.commit()


@router.delete(
    "/{definition_id}/family",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_GUARD,
)
async def delete_agent_family(
    definition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Exclui (hard-delete) o AGENTE inteiro — todas as versoes da familia a
    que `definition_id` pertence + ponteiro ativo. Agente que vive no CATALOG
    volta a rodar pelo fallback do codigo (a tela nao quebra)."""
    row = await _get_or_404(db, definition_id)
    await db.execute(
        delete(AgentDefinitionActive).where(
            AgentDefinitionActive.name == row.name,
            _tenant_cond(AgentDefinitionActive.tenant_id, row.tenant_id),
        )
    )
    await db.execute(
        delete(AgentDefinition).where(
            AgentDefinition.name == row.name,
            _tenant_cond(AgentDefinition.tenant_id, row.tenant_id),
        )
    )
    await db.commit()


@router.post(
    "/{definition_id}/preview",
    response_model=AgentDefinitionPreviewResponse,
    dependencies=_GUARD,
)
async def preview_agent(
    definition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentDefinitionPreviewResponse:
    """Renderiza o system_text composto (persona + expertises + prompt em
    XML) que seria enviado ao LLM em runtime. Sem chamar LLM."""
    row = await _get_or_404(db, definition_id)

    # Carrega persona + expertises (versao ativa)
    persona: AgentPersona | None = None
    if row.persona_id is not None:
        persona_stmt = (
            select(AgentPersona)
            .join(
                AgentPersonaActive,
                AgentPersonaActive.persona_id == AgentPersona.id,
            )
            .where(AgentPersona.id == row.persona_id)
        )
        persona = (await db.execute(persona_stmt)).scalar_one_or_none()

    expertises: list[AgentExpertise] = []
    if row.expertise_ids:
        exp_stmt = (
            select(AgentExpertise)
            .join(
                AgentExpertiseActive,
                AgentExpertiseActive.expertise_id == AgentExpertise.id,
            )
            .where(AgentExpertise.id.in_(row.expertise_ids))
        )
        rows_exp = (await db.execute(exp_stmt)).scalars().all()
        by_id = {e.id: e for e in rows_exp}
        expertises = [by_id[eid] for eid in row.expertise_ids if eid in by_id]

    # Resolve prompt
    try:
        prompt = await prompt_repo.resolve(db, name=row.prompt_name)
    except prompt_repo.PromptNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Prompt '{row.prompt_name}' nao encontrado em ai_prompt. "
                "Crie/ative o prompt antes de fazer preview."
            ),
        ) from e

    # Renderiza com contexto fake (mesmo contexto que runtime usa)
    rendered = prompt.render(
        context={"page": "credito.dossie", "period": "", "filters": ""}
    )
    prompt_system_text = "\n\n".join(
        block.text
        for msg in rendered
        if msg.role == "system"
        for block in msg.content
    )

    # Compose com XML tags (mesma logica do runtime — F2.b.2)
    system_text = compose_system_text(
        persona=persona,
        expertises=expertises,
        prompt_system_text=prompt_system_text,
    )

    return AgentDefinitionPreviewResponse(
        name=row.name,
        version=row.version,
        system_text=system_text,
        persona_full_id=persona.full_id if persona else None,
        expertise_full_ids=[e.full_id for e in expertises],
        prompt_full_id=prompt.full_id,
        model=row.model or prompt.model_default,
        fallback_model=row.fallback_model,
        temperature=(
            float(row.temperature) if row.temperature is not None else None
        ),
        max_tokens=row.max_tokens,
    )


# ─── Telemetria (Fatia B) ──────────────────────────────────────────────────


def _f(v: object) -> float:
    """Coage Decimal/None -> float (0.0)."""
    return float(v) if v is not None else 0.0


@router.get(
    "/usage/overview",
    response_model=list[AgentUsageOverviewRow],
    dependencies=_GUARD,
)
async def agents_usage_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    window_days: int = 30,
) -> list[AgentUsageOverviewRow]:
    """Ranking de uso por agente (power-law do catalogo, read-only).

    Agrega `agent_analysis_run` por `agent_name`, cross-tenant, ordenado por
    total de execucoes. Rota static `/usage/overview` (2 segmentos) nao colide
    com `/{definition_id}`.
    """
    window_days = max(1, min(window_days, 365))
    rows = (
        await db.execute(
            text(
                "SELECT agent_name, "
                "  count(*) AS total_runs, "
                "  count(*) FILTER ("
                "    WHERE triggered_at >= now() - make_interval(days => :wd)"
                "  ) AS window_runs, "
                "  count(*) FILTER (WHERE status='error') AS runs_error, "
                "  coalesce(sum(cost_brl_estimated),0) AS cost_brl_total, "
                "  coalesce(sum(cost_brl_estimated) FILTER ("
                "    WHERE triggered_at >= now() - make_interval(days => :wd)"
                "  ),0) AS cost_brl_window, "
                "  coalesce(sum(tokens_input+tokens_output+tokens_cache_read"
                "    +tokens_cache_creation),0) AS tokens_total, "
                "  max(triggered_at) AS last_run_at "
                "FROM agent_analysis_run "
                "GROUP BY agent_name ORDER BY total_runs DESC"
            ).bindparams(wd=window_days)
        )
    ).all()
    return [
        AgentUsageOverviewRow(
            agent_name=r.agent_name,
            total_runs=r.total_runs,
            window_runs=r.window_runs,
            runs_error=r.runs_error,
            cost_brl_total=_f(r.cost_brl_total),
            cost_brl_window=_f(r.cost_brl_window),
            tokens_total=r.tokens_total,
            last_run_at=r.last_run_at,
        )
        for r in rows
    ]


@router.get(
    "/{definition_id}/stats",
    response_model=AgentStatsResponse,
    dependencies=_GUARD,
)
async def agent_stats(
    definition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    window_days: int = 30,
) -> AgentStatsResponse:
    """Telemetria de USO de um agente (read-only).

    Agrega `agent_analysis_run` por `agent_name` (familia de versoes),
    cross-tenant (visao do system maintainer). Esta e a unica fonte com
    atribuicao por agente — `ai_usage_event` nao carrega agent_id.
    """
    row = await _get_or_404(db, definition_id)
    name = row.name
    window_days = max(1, min(window_days, 365))

    # 1) Agregado all-time (contagens por status + tokens + custo + duracao).
    overall = (
        await db.execute(
            text(
                "SELECT count(*) AS total_runs, "
                "  count(*) FILTER (WHERE status='success') AS runs_success, "
                "  count(*) FILTER (WHERE status='error') AS runs_error, "
                "  count(*) FILTER (WHERE status='partial') AS runs_partial, "
                "  coalesce(sum(tokens_input),0) AS tokens_input, "
                "  coalesce(sum(tokens_output),0) AS tokens_output, "
                "  coalesce(sum(tokens_cache_read),0) AS tokens_cache_read, "
                "  coalesce(sum(tokens_cache_creation),0) AS tokens_cache_creation, "
                "  coalesce(sum(cost_brl_estimated),0) AS cost_brl_total, "
                "  avg(duration_ms) AS avg_duration_ms, "
                "  max(triggered_at) AS last_run_at "
                "FROM agent_analysis_run WHERE agent_name = :name"
            ).bindparams(name=name)
        )
    ).one()

    # 2) Janela (ultimos window_days).
    window = (
        await db.execute(
            text(
                "SELECT count(*) AS window_runs, "
                "  coalesce(sum(cost_brl_estimated),0) AS window_cost_brl, "
                "  coalesce(sum(tokens_input+tokens_output+tokens_cache_read"
                "    +tokens_cache_creation),0) AS window_tokens_total "
                "FROM agent_analysis_run "
                "WHERE agent_name = :name "
                "  AND triggered_at >= now() - make_interval(days => :wd)"
            ).bindparams(name=name, wd=window_days)
        )
    ).one()

    # 3) Quebra por modelo.
    by_model_rows = (
        await db.execute(
            text(
                "SELECT model_used AS model, count(*) AS runs, "
                "  coalesce(sum(tokens_input+tokens_output+tokens_cache_read"
                "    +tokens_cache_creation),0) AS tokens_total, "
                "  coalesce(sum(cost_brl_estimated),0) AS cost_brl "
                "FROM agent_analysis_run WHERE agent_name = :name "
                "GROUP BY model_used ORDER BY runs DESC"
            ).bindparams(name=name)
        )
    ).all()

    # 4) Execucoes recentes.
    recent_rows = (
        await db.execute(
            text(
                "SELECT agent_version AS version, model_used, status, "
                "  tokens_input, tokens_output, tokens_cache_read, "
                "  tokens_cache_creation, cost_brl_estimated AS cost_brl, "
                "  duration_ms, triggered_at "
                "FROM agent_analysis_run WHERE agent_name = :name "
                "ORDER BY triggered_at DESC LIMIT 10"
            ).bindparams(name=name)
        )
    ).all()

    return AgentStatsResponse(
        agent_name=name,
        window_days=window_days,
        total_runs=overall.total_runs,
        runs_success=overall.runs_success,
        runs_error=overall.runs_error,
        runs_partial=overall.runs_partial,
        tokens_input=overall.tokens_input,
        tokens_output=overall.tokens_output,
        tokens_cache_read=overall.tokens_cache_read,
        tokens_cache_creation=overall.tokens_cache_creation,
        cost_brl_total=_f(overall.cost_brl_total),
        avg_duration_ms=(
            _f(overall.avg_duration_ms)
            if overall.avg_duration_ms is not None
            else None
        ),
        last_run_at=overall.last_run_at,
        window_runs=window.window_runs,
        window_cost_brl=_f(window.window_cost_brl),
        window_tokens_total=window.window_tokens_total,
        by_model=[
            AgentStatsByModel(
                model=r.model,
                runs=r.runs,
                tokens_total=r.tokens_total,
                cost_brl=_f(r.cost_brl),
            )
            for r in by_model_rows
        ],
        recent_runs=[
            AgentRunRecent(
                version=r.version,
                model_used=r.model_used,
                status=r.status,
                tokens_input=r.tokens_input,
                tokens_output=r.tokens_output,
                tokens_cache_read=r.tokens_cache_read,
                tokens_cache_creation=r.tokens_cache_creation,
                cost_brl=_f(r.cost_brl) if r.cost_brl is not None else None,
                duration_ms=r.duration_ms,
                triggered_at=r.triggered_at,
            )
            for r in recent_rows
        ],
    )
