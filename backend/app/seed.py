"""Seed script: creates initial tenant + user + module subscriptions + permissions.

Usage (after `alembic upgrade head`):

    python -m app.seed

Idempotent: skipping entries that already exist.
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Module, Permission
from app.core.security import hash_password
from app.shared.identity.subscription import TenantModuleSubscription
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission

# ---- Seed data ----
SEED_TENANT_SLUG = "a7-credit"
SEED_TENANT_NAME = "A7 Credit"
SEED_USER_EMAIL = "ricardo@a7credit.com.br"
SEED_USER_NAME = "Ricardo Pimenta"
SEED_USER_PASSWORD = "A7Credit2026!"  # pragma: allowlist secret


async def _seed() -> None:
    async with AsyncSessionLocal() as db:
        # Tenant
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == SEED_TENANT_SLUG))
        ).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(slug=SEED_TENANT_SLUG, name=SEED_TENANT_NAME, ativo=True)
            db.add(tenant)
            await db.flush()
            print(f"[seed] Tenant created: {tenant.slug}")
        else:
            print(f"[seed] Tenant exists: {tenant.slug}")

        # User
        user = (
            await db.execute(
                select(User).where(User.tenant_id == tenant.id, User.email == SEED_USER_EMAIL)
            )
        ).scalar_one_or_none()
        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=SEED_USER_EMAIL,
                name=SEED_USER_NAME,
                password_hash=hash_password(SEED_USER_PASSWORD),
                ativo=True,
            )
            db.add(user)
            await db.flush()
            print(f"[seed] User created: {user.email}")
        else:
            print(f"[seed] User exists: {user.email}")

        # Enable all 8 modules for the tenant
        for module in Module:
            sub = (
                await db.execute(
                    select(TenantModuleSubscription).where(
                        TenantModuleSubscription.tenant_id == tenant.id,
                        TenantModuleSubscription.module == module,
                    )
                )
            ).scalar_one_or_none()
            if sub is None:
                db.add(
                    TenantModuleSubscription(
                        tenant_id=tenant.id,
                        module=module,
                        enabled=True,
                        enabled_since=datetime.now(UTC),
                    )
                )
                print(f"[seed] Subscription created: {module.value}")

        # Grant user ADMIN on all 8 modules
        for module in Module:
            perm = (
                await db.execute(
                    select(UserModulePermission).where(
                        UserModulePermission.user_id == user.id,
                        UserModulePermission.module == module,
                    )
                )
            ).scalar_one_or_none()
            if perm is None:
                db.add(
                    UserModulePermission(
                        user_id=user.id,
                        module=module,
                        permission=Permission.ADMIN,
                    )
                )
                print(f"[seed] Permission created: {module.value}=admin")

        await db.commit()
        print("[seed] Done.")
        print(f"[seed] Login credentials: {SEED_USER_EMAIL} / {SEED_USER_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(_seed())
