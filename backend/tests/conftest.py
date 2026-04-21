"""Pytest fixtures — test client + isolated data setup.

Design: each fixture opens+commits+closes its own AsyncSession, so the app's
request handlers (which also open sessions via `get_db`) never share a
connection with a still-open fixture session. This avoids the classic
asyncpg 'another operation is in progress' error.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import AsyncSessionLocal, engine
from app.core.enums import Module, Permission
from app.core.security import hash_password
from app.main import app
from app.shared.identity.subscription import TenantModuleSubscription
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client against the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def tenant_a() -> Tenant:
    """Tenant A — full subscriptions on all 8 modules."""
    slug = f"test-a-{uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        t = Tenant(slug=slug, name=f"Test Tenant A {slug}", ativo=True)
        db.add(t)
        await db.flush()
        for m in Module:
            db.add(TenantModuleSubscription(tenant_id=t.id, module=m, enabled=True))
        await db.commit()
        await db.refresh(t)
    return t


@pytest.fixture
async def tenant_b() -> Tenant:
    """Tenant B — used for isolation tests."""
    slug = f"test-b-{uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        t = Tenant(slug=slug, name=f"Test Tenant B {slug}", ativo=True)
        db.add(t)
        await db.flush()
        for m in Module:
            db.add(TenantModuleSubscription(tenant_id=t.id, module=m, enabled=True))
        await db.commit()
        await db.refresh(t)
    return t


@pytest.fixture
async def user_in_tenant_a(tenant_a: Tenant) -> User:
    """User in tenant A with ADMIN on all 8 modules."""
    email = f"user-a-{uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as db:
        u = User(
            tenant_id=tenant_a.id,
            email=email,
            name="User A",
            password_hash=hash_password("test-password"),
            ativo=True,
        )
        db.add(u)
        await db.flush()
        for m in Module:
            db.add(UserModulePermission(user_id=u.id, module=m, permission=Permission.ADMIN))
        await db.commit()
        await db.refresh(u)
    return u


@pytest.fixture(scope="session", autouse=True)
async def _cleanup_engine():
    """Dispose async engine at session end to avoid 'event loop closed' warnings."""
    yield
    await engine.dispose()
