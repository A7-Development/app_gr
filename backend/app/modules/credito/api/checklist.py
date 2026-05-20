"""Checklist CRUD endpoints — per-tenant analysis items.

Each tenant defines its own checklist of items the IA agents must evaluate.
Items with `tenant_id IS NULL` are starter packs from Strata. The runtime
of specialist agents (`app.agentic.engine.runtime`) reads the relevant items
in real time and injects them into the agent's prompt — prompts stay generic.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.credito.models.analysis_item import CreditAnalysisItem
from app.modules.credito.schemas.checklist import (
    ChecklistItemRead,
    ChecklistItemUpsert,
)

router = APIRouter()


@router.get("/checklist", response_model=list[ChecklistItemRead])
async def list_checklist(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
    section: str | None = None,
    include_starter: bool = True,
) -> list[ChecklistItemRead]:
    """List checklist items visible to this tenant.

    By default returns tenant-specific items + Strata starter pack items
    (`tenant_id IS NULL`). Pass `include_starter=false` to only see your own.
    """
    query = select(CreditAnalysisItem)

    if include_starter:
        query = query.where(
            or_(
                CreditAnalysisItem.tenant_id == principal.tenant_id,
                CreditAnalysisItem.tenant_id.is_(None),
            )
        )
    else:
        query = query.where(CreditAnalysisItem.tenant_id == principal.tenant_id)

    if section is not None:
        query = query.where(CreditAnalysisItem.section == section)

    query = query.order_by(
        CreditAnalysisItem.section,
        CreditAnalysisItem.order_index,
        CreditAnalysisItem.code,
    )
    rows = (await db.execute(query)).scalars().all()
    return [ChecklistItemRead.model_validate(r) for r in rows]


@router.post(
    "/checklist",
    response_model=ChecklistItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_checklist_item(
    payload: ChecklistItemUpsert,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> ChecklistItemRead:
    """Create a new checklist item for the current tenant."""
    item = CreditAnalysisItem(
        tenant_id=principal.tenant_id,
        section=payload.section,
        code=payload.code,
        description=payload.description,
        guidance=payload.guidance,
        severity=payload.severity,
        auto_evaluable=payload.auto_evaluable,
        order_index=payload.order_index,
        active=payload.active,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return ChecklistItemRead.model_validate(item)


@router.patch("/checklist/{item_id}", response_model=ChecklistItemRead)
async def update_checklist_item(
    item_id: UUID,
    payload: ChecklistItemUpsert,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> ChecklistItemRead:
    """Update a tenant-owned checklist item.

    Strata starter-pack items (tenant_id IS NULL) cannot be edited from here —
    the tenant must clone them first.
    """
    item = (
        await db.execute(
            select(CreditAnalysisItem).where(
                CreditAnalysisItem.id == item_id,
                CreditAnalysisItem.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Item nao encontrado. Itens do starter pack Strata nao podem "
                "ser editados — clone primeiro."
            ),
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)
    return ChecklistItemRead.model_validate(item)


@router.delete("/checklist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checklist_item(
    item_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.ADMIN)),
) -> None:
    item = (
        await db.execute(
            select(CreditAnalysisItem).where(
                CreditAnalysisItem.id == item_id,
                CreditAnalysisItem.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item nao encontrado.")

    await db.delete(item)
    await db.commit()


@router.post(
    "/checklist/{item_id}/clone",
    response_model=ChecklistItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def clone_starter_item(
    item_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> ChecklistItemRead:
    """Clone a Strata starter-pack item into a tenant-owned editable copy."""
    starter = (
        await db.execute(
            select(CreditAnalysisItem).where(
                CreditAnalysisItem.id == item_id,
                CreditAnalysisItem.tenant_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if starter is None:
        raise HTTPException(
            status_code=404,
            detail="Item starter pack nao encontrado.",
        )

    clone = CreditAnalysisItem(
        tenant_id=principal.tenant_id,
        section=starter.section,
        code=starter.code,
        description=starter.description,
        guidance=starter.guidance,
        severity=starter.severity,
        auto_evaluable=starter.auto_evaluable,
        order_index=starter.order_index,
        active=starter.active,
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    return ChecklistItemRead.model_validate(clone)
