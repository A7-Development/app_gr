"""Document template CRUD endpoints — per-tenant doc extraction templates.

Each tenant defines its own templates (ex: "Relatorio Onboard A7") that
guide the document_extractor agent. Strata-provided templates use
`tenant_id IS NULL` and any tenant can use or clone them.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import DocumentType, Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.credito.models.document_template import CreditDocumentTemplate
from app.modules.credito.schemas.template import (
    DocumentTemplateRead,
    DocumentTemplateUpsert,
)

router = APIRouter()


@router.get("/templates", response_model=list[DocumentTemplateRead])
async def list_templates(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
    doc_type: DocumentType | None = None,
    include_starter: bool = True,
) -> list[DocumentTemplateRead]:
    query = select(CreditDocumentTemplate)

    if include_starter:
        query = query.where(
            or_(
                CreditDocumentTemplate.tenant_id == principal.tenant_id,
                CreditDocumentTemplate.tenant_id.is_(None),
            )
        )
    else:
        query = query.where(CreditDocumentTemplate.tenant_id == principal.tenant_id)

    if doc_type is not None:
        query = query.where(CreditDocumentTemplate.doc_type == doc_type)

    query = query.order_by(
        CreditDocumentTemplate.doc_type,
        CreditDocumentTemplate.name,
    )
    rows = (await db.execute(query)).scalars().all()
    return [DocumentTemplateRead.model_validate(r) for r in rows]


@router.post(
    "/templates",
    response_model=DocumentTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    payload: DocumentTemplateUpsert,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DocumentTemplateRead:
    template = CreditDocumentTemplate(
        tenant_id=principal.tenant_id,
        doc_type=payload.doc_type,
        name=payload.name,
        description=payload.description,
        fields_schema=payload.fields_schema,
        instructions=payload.instructions,
        active=payload.active,
        created_by=principal.user_id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return DocumentTemplateRead.model_validate(template)


@router.patch("/templates/{template_id}", response_model=DocumentTemplateRead)
async def update_template(
    template_id: UUID,
    payload: DocumentTemplateUpsert,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DocumentTemplateRead:
    template = (
        await db.execute(
            select(CreditDocumentTemplate).where(
                CreditDocumentTemplate.id == template_id,
                CreditDocumentTemplate.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Template nao encontrado. Templates do starter pack Strata "
                "nao podem ser editados — clone primeiro."
            ),
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, field, value)

    await db.commit()
    await db.refresh(template)
    return DocumentTemplateRead.model_validate(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.ADMIN)),
) -> None:
    template = (
        await db.execute(
            select(CreditDocumentTemplate).where(
                CreditDocumentTemplate.id == template_id,
                CreditDocumentTemplate.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template nao encontrado.")

    await db.delete(template)
    await db.commit()


@router.post(
    "/templates/{template_id}/clone",
    response_model=DocumentTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
async def clone_starter_template(
    template_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DocumentTemplateRead:
    starter = (
        await db.execute(
            select(CreditDocumentTemplate).where(
                CreditDocumentTemplate.id == template_id,
                CreditDocumentTemplate.tenant_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if starter is None:
        raise HTTPException(status_code=404, detail="Template starter nao encontrado.")

    clone = CreditDocumentTemplate(
        tenant_id=principal.tenant_id,
        doc_type=starter.doc_type,
        name=f"{starter.name} (copia)",
        description=starter.description,
        fields_schema=dict(starter.fields_schema),
        instructions=starter.instructions,
        active=starter.active,
        created_by=principal.user_id,
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    return DocumentTemplateRead.model_validate(clone)
