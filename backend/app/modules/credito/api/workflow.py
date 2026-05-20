"""Workflow endpoints under /credito/workflows.

Wraps the generic workflow engine with credito-specific semantics:
- Tenant-scoped listing of workflow definitions (templates + own)
- Editor: GET/POST/PATCH definitions + activate
- Catalog: list available node types (with `available=False` flagging "em breve")
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission, WorkflowStatus
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.workflow.models.definition import (
    WorkflowDefinition,
    WorkflowDefinitionActive,
)
from app.shared.workflow.schemas.definition import (
    WorkflowActivatePayload,
    WorkflowDefinitionCreate,
    WorkflowDefinitionRead,
    WorkflowDefinitionUpdate,
    WorkflowGraph,
)
from app.shared.workflow.services.dry_run import dry_run_workflow
from app.shared.workflow.services.engine import list_node_types_for_editor
from app.shared.workflow.services.graph_validator import (
    ValidationResult,
    validate_graph,
)

router = APIRouter()


@router.get("/workflows", response_model=list[WorkflowDefinitionRead])
async def list_workflows(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> list[WorkflowDefinitionRead]:
    """List Strata templates + tenant's own workflows (category=credit)."""
    rows = (
        await db.execute(
            select(WorkflowDefinition)
            .where(
                WorkflowDefinition.category == "credit",
                or_(
                    WorkflowDefinition.tenant_id.is_(None),  # Strata templates
                    WorkflowDefinition.tenant_id == principal.tenant_id,
                ),
                WorkflowDefinition.archived_at.is_(None),
            )
            .order_by(WorkflowDefinition.created_at.desc())
        )
    ).scalars().all()
    return [WorkflowDefinitionRead.model_validate(r) for r in rows]


@router.get("/workflows/{workflow_id}", response_model=WorkflowDefinitionRead)
async def get_workflow(
    workflow_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> WorkflowDefinitionRead:
    row = (
        await db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == workflow_id,
                or_(
                    WorkflowDefinition.tenant_id.is_(None),
                    WorkflowDefinition.tenant_id == principal.tenant_id,
                ),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow nao encontrado.")
    return WorkflowDefinitionRead.model_validate(row)


@router.post(
    "/workflows",
    response_model=WorkflowDefinitionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow(
    payload: WorkflowDefinitionCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.ADMIN)),
) -> WorkflowDefinitionRead:
    """Create a new tenant-owned workflow (v1, status=DRAFT).

    Two modes:
    - From scratch: caller provides `graph` + `category`. Useful when
      starting empty or supplying a custom graph.
    - Clone: caller provides `clone_from` (UUID of a template/own workflow
      visible to them); we copy `graph` + `category` from the source.
    """
    if payload.clone_from is not None:
        source = (
            await db.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.id == payload.clone_from,
                    or_(
                        WorkflowDefinition.tenant_id.is_(None),
                        WorkflowDefinition.tenant_id == principal.tenant_id,
                    ),
                )
            )
        ).scalar_one_or_none()
        if source is None:
            raise HTTPException(
                status_code=404,
                detail="Workflow de origem (clone_from) nao encontrado ou nao acessivel.",
            )
        graph_dict = dict(source.graph)
        category = source.category
    else:
        if payload.graph is None or payload.category is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Para criar workflow do zero forneca `graph` + `category`, "
                    "ou use `clone_from` para clonar um existente."
                ),
            )
        graph_dict = payload.graph.model_dump()
        category = payload.category

    row = WorkflowDefinition(
        tenant_id=principal.tenant_id,
        name=payload.name,
        version=1,
        description=payload.description,
        category=category,
        graph=graph_dict,
        status=WorkflowStatus.DRAFT,
        created_by=principal.user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return WorkflowDefinitionRead.model_validate(row)


@router.patch("/workflows/{workflow_id}", response_model=WorkflowDefinitionRead)
async def update_workflow(
    workflow_id: UUID,
    payload: WorkflowDefinitionUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.ADMIN)),
) -> WorkflowDefinitionRead:
    """Create a new VERSION of an existing workflow (immutable history)."""
    base = (
        await db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == workflow_id,
                WorkflowDefinition.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if base is None:
        raise HTTPException(status_code=404, detail="Workflow nao encontrado ou nao editavel.")

    new_row = WorkflowDefinition(
        tenant_id=base.tenant_id,
        name=base.name,
        version=base.version + 1,
        description=payload.description if payload.description is not None else base.description,
        category=base.category,
        graph=payload.graph.model_dump(),
        status=WorkflowStatus.DRAFT,
        created_by=principal.user_id,
    )
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)
    return WorkflowDefinitionRead.model_validate(new_row)


