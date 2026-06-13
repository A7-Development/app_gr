"""Dossier endpoints under /credito/dossies.

All endpoints are guarded by `require_module(Module.CREDITO, ...)`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.models.definition import PlaybookDefinition
from app.agentic.playbooks.models.run import PlaybookRun, PlaybookRunStep
from app.agentic.playbooks.schemas.definition import PlaybookGraph
from app.agentic.playbooks.schemas.dossier_descriptor_builder import (
    NodeStep,
    build_dossier_descriptor,
)
from app.agentic.playbooks.schemas.section_descriptor import DossierDescriptor
from app.agentic.playbooks.services import engine as workflow_engine
from app.agentic.playbooks.services.graph_validator import _topological_order
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
    FinalizePayload,
    NodeSubmitPayload,
)
from app.modules.credito.services import dossier as dossier_svc
from app.modules.credito.services.cadastral import (
    build_cadastral_card_projection,
)
from app.modules.credito.services.revenue import build_faturamento_payload
from app.modules.credito.services.social_contract import build_societario_payload

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
    progress = await dossier_svc.compute_progress_map(db, dossiers=rows)
    items: list[DossierListItem] = []
    for r in rows:
        base = DossierListItem.model_validate(r).model_dump()
        base.update(progress.get(r.id, {}))
        items.append(DossierListItem(**base))
    return items


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


@router.delete(
    "/dossies/{dossier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_dossie(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.ADMIN)),
) -> None:
    """Hard-delete a dossier (admin-only).

    Cascades to every `credit_dossier_*` child table (analyses, attachments,
    notes, links, etc.) and the bound `workflow_run` (which cascades to
    `workflow_node_run`). Operacao destrutiva — gate de Permission.ADMIN
    impede analyst comum de remover dossie alheio. Frontend so expoe a acao
    quando `user_permissions.credito === 'admin'`; backend valida sempre.
    """
    deleted = await dossier_svc.delete_dossier(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Dossie nao encontrado.")
    await db.commit()


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
                select(PlaybookRun).where(PlaybookRun.id == dossier.workflow_run_id)
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
                    select(PlaybookRunStep)
                    .where(PlaybookRunStep.run_id == run_row.id)
                    .order_by(PlaybookRunStep.started_at.asc().nulls_last())
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

    # Flags de cruzamento do dossie (com proveniencia estruturada). Sao a
    # unidade-produto — o cockpit as mostra no EvidencePanel + na view do
    # deterministic_check. Mais recentes primeiro; criticas no topo.
    from app.modules.credito.models.red_flag import CreditDossierRedFlag

    severity_rank = {"critical": 0, "important": 1, "informational": 2}
    flag_rows = (
        await db.execute(
            select(CreditDossierRedFlag).where(
                CreditDossierRedFlag.tenant_id == principal.tenant_id,
                CreditDossierRedFlag.dossier_id == dossier_id,
            )
        )
    ).scalars().all()
    red_flags = sorted(
        (
            {
                "id": str(f.id),
                "section": f.section,
                "severity": f.severity,
                "title": f.title,
                "description": f.description,
                "evidence": f.evidence,
                "check_type": f.check_type,
                "provenance": f.provenance,
                "decision_log_id": str(f.decision_log_id) if f.decision_log_id else None,
                "raised_by_agent": f.raised_by_agent,
                "analyst_resolution": f.analyst_resolution,
                "analyst_notes": f.analyst_notes,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in flag_rows
        ),
        key=lambda r: (
            severity_rank.get(r["severity"], 9),
            r["created_at"] or "",
        ),
    )

    return DossierStateResponse(
        dossier=DossierRead.model_validate(dossier),
        run=run,
        node_runs=node_runs_data,
        pending_node=pending_node,
        red_flags=red_flags,
    )


@router.get("/dossies/{dossier_id}/descriptor", response_model=DossierDescriptor)
async def get_dossie_descriptor(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> DossierDescriptor:
    """DossierDescriptor (Fase 1 / Etapa 4): estações + seções de agente
    derivadas SERVER-SIDE (decisão A1), portando o buildEstacoes do cockpit.

    ADITIVO: o cockpit ainda NÃO consome isto (segue no /state com a derivação
    client-side). O rewire pra consumir aqui — e matar o buildEstacoes/afinidade
    do frontend — é o passo LIVE. Ver docs/esteira-credito-interface-camadas.md §5.
    """
    dossier = await dossier_svc.get_dossier(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    if dossier is None:
        raise HTTPException(status_code=404, detail="Dossie nao encontrado.")
    code = dossier.code or str(dossier_id)
    if dossier.workflow_run_id is None:
        return DossierDescriptor(code=code, stations=[])

    run_row = (
        await db.execute(
            select(PlaybookRun).where(PlaybookRun.id == dossier.workflow_run_id)
        )
    ).scalar_one_or_none()
    if run_row is None:
        return DossierDescriptor(code=code, stations=[])

    definition = (
        await db.execute(
            select(PlaybookDefinition).where(PlaybookDefinition.id == run_row.definition_id)
        )
    ).scalar_one_or_none()
    if definition is None:
        return DossierDescriptor(code=code, stations=[])

    graph = PlaybookGraph.model_validate(definition.graph)
    ordered = _topological_order(graph)

    step_rows = (
        await db.execute(
            select(PlaybookRunStep).where(PlaybookRunStep.run_id == run_row.id)
        )
    ).scalars().all()
    by_node = {s.node_id: s for s in step_rows}

    node_steps: list[NodeStep] = []
    for spec in ordered:
        run_step = by_node.get(spec.id)
        if run_step is None:
            node_steps.append(
                NodeStep(
                    id=spec.id,
                    label=spec.label or spec.type,
                    node_type=spec.type,
                    state="pending",
                    config=spec.config,
                )
            )
            continue
        status_val = (
            run_step.status.value
            if hasattr(run_step.status, "value")
            else str(run_step.status)
        )
        node_steps.append(
            NodeStep(
                id=spec.id,
                label=spec.label or spec.type,
                node_type=spec.type,
                state=status_val,
                output=run_step.output_data or None,
                input=run_step.input_data or None,
                config=spec.config,
            )
        )

    return build_dossier_descriptor(code, node_steps)


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
            select(PlaybookRunStep).where(
                PlaybookRunStep.run_id == dossier.workflow_run_id,
                PlaybookRunStep.node_id == node_id,
                PlaybookRunStep.status == NodeRunStatus.WAITING_INPUT,
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

    # Remove the WAITING_INPUT row so the engine re-executes the node with the
    # submitted pending_input. If we left it as COMPLETED here, `_execute_run`
    # would treat the node as already settled and skip re-execution — the
    # `output` in context_data would never be populated with the submitted
    # values, breaking templates like `{{node.<id>.output.cnpj}}` in
    # downstream nodes (e.g. bureau_query.entity_ref).
    await db.delete(waiting)
    await db.flush()

    submitted = dict(payload.values)

    # ORDEM CRITICA: persistir identidade + grafo ANTES de resumir o run.
    # Nodes downstream (cadastral_enrichment, gates deterministicos) leem
    # dossier.target_cnpj e credit_dossier_company(role=TARGET) na MESMA sessao.
    # Se o absorb rodasse depois do resume_run (bug ate 2026-06-04), a
    # empresa-alvo ainda nao existiria quando o enrichment executasse no resume
    # -> falhava "dossie sem empresa-alvo". absorb usa `submitted` (payload
    # cru), nao depende do output que o resume_run grava.

    # If the human_input collected an identity field (cnpj/cpf/razao_social/
    # nome), populate dossier.target_* retroactively. Lets fluxos genericos
    # comecarem sem identidade e ganharem identidade ao longo da execucao —
    # importante pra UI mostrar "Analise · ACME LTDA" depois que coletou.
    await dossier_svc.absorb_identity_from_human_input(
        db,
        tenant_id=principal.tenant_id,
        dossier_id=dossier_id,
        submitted=submitted,
    )

    # If the human_input collected the entry societary graph (empresa-alvo,
    # data de fundacao, socios com %participacao, coligadas), persist it into
    # credit_dossier_company / credit_dossier_person. No-op caso o form nao
    # carregue campos de grafo. Insumo dos checks deterministicos (idade da
    # empresa, soma de participacoes) + do enrichment cadastral.
    await dossier_svc.absorb_graph_from_human_input(
        db,
        tenant_id=principal.tenant_id,
        dossier_id=dossier_id,
        submitted=submitted,
    )

    # Resume the workflow run with the submitted values — os nodes downstream
    # ja enxergam a identidade + grafo persistidos acima (mesma sessao).
    await workflow_engine.resume_run(
        db,
        run_id=dossier.workflow_run_id,
        pending_inputs={node_id: submitted},
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


@router.post("/dossies/{dossier_id}/finalize", response_model=DossierStateResponse)
async def finalize_dossie(
    dossier_id: UUID,
    payload: FinalizePayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DossierStateResponse:
    """Finaliza o dossie: cria o parecer (credit_dossier_opinion) e conclui o
    node de revisao (human_review), levando o run ao fim.

    O parecer rascunho ja vem editado pelo analista no checkpoint; o texto
    final vai em analyst_final/executive_summary, com recommendation escolhida
    (default 'conditional'). Idempotente por versao — cada finalize cria uma
    nova versao current do parecer.
    """
    dossier = await dossier_svc.get_dossier(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    if dossier is None:
        raise HTTPException(status_code=404, detail="Dossie nao encontrado.")
    if dossier.workflow_run_id is None:
        raise HTTPException(
            status_code=400, detail="Dossie nao tem workflow run associado."
        )

    waiting = (
        await db.execute(
            select(PlaybookRunStep).where(
                PlaybookRunStep.run_id == dossier.workflow_run_id,
                PlaybookRunStep.node_id == payload.node_id,
                PlaybookRunStep.status == NodeRunStatus.WAITING_INPUT,
            )
        )
    ).scalar_one_or_none()
    if waiting is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No '{payload.node_id}' nao esta aguardando revisao. "
                "Talvez ja tenha sido finalizado."
            ),
        )

    await dossier_svc.create_opinion(
        db,
        tenant_id=principal.tenant_id,
        dossier_id=dossier_id,
        executive_summary=payload.opinion.executive_summary,
        recommendation=payload.opinion.recommendation,
        strengths=payload.opinion.strengths,
        concerns=payload.opinion.concerns,
        conditions=payload.opinion.conditions,
        ai_draft=None,
        analyst_id=principal.user_id,
    )

    await db.delete(waiting)
    await db.flush()
    await workflow_engine.resume_run(
        db,
        run_id=dossier.workflow_run_id,
        pending_inputs={payload.node_id: {"approved": True}},
    )
    await dossier_svc.sync_status_from_workflow(db, dossier=dossier)
    await db.commit()
    return await get_dossie_state(
        dossier_id=dossier_id, principal=principal, db=db
    )


@router.post(
    "/dossies/{dossier_id}/nodes/{node_id}/rerun",
    response_model=DossierStateResponse,
)
async def rerun_node_endpoint(
    dossier_id: UUID,
    node_id: str,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> DossierStateResponse:
    """Reprocessa um node e tudo a jusante (apos o analista editar inputs ou
    re-anexar um documento). Remove os node_runs alvo + suas flags e re-executa.
    """
    dossier = await dossier_svc.get_dossier(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    if dossier is None:
        raise HTTPException(status_code=404, detail="Dossie nao encontrado.")
    try:
        await dossier_svc.rerun_node(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            node_id=node_id,
        )
    except dossier_svc.DossierServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await dossier_svc.sync_status_from_workflow(db, dossier=dossier)
    await db.commit()
    return await get_dossie_state(
        dossier_id=dossier_id, principal=principal, db=db
    )


@router.get("/dossies/{dossier_id}/faturamento/analytics")
async def faturamento_analytics(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> dict:
    """Série de faturamento homologada + analytics determinístico + atestação.

    Mesmo payload que a read-tool entrega ao agente — a tela do checkpoint
    mostra os MESMOS fatos que o `revenue_analyst` julgou (números da fonte
    determinística, não do agente).
    """
    return await build_faturamento_payload(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )


@router.get("/dossies/{dossier_id}/societario")
async def societario(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> dict:
    """Ficha do contrato social homologado + estrutura QSA + cruzamentos BDC.

    Mesmo payload que a read-tool entrega ao `social_contract_analyst` — a
    tela do checkpoint mostra os MESMOS fatos que o agente julgou (números e
    cruzamentos da fonte determinística, não do agente).
    """
    return await build_societario_payload(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )


@router.get("/dossies/{dossier_id}/cadastral")
async def dados_cadastrais(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> dict:
    """Card 'Dados cadastrais coletados' — DIRIGIDO PELO CONTRATO (Fase 2).

    Projeta o basic_data via o Contrato de Dados ativo: `campos` com rótulo
    pt-BR / categoria / ordem (só `on_screen`) + campos novos (🆕) fora do
    contrato. White-label (sem vendor). 404 quando o dossie não tem empresa-alvo.
    """
    view = await build_cadastral_card_projection(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    if view is None:
        raise HTTPException(
            status_code=404, detail="Empresa-alvo nao encontrada no dossie."
        )
    return view
