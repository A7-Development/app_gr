"""Pydantic schemas for /credito/dossies endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import DossierStatus


class DossierCreate(BaseModel):
    """Input to create a new dossier (wizard step 'Confirma')."""

    model_config = ConfigDict(extra="forbid")

    target_cnpj: str = Field(..., min_length=14, max_length=20)
    target_name: str = Field(..., min_length=1, max_length=255)
    workflow_definition_id: UUID
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
    target_cnpj: str
    target_name: str
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
    """Compact row for the dossier listing page."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_cnpj: str
    target_name: str
    status: DossierStatus
    operation_type: str | None
    requested_amount: Decimal | None
    analyst_id: UUID | None
    workflow_definition_id: UUID
    workflow_run_id: UUID | None
    created_at: datetime
    updated_at: datetime


class NodeSubmitPayload(BaseModel):
    """Payload submitted by the analyst when resuming a paused human node.

    The shape of `values` is determined by the node's `config.fields`.
    The engine writes the values to the node's pending_input slot in the
    run context and re-executes the node.
    """

    model_config = ConfigDict(extra="forbid")

    values: dict[str, "object"]


class DossierStateResponse(BaseModel):
    """Combined view: dossier + workflow run + node runs.

    Used by the dossier detail page to render real-time state of the
    workflow execution (which nodes completed, which is paused waiting
    for input, what the agent outputs were, etc).
    """

    model_config = ConfigDict(from_attributes=True)

    dossier: DossierRead
    run: dict | None  # serialized WorkflowRunRead (avoid forward ref headaches)
    node_runs: list[dict]
    pending_node: dict | None  # the WAITING_INPUT node, if any (with form descriptor)
