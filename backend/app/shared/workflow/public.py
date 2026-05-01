"""Public contract of the workflow engine.

This is the only file other modules should import from `app.shared.workflow`.
Internals (engine.py, node implementations, model internals) are not contract
and may change without notice.

Consumers (modules/credito, modules/risco when wired):
- Use `WorkflowGraph` schemas to validate definitions
- Use `WorkflowRunRead` for API responses showing run state
- Call `start_run()` / `pause_run()` / `resume_run()` from services
- Read `NodeStatus` / `RunStatus` enums from `app.core.enums`
"""

from app.shared.workflow.models.definition import (
    WorkflowDefinition,
    WorkflowDefinitionActive,
)
from app.shared.workflow.models.run import WorkflowNodeRun, WorkflowRun
from app.shared.workflow.schemas.definition import (
    EdgeSpec,
    NodeSpec,
    WorkflowDefinitionCreate,
    WorkflowDefinitionRead,
    WorkflowDefinitionUpdate,
    WorkflowGraph,
)
from app.shared.workflow.schemas.run import (
    WorkflowNodeRunRead,
    WorkflowRunRead,
)

__all__ = [
    # Models (for FK references and joins inside other modules)
    "WorkflowDefinition",
    "WorkflowDefinitionActive",
    "WorkflowRun",
    "WorkflowNodeRun",
    # Schemas
    "NodeSpec",
    "EdgeSpec",
    "WorkflowGraph",
    "WorkflowDefinitionCreate",
    "WorkflowDefinitionUpdate",
    "WorkflowDefinitionRead",
    "WorkflowRunRead",
    "WorkflowNodeRunRead",
]
