"""Module access guard: checks tenant subscription + user permission.

Usage in endpoints:

    from app.core.module_guard import require_module
    from app.core.enums import Module, Permission

    @router.get("/receita")
    async def receita(
        _: None = Depends(require_module(Module.BI, Permission.READ)),
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
from app.core.enums import Module, Permission
from app.core.tenant_middleware import RequestPrincipal, get_current_principal


def require_module(module: Module, permission: Permission) -> Callable:
    """Return a FastAPI dependency enforcing module subscription + user permission.

    - If the tenant does NOT have the module enabled -> HTTP 402 Payment Required.
    - If the user lacks sufficient permission -> HTTP 403 Forbidden.
    - Otherwise, returns None (guard passes).
    """

    async def _guard(
        principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> None:
        from app.shared.identity.subscription import TenantModuleSubscription
        from app.shared.identity.user_permission import UserModulePermission

        # 1. Check tenant subscription
        sub_stmt = select(TenantModuleSubscription).where(
            TenantModuleSubscription.tenant_id == principal.tenant_id,
            TenantModuleSubscription.module == module,
        )
        sub = (await db.execute(sub_stmt)).scalar_one_or_none()
        if sub is None or not sub.enabled:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"O modulo '{module.value}' nao esta habilitado para este tenant.",
            )

        # 2. Check user permission
        perm_stmt = select(UserModulePermission).where(
            UserModulePermission.user_id == principal.user_id,
            UserModulePermission.module == module,
        )
        perm = (await db.execute(perm_stmt)).scalar_one_or_none()
        current = perm.permission if perm else Permission.NONE
        if not current.satisfies(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Permissao insuficiente no modulo '{module.value}'. "
                    f"Necessario '{permission.value}', usuario tem '{current.value}'."
                ),
            )

    return _guard
