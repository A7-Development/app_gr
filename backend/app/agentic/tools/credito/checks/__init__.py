"""Deterministic credit checks package.

Importing this package registers all checks (side-effect imports below), so
the `deterministic_check` node can resolve them from `CHECK_REGISTRY`.
"""

# Side-effect imports: each module calls @register_check at import time.
from app.agentic.tools.credito.checks import (  # noqa: F401
    cnae_permitido,
    company_founding_age,
    company_status_active,
    ownership_sum,
)
from app.agentic.tools.credito.checks._base import (
    CHECK_REGISTRY,
    CheckContext,
    CheckMeta,
    CheckResult,
    FlagSpec,
    get_check,
    list_checks,
    register_check,
)

__all__ = [
    "CHECK_REGISTRY",
    "CheckContext",
    "CheckMeta",
    "CheckResult",
    "FlagSpec",
    "get_check",
    "list_checks",
    "register_check",
]
