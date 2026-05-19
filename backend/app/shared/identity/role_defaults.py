"""Role-to-permission materialization.

`tenant_role` is sugar above the granular `user_module_permission` matrix.
Assigning or changing a role (re)populates the matrix via
`apply_role_defaults` so guards (`require_module`) keep being the single
source of truth — roles never replace them.

Matrix conventions:

    Owner  -> ADMIN in every module the tenant has enabled.
    Member -> WRITE in transactional modules, READ in analytical ones,
              NONE in Integracoes (sensitive credentials) and Admin.
    Viewer -> READ in every module except Integracoes and Admin (NONE).

Modules the tenant has NOT enabled receive no row (the guard already
returns HTTP 402 for those — populating perms there would be misleading).

Tenant invariant: a tenant must always have >=1 active Owner. Helpers in
this module check the invariant when removing/demoting an Owner.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Module, Permission, TenantRole
from app.shared.identity.subscription import TenantModuleSubscription
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission

# ---------------------------------------------------------------------------
# Role -> per-module permission table.
# ---------------------------------------------------------------------------
# Keep this canonical here so future modules added to the `Module` enum
# force an update to this map (no silent NONE on a new module).

_ROLE_MATRIX: dict[TenantRole, dict[Module, Permission]] = {
    TenantRole.OWNER: {
        Module.BI:             Permission.ADMIN,
        Module.CADASTROS:      Permission.ADMIN,
        Module.OPERACOES:      Permission.ADMIN,
        Module.CREDITO:        Permission.ADMIN,
        Module.CONTROLADORIA: Permission.ADMIN,
        Module.RISCO:          Permission.ADMIN,
        Module.INTEGRACOES:   Permission.ADMIN,
        Module.LABORATORIO:    Permission.ADMIN,
        Module.ADMIN:          Permission.ADMIN,
    },
    TenantRole.MEMBER: {
        Module.BI:             Permission.READ,
        Module.CADASTROS:      Permission.WRITE,
        Module.OPERACOES:      Permission.WRITE,
        Module.CREDITO:        Permission.WRITE,
        Module.CONTROLADORIA: Permission.READ,
        Module.RISCO:          Permission.READ,
        Module.INTEGRACOES:   Permission.NONE,
        Module.LABORATORIO:    Permission.READ,
        Module.ADMIN:          Permission.NONE,
    },
    TenantRole.VIEWER: {
        Module.BI:             Permission.READ,
        Module.CADASTROS:      Permission.READ,
        Module.OPERACOES:      Permission.READ,
        Module.CREDITO:        Permission.READ,
        Module.CONTROLADORIA: Permission.READ,
        Module.RISCO:          Permission.READ,
        Module.INTEGRACOES:   Permission.NONE,
        Module.LABORATORIO:    Permission.READ,
        Module.ADMIN:          Permission.NONE,
    },
}


def role_defaults_for(role: TenantRole) -> dict[Module, Permission]:
    """Return the default permission map for a given role.

    Caller can use it to render UIs ("herdado do role") or to compute
    overrides without hitting the DB.
    """
    return dict(_ROLE_MATRIX[role])


async def apply_role_defaults(
    db: AsyncSession,
    *,
    user: User,
    overwrite: bool = True,
) -> dict[Module, Permission]:
    """(Re)populate `user_module_permission` for `user` from its tenant_role.

    Only modules with active subscription on the user's tenant receive a row;
    others are left untouched (the guard already returns 402 for those).

    When `overwrite=True` (default), existing rows are reset to the role
    default. Set `overwrite=False` to preserve manual overrides — useful when
    the tenant enables a new module and you want to grant the role default to
    everyone without clobbering existing perms in other modules.

    Returns the map of (module, permission) actually applied.
    """
    # 1. Which modules does the tenant have enabled?
    sub_stmt = select(TenantModuleSubscription).where(
        TenantModuleSubscription.tenant_id == user.tenant_id,
        TenantModuleSubscription.enabled.is_(True),
    )
    subs = (await db.execute(sub_stmt)).scalars().all()
    enabled_modules = {s.module for s in subs}

    # 2. Resolve the role defaults intersected with enabled modules.
    matrix = _ROLE_MATRIX[user.tenant_role]
    target: dict[Module, Permission] = {
        m: matrix[m] for m in enabled_modules if m in matrix
    }

    if not target:
        return {}

    # 3. Upsert each row. Postgres ON CONFLICT lets us idempotently apply.
    for module, permission in target.items():
        stmt = pg_insert(UserModulePermission).values(
            user_id=user.id,
            module=module,
            permission=permission,
        )
        if overwrite:
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "module"],
                set_={"permission": permission},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["user_id", "module"]
            )
        await db.execute(stmt)

    return target


async def count_active_owners(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    excluding_user_id: UUID | None = None,
) -> int:
    """Count Owners that are ativo=True in a tenant.

    Use this before:
    - changing a user's role from OWNER to something else
    - deactivating (ativo=false) a user that is OWNER
    - revoking access of an Owner

    If `excluding_user_id` is given, that user is excluded from the count —
    useful to check "if I take this guy out, are there still other Owners?".
    """
    stmt = select(User).where(
        User.tenant_id == tenant_id,
        User.tenant_role == TenantRole.OWNER,
        User.ativo.is_(True),
    )
    if excluding_user_id is not None:
        stmt = stmt.where(User.id != excluding_user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return len(rows)


class LastOwnerError(Exception):
    """Raised when an operation would leave the tenant with zero active Owners."""


async def assert_not_last_owner(
    db: AsyncSession,
    *,
    user: User,
) -> None:
    """Guard: raises LastOwnerError if `user` is the only active Owner of its tenant.

    Call this before role demotion, deactivation, or hard delete of an Owner.
    """
    if user.tenant_role != TenantRole.OWNER:
        return
    if not user.ativo:
        return
    others = await count_active_owners(
        db, tenant_id=user.tenant_id, excluding_user_id=user.id
    )
    if others == 0:
        raise LastOwnerError(
            "Este usuario e o unico Owner ativo do tenant. "
            "Promova outro usuario a Owner antes de desativar ou rebaixar este."
        )
