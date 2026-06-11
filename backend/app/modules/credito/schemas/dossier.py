"""Pydantic schemas for /credito/dossies endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import DossierStatus, OpinionRecommendation

# Next-action enum used by the listing to drive UI decisions:
#   "human_input"        — paused on a human_input node, waiting for the analyst
#   "agent_running"      — a specialist agent or bureau_query is executing now
#   "blocked"            — workflow is paused or blocked on an external dep
#   "ready_to_finalize"  — analysis complete, awaiting human confirmation
#   "finalized"          — workflow finished successfully
NextActionKind = Literal[
    "human_input",
    "agent_running",
    "blocked",
    "ready_to_finalize",
    "finalized",
]


class DossierCreate(BaseModel):
    """Input to create a new dossier ('Iniciar análise').

    Identidade da entidade analisada e OPCIONAL: o fluxo coletado pode
    pedir CNPJ/CPF/nome via human_input e o motor preenche retroativamente
    via `services.dossier.absorb_identity_from_human_input`. Fluxos sem
    identidade (simulacao, analise de produto) ficam sem.
    """

    model_config = ConfigDict(extra="forbid")

    workflow_definition_id: UUID
    target_cnpj: str | None = Field(None, max_length=20)
    target_name: str | None = Field(None, max_length=255)
    operation_type: str | None = Field(None, max_length=64)
    requested_amount: Decimal | None = None
    requested_term_days: int | None = Field(None, ge=1)
    notes: str | None = None


class DossierUpdate(BaseModel):
    """Input to update domain fields of an existing dossier."""

    model_config = ConfigDict(extra="forbid")

    target_name: str | None = Field(None, min_length=1, max_length=255)
    operation_type: str | None = None
    requested_amount: Decimal | None = None
    requested_term_days: int | None = Field(None, ge=1)
    notes: str | None = None


class DossierRead(BaseModel):
    """Detailed view of a dossier."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    code: str | None = None
    target_cnpj: str | None
    target_name: str | None
    operation_type: str | None
    requested_amount: Decimal | None
    requested_term_days: int | None
    status: DossierStatus
    workflow_definition_id: UUID
    workflow_run_id: UUID | None
    analyst_id: UUID | None
    finalized_at: datetime | None
    created_at: datetime
    updated_at: datetime
    notes: str | None


class DossierListItem(BaseModel):
    """Compact row for the dossier listing page.

    Carries enough state for the listing to render:
    - Empresa / CNPJ / Status / Operacao / Atualizado columns (existing)
    - Progresso (X/Y etapas) via `completed_steps` + `total_steps`
    - Proxima acao (badge) via `next_action_kind` + `next_action_label`
    - Deep-link para retomar do step ativo via `next_node_id`
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str | None = None
    target_cnpj: str | None
    target_name: str | None
    status: DossierStatus
    operation_type: str | None
    requested_amount: Decimal | None
    analyst_id: UUID | None
    workflow_definition_id: UUID
    workflow_run_id: UUID | None
    created_at: datetime
    updated_at: datetime
    completed_steps: int = 0
    total_steps: int = 0
    next_action_kind: NextActionKind = "blocked"
    next_action_label: str = ""
    next_node_id: str | None = None


class OpinionInput(BaseModel):
    """Parecer rascunho editavel pelo analista no checkpoint (Fatia 1).

    Recomendacao default 'conditional' (rascunho neutro — decisao 2026-06-01);
    o analista edita por cima antes de finalizar.
    """

    model_config = ConfigDict(extra="forbid")

    executive_summary: str = Field(..., min_length=1)
    recommendation: OpinionRecommendation = OpinionRecommendation.CONDITIONAL
    strengths: list[str] = []
    concerns: list[str] = []
    conditions: list[str] = []


class FinalizePayload(BaseModel):
    """Finaliza o dossie: cria o parecer e conclui o node de revisao."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    opinion: OpinionInput


class NodeSubmitPayload(BaseModel):
    """Payload submitted by the analyst when resuming a paused human node.

    The shape of `values` is determined by the node's `config.fields`.
    The engine writes the values to the node's pending_input slot in the
    run context and re-executes the node.
    """

    model_config = ConfigDict(extra="forbid")

    values: dict[str, object]


class DossierStateResponse(BaseModel):
    """Combined view: dossier + workflow run + node runs.

    Used by the dossier detail page to render real-time state of the
    workflow execution (which nodes completed, which is paused waiting
    for input, what the agent outputs were, etc).
    """

    model_config = ConfigDict(from_attributes=True)

    dossier: DossierRead
    run: dict | None  # serialized PlaybookRunRead (avoid forward ref headaches)
    node_runs: list[dict]
    pending_node: dict | None  # the WAITING_INPUT node, if any (with form descriptor)
    # Flags de cruzamento (credit_dossier_red_flag) com proveniencia
    # estruturada — a unidade-produto da esteira. O cockpit renderiza no
    # track de inconsistencias do EvidencePanel + na view do deterministic_check.
    red_flags: list[dict] = []
