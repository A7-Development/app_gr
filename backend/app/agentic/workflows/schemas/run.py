"""Pydantic schemas for WorkflowRun + WorkflowRunStep (API output).

Inputs (start a run, pause, resume) live in `services/engine.py` as plain
function arguments — the API layer wraps them.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import NodeRunStatus, WorkflowRunStatus


class WorkflowRunStepRead(BaseModel):
    """Output: one node execution within a run."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    node_id: str
    node_type: str
    status: NodeRunStatus
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    tokens_input: int
    tokens_output: int
    cost_brl: Decimal
    error_detail: str | None
    attempt_number: int


class WorkflowRunRead(BaseModel):
    """Output: a workflow run with its node runs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    definition_id: UUID
    trigger_type: str
    trigger_data: dict[str, Any]
    status: WorkflowRunStatus
    started_at: datetime | None
    completed_at: datetime | None
    paused_at: datetime | None
    context_data: dict[str, Any]
    error_detail: str | None
    initiated_by: UUID | None
    created_at: datetime
    node_runs: list[WorkflowRunStepRead] = []
