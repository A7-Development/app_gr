"""System-maintainer guard: gates global admin endpoints to the maintainer tenant.

The system maintainer is the tenant marked with `tenants.is_system_maintainer = true`.
A partial unique index in the schema enforces at most one such tenant.

Endpoints that manage global resources (AI provider credentials, AI tier per
tenant, prompt library) require BOTH:
1. The principal's tenant is the system maintainer (this guard), AND
2. The principal has `Module.ADMIN` + `Permission.ADMIN` (regular `require_module`).

Compose at the route definition:

    @router.post("/api/v1/admin/ai/providers")
    async def create_provider(
        _: None = Depends(require_system_maintainer),
        __: None = Depends(require_module(Module.ADMIN, Permission.ADMIN)),
        ...
    ):
        ...
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tenant_middleware import RequestPrincipal, get_current_principal


async def require_system_maintainer(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Allow only members of the maintainer tenant to proceed.

    Returns 403 if the principal's tenant is not flagged as system maintainer.
    """
    from app.shared.identity.tenant import Tenant

    tenant = await db.get(Tenant, principal.tenant_id)
    if tenant is None or not tenant.is_system_maintainer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao tenant mantenedor do sistema.",
        )
