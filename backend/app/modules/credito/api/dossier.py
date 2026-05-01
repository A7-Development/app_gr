"""Dossier endpoints under /credito/dossies.

All endpoints are guarded by `require_module(Module.CREDITO, ...)`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import DossierStatus, Module, NodeRunStatus, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.credito.schemas.dossier import (
    DossierCreate,
    DossierListItem,
    DossierRead,
    DossierStateResponse,
    DossierUpdate,
    NodeSubmitPayload,
)
from app.modules.credito.services import dossier as dossier_svc
from app.shared.workflow.models.run import WorkflowNodeRun, WorkflowRun
from app.shared.workflow.services import engine as workflow_engine

router = APIRouter()


@router.get("/dossies", response_model=list[DossierListItem])
async def list_dossies(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
    status_filter: DossierStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[DossierListItem]:
    rows = await dossier_svc.list_dossiers(
        db,
        tenant_id=principal.tenant_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [DossierListItem.model_validate(r) for r in rows]


@router.post("/dossies", response_model=DossierRead, status_code=status.HTTP_201_CREATED)
async def create_dossie(
    payload: DossierCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DossierRead:
    dossier = await dossier_svc.create_dossier(
        db,
        tenant_id=principal.tenant_id,
        target_cnpj=payload.target_cnpj,
        target_name=payload.target_name,
        workflow_definition_id=payload.workflow_definition_id,
        analyst_id=principal.user_id,
        operation_type=payload.operation_type,
        requested_amount=payload.requested_amount,
        requested_term_days=payload.requested_term_days,
        notes=payload.notes,
    )
    await db.commit()
    return DossierRead.model_validate(dossier)


@router.get("/dossies/{dossier_id}", response_model=DossierRead)
async def get_dossie(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> DossierRead:
    dossier = await dossier_svc.get_dossier(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    if dossier is None:
        raise HTTPException(status_code=404, detail="Dossie nao encontrado.")
    return DossierRead.model_validate(dossier)


@router.patch("/dossies/{dossier_id}", response_model=DossierRead)
async def update_dossie(
    dossier_id: UUID,
    payload: DossierUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DossierRead:
    dossier = await dossier_svc.get_dossier(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    if dossier is None:
        raise HTTPException(status_code=404, detail="Dossie nao encontrado.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dossier, field, value)

    await db.commit()
    return DossierRead.model_validate(dossier)


# ─── Workflow state + submission ──────────────────────────────────────────


@router.get("/dossies/{dossier_id}/state", response_model=DossierStateResponse)
async def get_dossie_state(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> DossierStateResponse:
    """Combined dossier + workflow_run + node_runs view.

    The dossier detail page polls this to render the live state of the
    workflow: which nodes ran, which is currently waiting for input,
    what the outputs are.
    """
    dossier = await dossier_svc.get_dossier(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    if dossier is None:
        raise HTTPException(status_code=404, detail="Dossie nao encontrado.")

    run = None
    node_runs_data: list[dict] = []
    pending_node: dict | None = None

    if dossier.workflow_run_id is not None:
        run_row = (
            await db.execute(
                select(WorkflowRun).where(WorkflowRun.id == dossier.workflow_run_id)
            )
        ).scalar_one_or_none()
        if run_row is not None:
            run = {
                "id": str(run_row.id),
                "status": run_row.status.value if hasattr(run_row.status, "value") else str(run_row.status),
                "started_at": run_row.started_at.isoformat() if run_row.started_at else None,
                "completed_at": run_row.completed_at.isoformat() if run_row.completed_at else None,
                "paused_at": run_row.paused_at.isoformat() if run_row.paused_at else None,
                "trigger_data": run_row.trigger_data or {},
                "context_data": run_row.context_data or {},
                "error_detail": run_row.error_detail,
            }

            nr_rows = (
                await db.execute(
                    select(WorkflowNodeRun)
                    .where(WorkflowNodeRun.run_id == run_row.id)
                    .order_by(WorkflowNodeRun.started_at.asc().nulls_last())
                )
            ).scalars().all()

            for nr in nr_rows:
                row = {
                    "id": str(nr.id),
                    "node_id": nr.node_id,
                    "node_type": nr.node_type,
                    "status": nr.status.value if hasattr(nr.status, "value") else str(nr.status),
                    "input_data": nr.input_data or {},
                    "output_data": nr.output_data or {},
                    "started_at": nr.started_at.isoformat() if nr.started_at else None,
                    "completed_at": nr.completed_at.isoformat() if nr.completed_at else None,
                    "duration_ms": nr.duration_ms,
                    "tokens_input": nr.tokens_input,
                    "tokens_output": nr.tokens_output,
                    "cost_brl": str(nr.cost_brl) if nr.cost_brl is not None else "0",
                    "error_detail": nr.error_detail,
                    "attempt_number": nr.attempt_number,
                }
                node_runs_data.append(row)

                # Identify the pending node — first one in WAITING_INPUT.
                if pending_node is None and nr.status == NodeRunStatus.WAITING_INPUT:
                    pending_node = row

    return DossierStateResponse(
        dossier=DossierRead.model_validate(dossier),
        run=run,
        node_runs=node_runs_data,
        pending_node=pending_node,
    )


@router.post(
    "/dossies/{dossier_id}/nodes/{node_id}/submit",
    response_model=DossierStateResponse,
)
async def submit_node_input(
    dossier_id: UUID,
    node_id: str,
    payload: NodeSubmitPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DossierStateResponse:
    """Submit values to a paused human_input/human_review node and resume.

    Resolves the dossier's workflow_run, validates that `node_id` is the
    one currently waiting for input, calls `engine.resume_run` with the
    submitted values, then returns the updated state.
    """
    dossier = await dossier_svc.get_dossier(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    if dossier is None:
        raise HTTPException(status_code=404, detail="Dossie nao encontrado.")
    if dossier.workflow_run_id is None:
        raise HTTPException(
            status_code=400,
            detail="Dossie nao tem workflow run associado.",
        )

    # Validate the run is paused and node is awaiting input.
    waiting = (
        await db.execute(
            select(WorkflowNodeRun).where(
                WorkflowNodeRun.run_id == dossier.workflow_run_id,
                WorkflowNodeRun.node_id == node_id,
                WorkflowNodeRun.status == NodeRunStatus.WAITING_INPUT,
            )
        )
    ).scalar_one_or_none()
    if waiting is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No '{node_id}' nao esta aguardando input. "
                "Talvez ja tenha sido submetido ou o workflow esteja em outro estado."
            ),
        )

    # Mark this node row as completed by removing it (engine will create a
    # new node_run row when it re-executes the node with pending_input).
    waiting.status = NodeRunStatus.COMPLETED
    waiting.output_data = {**(waiting.output_data or {}), "_superseded": True}
    await db.flush()

    # Resume the workflow run with the submitted values.
    await workflow_engine.resume_run(
        db,
        run_id=dossier.workflow_run_id,
        pending_inputs={node_id: dict(payload.values)},
    )

    # Sync dossier status from updated workflow run.
    await dossier_svc.sync_status_from_workflow(db, dossier=dossier)
    await db.commit()

    # Return the fresh state.
    return await get_dossie_state(
        dossier_id=dossier_id,
        principal=principal,
        db=db,
    )
