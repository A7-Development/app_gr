"""CRUD admin de Servidores MCP — /api/v1/admin/ia/mcp (spec copiloto-mcp §7).

Padrao versionado (espelha ai_agent_definitions): edicao cria nova versao
(sem ativar); ativacao move o ponteiro em `mcp_server_active` (rollback de
1 UPDATE). `POST /{id}/test` = probe barato (initialize + tools/list, sem
custo de dataset) via `agentic.mcp.public.probe_server`.

Guard: system maintainer + ADMIN/ADMIN (gestao global de IA, §19.1).
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.mcp.public import McpServer, McpServerActive, probe_server
from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.ai.schemas.mcp import (
    McpProbeResponse,
    McpServerActivate,
    McpServerCreate,
    McpServerDetail,
    McpServerUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ia/mcp", tags=["admin:ia-mcp"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


async def _active_ids(db: AsyncSession) -> set[UUID]:
    rows = (await db.execute(select(McpServerActive.server_id))).scalars().all()
    return set(rows)


def _to_detail(row: McpServer, active_ids: set[UUID]) -> McpServerDetail:
    return McpServerDetail(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        version=row.version,
        url=row.url,
        transport=row.transport.value,
        module=row.module,
        credential_id=row.credential_id,
        auth_header_map=row.auth_header_map,
        allowed_tools=row.allowed_tools,
        mode=row.mode.value,
        cost_hint=row.cost_hint,
        max_calls_per_turn=row.max_calls_per_turn,
        tool_result_max_chars=row.tool_result_max_chars,
        description=row.description,
        created_at=row.created_at,
        archived_at=row.archived_at,
        is_active=row.id in active_ids,
    )


async def _get_or_404(db: AsyncSession, server_id: UUID) -> McpServer:
    row = await db.get(McpServer, server_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Servidor MCP nao encontrado.",
        )
    return row


@router.get("", dependencies=_GUARD, response_model=list[McpServerDetail])
async def list_servers(
    db: Annotated[AsyncSession, Depends(get_db)],
    include_archived: bool = False,
) -> list[McpServerDetail]:
    """Todas as versoes, mais recente primeiro (o front colapsa por familia)."""
    stmt = select(McpServer).order_by(McpServer.name, McpServer.version.desc())
    rows = (await db.execute(stmt)).scalars().all()
    active = await _active_ids(db)
    out = [_to_detail(r, active) for r in rows]
    if not include_archived:
        out = [d for d in out if d.archived_at is None or d.is_active]
    return out


@router.get("/{server_id}", dependencies=_GUARD, response_model=McpServerDetail)
async def get_server(
    server_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> McpServerDetail:
    row = await _get_or_404(db, server_id)
    return _to_detail(row, await _active_ids(db))


@router.post(
    "",
    dependencies=_GUARD,
    response_model=McpServerDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_server(
    payload: McpServerCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> McpServerDetail:
    """Cria a v1 da familia e ativa. Nome ja existente -> 409."""
    exists = (
        await db.execute(
            select(func.count())
            .select_from(McpServer)
            .where(McpServer.name == payload.name)
        )
    ).scalar_one()
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ja existe servidor MCP com nome '{payload.name}'.",
        )

    row = McpServer(
        tenant_id=None,
        name=payload.name,
        version=1,
        url=payload.url,
        transport=payload.transport,
        module=payload.module,
        credential_id=payload.credential_id,
        auth_header_map=payload.auth_header_map,
        allowed_tools=payload.allowed_tools,
        mode=payload.mode,
        cost_hint=payload.cost_hint,
        max_calls_per_turn=payload.max_calls_per_turn,
        tool_result_max_chars=payload.tool_result_max_chars,
        description=payload.description,
        created_by_user_id=principal.user_id,
    )
    db.add(row)
    await db.flush()

    stmt = pg_insert(McpServerActive).values(
        tenant_id=None,
        name=row.name,
        server_id=row.id,
        activated_by_user_id=principal.user_id,
    )
    await db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_mcp_server_active_tenant_name",
            set_={"server_id": row.id, "activated_by_user_id": principal.user_id},
        )
    )
    await db.commit()
    return _to_detail(row, {row.id})


def _coalesce(new, base):
    return new if new is not None else base


@router.put("/{server_id}", dependencies=_GUARD, response_model=McpServerDetail)
async def update_server(
    server_id: UUID,
    payload: McpServerUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> McpServerDetail:
    """Copia a versao base + patches -> NOVA versao (imutavel; NAO ativa)."""
    base = await _get_or_404(db, server_id)
    next_version = (
        await db.execute(
            select(func.max(McpServer.version)).where(McpServer.name == base.name)
        )
    ).scalar_one() + 1

    row = McpServer(
        tenant_id=base.tenant_id,
        name=base.name,
        version=next_version,
        url=_coalesce(payload.url, base.url),
        transport=_coalesce(payload.transport, base.transport),
        module=_coalesce(payload.module, base.module),
        credential_id=_coalesce(payload.credential_id, base.credential_id),
        auth_header_map=_coalesce(payload.auth_header_map, base.auth_header_map),
        allowed_tools=_coalesce(payload.allowed_tools, base.allowed_tools),
        mode=_coalesce(payload.mode, base.mode),
        cost_hint=_coalesce(payload.cost_hint, base.cost_hint),
        max_calls_per_turn=_coalesce(
            payload.max_calls_per_turn, base.max_calls_per_turn
        ),
        tool_result_max_chars=_coalesce(
            payload.tool_result_max_chars, base.tool_result_max_chars
        ),
        description=_coalesce(payload.description, base.description),
        created_by_user_id=principal.user_id,
    )
    db.add(row)
    await db.commit()
    return _to_detail(row, await _active_ids(db))


@router.put("/{name}/active", dependencies=_GUARD, response_model=McpServerDetail)
async def activate_version(
    name: str,
    payload: McpServerActivate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> McpServerDetail:
    """Move o ponteiro ativo da familia para a versao pedida (rollback 1 call)."""
    row = (
        await db.execute(
            select(McpServer).where(
                McpServer.name == name, McpServer.version == payload.version
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Versao v{payload.version} de '{name}' nao existe.",
        )
    if row.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Versao arquivada nao pode ser ativada.",
        )

    stmt = pg_insert(McpServerActive).values(
        tenant_id=None,
        name=name,
        server_id=row.id,
        activated_by_user_id=principal.user_id,
    )
    await db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_mcp_server_active_tenant_name",
            set_={"server_id": row.id, "activated_by_user_id": principal.user_id},
        )
    )
    await db.commit()
    return _to_detail(row, {row.id})


@router.post("/{server_id}/archive", dependencies=_GUARD, response_model=McpServerDetail)
async def archive_version(
    server_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> McpServerDetail:
    """Soft-delete de uma versao. Versao ativa nao pode ser arquivada."""
    row = await _get_or_404(db, server_id)
    active = await _active_ids(db)
    if row.id in active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Versao ativa nao pode ser arquivada — ative outra antes.",
        )
    from datetime import UTC, datetime

    row.archived_at = datetime.now(UTC)
    await db.commit()
    return _to_detail(row, active)


@router.post("/{server_id}/test", dependencies=_GUARD, response_model=McpProbeResponse)
async def test_connection(
    server_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> McpProbeResponse:
    """Probe de conexao (initialize + tools/list) — sem custo de dataset."""
    row = await _get_or_404(db, server_id)
    try:
        result = await probe_server(db, row)
        return McpProbeResponse(**result)
    except Exception as exc:
        logger.warning("Probe MCP '%s' falhou: %s", row.name, exc)
        return McpProbeResponse(ok=False, error=str(exc))
