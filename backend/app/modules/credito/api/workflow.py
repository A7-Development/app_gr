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

from app.agentic.playbooks.models.definition import (
    PlaybookDefinition,
    PlaybookDefinitionActive,
)
from app.agentic.playbooks.schemas.definition import (
    PlaybookActivatePayload,
    PlaybookDefinitionCreate,
    PlaybookDefinitionRead,
    PlaybookDefinitionUpdate,
    PlaybookGraph,
)
from app.agentic.playbooks.services.dry_run import dry_run_workflow
from app.agentic.playbooks.services.engine import list_node_types_for_editor
from app.agentic.playbooks.services.graph_validator import (
    ValidationResult,
    validate_graph,
)
from app.core.database import get_db
from app.core.enums import Module, Permission, PlaybookStatus
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.data_providers.models.dataset import DataProviderDataset

router = APIRouter()


@router.get("/workflows", response_model=list[PlaybookDefinitionRead])
async def list_workflows(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> list[PlaybookDefinitionRead]:
    """List Strata templates + tenant's own workflows (category=credit)."""
    rows = (
        await db.execute(
            select(PlaybookDefinition)
            .where(
                PlaybookDefinition.category == "credit",
                or_(
                    PlaybookDefinition.tenant_id.is_(None),  # Strata templates
                    PlaybookDefinition.tenant_id == principal.tenant_id,
                ),
                PlaybookDefinition.archived_at.is_(None),
            )
            .order_by(PlaybookDefinition.created_at.desc())
        )
    ).scalars().all()
    return [PlaybookDefinitionRead.model_validate(r) for r in rows]


@router.get("/workflows/{workflow_id}", response_model=PlaybookDefinitionRead)
async def get_workflow(
    workflow_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> PlaybookDefinitionRead:
    row = (
        await db.execute(
            select(PlaybookDefinition).where(
                PlaybookDefinition.id == workflow_id,
                or_(
                    PlaybookDefinition.tenant_id.is_(None),
                    PlaybookDefinition.tenant_id == principal.tenant_id,
                ),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow nao encontrado.")
    return PlaybookDefinitionRead.model_validate(row)


@router.post(
    "/workflows",
    response_model=PlaybookDefinitionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow(
    payload: PlaybookDefinitionCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.ADMIN)),
) -> PlaybookDefinitionRead:
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
                select(PlaybookDefinition).where(
                    PlaybookDefinition.id == payload.clone_from,
                    or_(
                        PlaybookDefinition.tenant_id.is_(None),
                        PlaybookDefinition.tenant_id == principal.tenant_id,
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

    row = PlaybookDefinition(
        tenant_id=principal.tenant_id,
        name=payload.name,
        version=1,
        description=payload.description,
        category=category,
        graph=graph_dict,
        status=PlaybookStatus.DRAFT,
        created_by=principal.user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return PlaybookDefinitionRead.model_validate(row)


@router.patch("/workflows/{workflow_id}", response_model=PlaybookDefinitionRead)
async def update_workflow(
    workflow_id: UUID,
    payload: PlaybookDefinitionUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.ADMIN)),
) -> PlaybookDefinitionRead:
    """Create a new VERSION of an existing workflow (immutable history)."""
    base = (
        await db.execute(
            select(PlaybookDefinition).where(
                PlaybookDefinition.id == workflow_id,
                PlaybookDefinition.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if base is None:
        raise HTTPException(status_code=404, detail="Workflow nao encontrado ou nao editavel.")

    new_row = PlaybookDefinition(
        tenant_id=base.tenant_id,
        name=base.name,
        version=base.version + 1,
        description=payload.description if payload.description is not None else base.description,
        category=base.category,
        graph=payload.graph.model_dump(),
        status=PlaybookStatus.DRAFT,
        created_by=principal.user_id,
    )
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)
    return PlaybookDefinitionRead.model_validate(new_row)


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

    Regra (2026-06-12, fase de construcao): qualquer versao do TENANT pode
    ser excluida — inclusive ACTIVE/ARCHIVED — desde que NADA a referencie.
    A auditoria e preservada por REFERENCIA, nao por status: versao com
    dossie/execucao apontando pra ela e bloqueada (exclua os dossies antes);
    versao orfa e lixo de iteracao e pode sair.

    Templates Strata (tenant_id NULL): excluiveis APENAS pelo tenant
    mantenedor do sistema (master user) — mesmas travas de referencia,
    checadas SEM filtro de tenant (template global pode estar em uso por
    qualquer tenant).
    """
    from sqlalchemy import func

    from app.agentic.playbooks.models.run import PlaybookRun
    from app.modules.credito.models.dossier import CreditDossier
    from app.shared.identity.tenant import Tenant

    row = (
        await db.execute(
            select(PlaybookDefinition).where(PlaybookDefinition.id == workflow_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow nao encontrado.")

    if row.tenant_id is None:
        tenant = await db.get(Tenant, principal.tenant_id)
        if tenant is None or not tenant.is_system_maintainer:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Template Strata so pode ser excluido pelo tenant "
                    "mantenedor do sistema."
                ),
            )
    elif row.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=404,
            detail="Workflow nao encontrado ou nao pertence ao tenant.",
        )

    n_dossiers = await db.scalar(
        select(func.count())
        .select_from(CreditDossier)
        .where(CreditDossier.workflow_definition_id == workflow_id)
    )
    if n_dossiers:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{n_dossiers} dossie(s) usam esta versao do playbook — "
                "exclua-os primeiro (a trilha de auditoria deles referencia "
                "este grafo)."
            ),
        )
    n_runs = await db.scalar(
        select(func.count())
        .select_from(PlaybookRun)
        .where(PlaybookRun.definition_id == workflow_id)
    )
    if n_runs:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{n_runs} execucao(oes) registradas usam esta versao — "
                "ha trilha de auditoria apontando pra ela."
            ),
        )

    # Ponteiro de versao ativa: se aponta pra ESTA versao e existem OUTRAS
    # versoes vivas do mesmo nome, peca pra ativar outra (senao o nome fica
    # sem versao ativa por acidente). Se e a ultima versao, o ponteiro sai
    # junto — exclusao limpa do playbook inteiro.
    # Template global pode ter VARIOS ponteiros (um por tenant) — trata lista.
    actives = list(
        (
            await db.execute(
                select(PlaybookDefinitionActive).where(
                    PlaybookDefinitionActive.active_definition_id == workflow_id
                )
            )
        )
        .scalars()
        .all()
    )
    if actives:
        n_outras = await db.scalar(
            select(func.count())
            .select_from(PlaybookDefinition)
            .where(
                PlaybookDefinition.name == row.name,
                # Irmas no MESMO escopo da versao (tenant ou global/Strata).
                PlaybookDefinition.tenant_id.is_(None)
                if row.tenant_id is None
                else PlaybookDefinition.tenant_id == row.tenant_id,
                PlaybookDefinition.id != workflow_id,
                PlaybookDefinition.archived_at.is_(None),
            )
        )
        if n_outras:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Esta e a versao ATIVA e existem outras versoes deste "
                    "playbook — ative outra antes de excluir esta."
                ),
            )
        for a in actives:
            await db.delete(a)
        await db.flush()

    await db.delete(row)
    await db.commit()


@router.put(
    "/workflows/{name}/active",
    response_model=PlaybookDefinitionRead,
)
async def activate_workflow(
    name: str,
    payload: PlaybookActivatePayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.ADMIN)),
) -> PlaybookDefinitionRead:
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
            select(PlaybookDefinition).where(
                PlaybookDefinition.id == payload.definition_id,
                PlaybookDefinition.name == name,
                or_(
                    PlaybookDefinition.tenant_id.is_(None),
                    PlaybookDefinition.tenant_id == principal.tenant_id,
                ),
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=404,
            detail="Versao nao encontrada para esse nome de workflow.",
        )
    if target.status == PlaybookStatus.ARCHIVED:
        raise HTTPException(
            status_code=400,
            detail="Nao e possivel ativar uma versao ARCHIVED.",
        )

    # Gate de validação semântica (Fase 2). DRAFT pode ser inválido — você
    # constrói incrementalmente. Mas ATIVAR um fluxo que vai rodar em prod
    # com erro estrutural é bloqueado: 422 com lista de erros pra UI mostrar.
    graph_obj = PlaybookGraph.model_validate(target.graph)
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
            select(PlaybookDefinitionActive).where(
                PlaybookDefinitionActive.name == name,
                PlaybookDefinitionActive.tenant_id == pointer_tenant_id,
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
            PlaybookDefinitionActive(
                id=uuid4(),
                name=name,
                tenant_id=pointer_tenant_id,
                active_definition_id=payload.definition_id,
                activated_by=principal.user_id,
            )
        )

    # Promote target to ACTIVE if it was DRAFT.
    if target.status == PlaybookStatus.DRAFT:
        target.status = PlaybookStatus.ACTIVE

    # (Optional) other versions of the same name from this tenant could be
    # archived here. For now we don't auto-archive — user can archive
    # explicitly. Multiple ACTIVE rows existing for different versions of
    # the same name is fine because only ONE is pointed-to by *_active.

    await db.commit()
    await db.refresh(target)
    return PlaybookDefinitionRead.model_validate(target)


@router.get(
    "/workflows/{name}/active",
    response_model=PlaybookDefinitionRead,
)
async def get_active_workflow(
    name: str,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> PlaybookDefinitionRead:
    """Return the active workflow definition for `name` for this tenant.

    Resolution order:
    1. Tenant-specific pointer in `workflow_definition_active`
    2. Strata starter pointer (`tenant_id IS NULL`) as fallback
    """
    pointer = (
        await db.execute(
            select(PlaybookDefinitionActive).where(
                PlaybookDefinitionActive.name == name,
                PlaybookDefinitionActive.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()

    if pointer is None:
        pointer = (
            await db.execute(
                select(PlaybookDefinitionActive).where(
                    PlaybookDefinitionActive.name == name,
                    PlaybookDefinitionActive.tenant_id.is_(None),
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
            select(PlaybookDefinition).where(
                PlaybookDefinition.id == pointer.active_definition_id
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=500,
            detail="Pointer ativo aponta para definition inexistente — DB inconsistente.",
        )

    return PlaybookDefinitionRead.model_validate(target)


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

    Source of truth: `app.agentic.engine.catalog.CATALOG` (+ CREDIT_BUILDER_PALETTE
    para a curadoria da paleta do builder). `palette` é null quando o agente NÃO
    entra na paleta de crédito (ex.: auditores de Cota Sub) — o frontend deriva a
    paleta 100% daqui, sem lista própria.
    """
    from app.agentic.engine.catalog import CATALOG, CREDIT_BUILDER_PALETTE

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
            "palette": (
                {"label": pal.label, "icon": pal.icon, "blurb": pal.blurb}
                if (pal := CREDIT_BUILDER_PALETTE.get(spec.name)) is not None
                else None
            ),
        }
        for spec in CATALOG.values()
    ]


class DataProductRead(BaseModel):
    """Dataset externo exposto ao TENANT — WHITE-LABEL.

    SO campos neutros. `provider_slug`, `provider_api`, `provider_dataset_code`,
    `provider_query_name`, preco/markup NUNCA aparecem aqui (decisao 2026-06-04).
    O node `cadastral_enrichment` referencia o `public_code`; o vendor resolve
    em runtime dentro de integracoes.
    """

    public_code: str
    display_name: str
    categoria_ui: str | None = None
    description: str | None = None


def _serialize_data_product(ds: DataProviderDataset) -> DataProductRead:
    """Serializa um dataset para o contrato tenant-facing (sem vendor).

    Funcao pura (testavel): garante que nenhum campo de vendor escapa. UI cai
    em `public_code` quando `display_name_pt_br` nao foi curado.
    """
    return DataProductRead(
        public_code=ds.public_code or "",
        display_name=ds.display_name_pt_br or (ds.public_code or ""),
        categoria_ui=ds.categoria_ui,
        description=ds.description_pt_br,
    )


@router.get("/data-products", response_model=list[DataProductRead])
async def list_data_products(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> list[DataProductRead]:
    """Lista datasets externos habilitados para a paleta do builder (white-label).

    Data-driven: a paleta de "produtos de dado" vem do catalogo
    (`provedor_dados_dataset` com `enabled_for_sale=true` e `public_code`
    definido), NAO de lista hardcoded. Retorna apenas codigo neutro +
    rotulo/categoria/descricao — o vendor nunca vaza pro tenant.
    """
    # So datasets que o CadastralEnrichmentNode consegue executar de fato:
    # fetch_cadastral_pj (integracoes) hoje so atende BigDataCorp. Datasets de
    # outros provedores (ex.: JUCESP/Infosimples) entram no builder por
    # RECEITA do node `official_document_fetch`, nao como card de
    # enriquecimento — sem este filtro a paleta exibia cards que falhavam na
    # primeira execucao. Generalizar = follow-up `data_query` (2026-06-11).
    from app.shared.data_providers.enums import DataProviderSlug
    from app.shared.data_providers.models.provider import DataProvider

    rows = (
        await db.execute(
            select(DataProviderDataset)
            .join(DataProvider, DataProvider.id == DataProviderDataset.provider_id)
            .where(DataProvider.slug == DataProviderSlug.BIGDATACORP)
            .where(DataProviderDataset.enabled_for_sale.is_(True))
            .where(DataProviderDataset.public_code.isnot(None))
            .order_by(DataProviderDataset.categoria_ui, DataProviderDataset.public_code)
        )
    ).scalars().all()
    return [_serialize_data_product(r) for r in rows]


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
    graph: Annotated[PlaybookGraph, Body(embed=False)],
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
            select(PlaybookDefinition).where(
                PlaybookDefinition.id == workflow_id,
                or_(
                    PlaybookDefinition.tenant_id.is_(None),
                    PlaybookDefinition.tenant_id == principal.tenant_id,
                ),
            )
        )
    ).scalar_one_or_none()
    if base is None:
        raise HTTPException(
            status_code=404, detail="Workflow nao encontrado ou nao acessivel."
        )
    graph = PlaybookGraph.model_validate(base.graph)
    result = dry_run_workflow(graph, trigger_data=payload.trigger_data)
    return {
        "final_status": result.final_status,
        "error": result.error,
        "steps": [asdict(s) for s in result.steps],
    }


# ─── Existing endpoint extensions ─────────────────────────────────────────
# (Activation is gated by validation: cannot activate a graph with errors.)