@router.delete(
    "/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_workflow(
    workflow_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.ADMIN)),
) -> None:
    """Delete a tenant-owned workflow definition.

    Constraints:
    - Only DRAFT versions can be deleted (preserves audit trail of executed runs).
    - Only the tenant owner can delete (Strata templates are immutable).
    - The active version cannot be deleted — activate another first.
    """
    row = (
        await db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == workflow_id,
                WorkflowDefinition.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Workflow nao encontrado ou nao pertence ao tenant.",
        )
    if row.status != WorkflowStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=(
                "Somente versoes em DRAFT podem ser deletadas. Versoes ARCHIVED "
                "ficam por auditoria e ACTIVE precisa ser substituida primeiro."
            ),
        )

    # Block delete if it's currently active.
    active = (
        await db.execute(
            select(WorkflowDefinitionActive).where(
                WorkflowDefinitionActive.active_definition_id == workflow_id
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        raise HTTPException(
            status_code=400,
            detail="Esta versao esta ativa. Ative outra antes de deletar.",
        )

    await db.delete(row)
    await db.commit()


@router.put(
    "/workflows/{name}/active",
    response_model=WorkflowDefinitionRead,
)
async def activate_workflow(
    name: str,
    payload: WorkflowActivatePayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.ADMIN)),
) -> WorkflowDefinitionRead:
    """Set `definition_id` as the tenant's active version of `name`.

    The definition must:
    - Have the same `name` as the path param
    - Belong to the tenant (or be a Strata starter — in which case the
      tenant pointer is created scoped to the tenant)
    - Not be ARCHIVED

    Atomic via UPSERT on `workflow_definition_active`.
    """
    target = (
        await db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == payload.definition_id,
                WorkflowDefinition.name == name,
                or_(
                    WorkflowDefinition.tenant_id.is_(None),
                    WorkflowDefinition.tenant_id == principal.tenant_id,
                ),
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=404,
            detail="Versao nao encontrada para esse nome de workflow.",
        )
    if target.status == WorkflowStatus.ARCHIVED:
        raise HTTPException(
            status_code=400,
            detail="Nao e possivel ativar uma versao ARCHIVED.",
        )

    # Gate de validação semântica (Fase 2). DRAFT pode ser inválido — você
    # constrói incrementalmente. Mas ATIVAR um fluxo que vai rodar em prod
    # com erro estrutural é bloqueado: 422 com lista de erros pra UI mostrar.
    graph_obj = WorkflowGraph.model_validate(target.graph)
    val = validate_graph(graph_obj)
    if val.has_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Esta versao tem erros de validacao e nao pode ser ativada. "
                    "Corrija no editor e tente novamente."
                ),
                "validation": _validation_to_response(val),
            },
        )

    # Find existing active pointer for this (name, tenant) — same tenant scope
    # as the target. If target is a Strata starter (tenant_id IS NULL), the
    # ACTIVE pointer is also tenant-scoped (we create one for THIS tenant).
    pointer_tenant_id = principal.tenant_id

    existing = (
        await db.execute(
            select(WorkflowDefinitionActive).where(
                WorkflowDefinitionActive.name == name,
                WorkflowDefinitionActive.tenant_id == pointer_tenant_id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.active_definition_id = payload.definition_id
        existing.activated_by = principal.user_id
        # `activated_at` updated automatically by the model? Use func.now().
        from sqlalchemy.sql import func

        existing.activated_at = func.now()
    else:
        db.add(
            WorkflowDefinitionActive(
                id=uuid4(),
                name=name,
                tenant_id=pointer_tenant_id,
                active_definition_id=payload.definition_id,
                activated_by=principal.user_id,
            )
        )

    # Promote target to ACTIVE if it was DRAFT.
    if target.status == WorkflowStatus.DRAFT:
        target.status = WorkflowStatus.ACTIVE

    # (Optional) other versions of the same name from this tenant could be
    # archived here. For now we don't auto-archive — user can archive
    # explicitly. Multiple ACTIVE rows existing for different versions of
    # the same name is fine because only ONE is pointed-to by *_active.

    await db.commit()
    await db.refresh(target)
    return WorkflowDefinitionRead.model_validate(target)


@router.get(
    "/workflows/{name}/active",
    response_model=WorkflowDefinitionRead,
)
async def get_active_workflow(
    name: str,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> WorkflowDefinitionRead:
    """Return the active workflow definition for `name` for this tenant.

    Resolution order:
    1. Tenant-specific pointer in `workflow_definition_active`
    2. Strata starter pointer (`tenant_id IS NULL`) as fallback
    """
    pointer = (
        await db.execute(
            select(WorkflowDefinitionActive).where(
                WorkflowDefinitionActive.name == name,
                WorkflowDefinitionActive.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()

    if pointer is None:
        pointer = (
            await db.execute(
                select(WorkflowDefinitionActive).where(
                    WorkflowDefinitionActive.name == name,
                    WorkflowDefinitionActive.tenant_id.is_(None),
                )
            )
        ).scalar_one_or_none()

    if pointer is None:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhuma versao ativa para '{name}'.",
        )

    target = (
        await db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == pointer.active_definition_id
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=500,
            detail="Pointer ativo aponta para definition inexistente — DB inconsistente.",
        )

    return WorkflowDefinitionRead.model_validate(target)


@router.get("/node-types")
async def get_node_types_catalog(
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> list[dict]:
    """Return the catalog of node types for the visual editor palette.

    Includes types marked `available=False` so the UI can render them as
    "em breve" — selling the future vision without confusing users.
    """
    return list_node_types_for_editor()


@router.get("/agent-catalog")
async def get_agent_catalog(
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> list[dict]:
    """Return per-agent metadata for the editor's input-binding UI.

    The `/node-types` endpoint exposes node TYPES (one entry for
    `specialist_agent`); this endpoint exposes the AGENTS that live behind
    that single node type — each with its declared input contract
    (`inputs: [{name, type, description, optional}]`) so the frontend can
    render the slot-binding UI.

    Source of truth: `app.agentic.engine.catalog.CATALOG`.
    """
    from app.agentic.engine.catalog import CATALOG

    return [
        {
            "name": spec.name,
            "description": spec.description,
            "section_id": spec.section_id,
            "multimodal": spec.multimodal,
            "inputs": [
                {
                    "name": slot.name,
                    "type": slot.type.value,
                    "description": slot.description,
                    "optional": slot.optional,
                }
                for slot in spec.inputs
            ],
        }
        for spec in CATALOG.values()
    ]


# ─── Semantic validation ──────────────────────────────────────────────────


def _validation_to_response(result: ValidationResult) -> dict:
    """Serialize ValidationResult (dataclasses) for JSON response.

    `produced_by_node` is REQUIRED by the editor frontend's RefField
    (variable picker) — it lists what each upstream node publishes so the
    user can pick a typed variable. Drop it and the picker silently shows
    "nenhuma variavel disponivel" mesmo quando o human_input upstream tem
    fields declarados.
    """
    return {
        "has_errors": result.has_errors,
        "errors": [asdict(e) for e in result.errors],
        "produced_by_node": result.produced_by_node,
    }


@router.post("/workflows/_validate")
async def validate_workflow_graph(
    graph: Annotated[WorkflowGraph, Body(embed=False)],
    _principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> dict:
    """Run semantic validation on a graph WITHOUT persisting it.

    Used by the editor to give immediate feedback before save/activate. The
    response shape is:
        {
            "has_errors": bool,
            "errors": [
                {"node_id": str, "severity": "error|warning",
                 "code": str, "message": str (pt-BR), ...}
            ],
            "produced_by_node": {
                "<node_id>": {"<var_name>": "<vartype_str>", ...}
            }
        }
    """
    result = validate_graph(graph)
    return _validation_to_response(result)


class _DryRunPayload(BaseModel):
    """Body do POST /workflows/{id}/dry-run.

    `trigger_data` é o seed que o engine real receberia em
    `dossier_svc.create_dossier` (ex.: `{cnpj, target_name, ...}`).
    """

    trigger_data: dict[str, Any] = Field(default_factory=dict)


@router.post("/workflows/{workflow_id}/dry-run")
async def dry_run_workflow_endpoint(
    workflow_id: UUID,
    payload: _DryRunPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> dict:
    """Executa o grafo do workflow em modo SANDBOX.

    Não toca DB, não chama Serasa nem Anthropic. Cada nó produz output
    mock baseado em `produces()` (Fase 2). Útil pro editor "Testar" antes
    de criar dossier real e queimar requisição paga de bureau.
    """
    base = (
        await db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == workflow_id,
                or_(
                    WorkflowDefinition.tenant_id.is_(None),
                    WorkflowDefinition.tenant_id == principal.tenant_id,
                ),
            )
        )
    ).scalar_one_or_none()
    if base is None:
        raise HTTPException(
            status_code=404, detail="Workflow nao encontrado ou nao acessivel."
        )
    graph = WorkflowGraph.model_validate(base.graph)
    result = dry_run_workflow(graph, trigger_data=payload.trigger_data)
    return {
        "final_status": result.final_status,
        "error": result.error,
        "steps": [asdict(s) for s in result.steps],
    }


# ─── Existing endpoint extensions ─────────────────────────────────────────
# (Activation is gated by validation: cannot activate a graph with errors.)
