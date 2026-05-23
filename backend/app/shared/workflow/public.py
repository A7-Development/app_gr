"""Public contract of the workflow engine.

This is the only file other modules should import from `app.shared.workflow`.
Internals (engine.py, node implementations, model internals) are not contract
and may change without notice.

Consumers (modules/credito, modules/risco when wired):
- Use `PlaybookGraph` schemas to validate definitions
- Use `PlaybookRunRead` for API responses showing run state
- Call `start_run()` / `pause_run()` / `resume_run()` from services
- Read `NodeStatus` / `RunStatus` enums from `app.core.enums`
"""

from app.shared.workflow.models.definition import (
    PlaybookDefinition,
    PlaybookDefinitionActive,
)
from app.shared.workflow.models.run import PlaybookRun, PlaybookRunStep
from app.shared.workflow.schemas.definition import (
    EdgeSpec,
    NodeSpec,
    PlaybookDefinitionCreate,
    PlaybookDefinitionRead,
    PlaybookDefinitionUpdate,
    PlaybookGraph,
)
from app.shared.workflow.schemas.run import (
    PlaybookRunRead,
    PlaybookRunStepRead,
)

__all__ = [
    "EdgeSpec",
    "NodeSpec",
    "PlaybookDefinition",
    "PlaybookDefinitionActive",
    "PlaybookDefinitionCreate",
    "PlaybookDefinitionRead",
    "PlaybookDefinitionUpdate",
    "PlaybookGraph",
    "PlaybookRun",
    "PlaybookRunRead",
    "PlaybookRunStep",
    "PlaybookRunStepRead",
]
