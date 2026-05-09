"""AI capability guard: checks tenant subscription + user permission for AI.

Parallel to `core/module_guard.py::require_module`, but for the transversal AI
capability (which lives outside the closed `Module` enum — see CLAUDE.md sec 19).

Usage:

    from app.core.ai_guard import require_ai
    from app.core.enums import AICapability

    @router.post("/api/v1/ai/chat")
    async def chat(
        _: None = Depends(require_ai(AICapability.READ)),
        ...
    ):
        ...
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import AICapability
from app.core.tenant_middleware import RequestPrincipal, get_current_principal


def require_ai(capability: AICapability) -> Callable:
    """Return a FastAPI dependency enforcing AI subscription + user permission.

    - If the tenant does NOT have AI enabled -> HTTP 402 Payment Required.
    - If the user lacks sufficient permission -> HTTP 403 Forbidden.
    - Otherwise, returns None (guard passes).
    """

    async def _guard(
        principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> None:
        from app.shared.ai.models.permission import UserAIPermission
        from app.shared.ai.models.subscription import TenantAISubscription

        # 1. Check tenant subscription
        sub_stmt = select(TenantAISubscription).where(
            TenantAISubscription.tenant_id == principal.tenant_id
        )
        sub = (await db.execute(sub_stmt)).scalar_one_or_none()
        if sub is None or not sub.enabled:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="A capacidade de IA nao esta habilitada para este tenant.",
            )

        # 2. Check user permission
        perm_stmt = select(UserAIPermission).where(
            UserAIPermission.user_id == principal.user_id
        )
        perm = (await db.execute(perm_stmt)).scalar_one_or_none()
        current = perm.permission if perm else AICapability.NONE
        if not current.satisfies(capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Permissao insuficiente em IA. "
                    f"Necessario '{capability.value}', usuario tem '{current.value}'."
                ),
            )

    return _guard
