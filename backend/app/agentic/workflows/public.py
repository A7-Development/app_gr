"""Public contract of the workflow engine.

This is the only file other modules should import from `app.agentic.workflows`.
Internals (engine.py, node implementations, model internals) are not contract
and may change without notice.

Consumers (modules/credito, modules/risco when wired):
- Use `WorkflowGraph` schemas to validate definitions
- Use `WorkflowRunRead` for API responses showing run state
- Call `start_run()` / `pause_run()` / `resume_run()` from services
- Read `NodeStatus` / `RunStatus` enums from `app.core.enums`
"""

from app.agentic.workflows.models.definition import (
    WorkflowDefinition,
    WorkflowDefinitionActive,
)
from app.agentic.workflows.models.run import WorkflowRun, WorkflowRunStep
from app.agentic.workflows.schemas.definition import (
    EdgeSpec,
    NodeSpec,
    WorkflowDefinitionCreate,
    WorkflowDefinitionRead,
    WorkflowDefinitionUpdate,
    WorkflowGraph,
)
from app.agentic.workflows.schemas.run import (
    WorkflowRunRead,
    WorkflowRunStepRead,
)

__all__ = [
    "EdgeSpec",
    "NodeSpec",
    "WorkflowDefinition",
    "WorkflowDefinitionActive",
    "WorkflowDefinitionCreate",
    "WorkflowDefinitionRead",
    "WorkflowDefinitionUpdate",
    "WorkflowGraph",
    "WorkflowRun",
    "WorkflowRunRead",
    "WorkflowRunStep",
    "WorkflowRunStepRead",
]
