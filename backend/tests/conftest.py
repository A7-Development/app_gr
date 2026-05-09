"""Pytest fixtures — test client + isolated data setup.

Design: each fixture opens+commits+closes its own AsyncSession, so the app's
request handlers (which also open sessions via `get_db`) never share a
connection with a still-open fixture session. This avoids the classic
asyncpg 'another operation is in progress' error.
"""

from collections.abc import AsyncGenerator
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, engine
from app.core.enums import Module, Permission
from app.core.security import hash_password
from app.main import app
from app.shared.identity.subscription import TenantModuleSubscription
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission


def pytest_configure(config: pytest.Config) -> None:
    """Aborta o pytest se DATABASE_URL nao apontar para um banco de testes.

    Why: as fixtures abaixo escrevem direto via `AsyncSessionLocal`, que
    usa o engine global da app. Sem este guard, rodar pytest com `.env`
    apontando para producao polui o DB com tenants/users/warehouse de
    teste (incidente 2026-04-27: 1267 tenants `test-a-*`/`test-b-*` em
    `gr_db@192.168.100.27`, 16k+ linhas em 16 tabelas).

    How to apply: o nome do database (parte depois do ultimo `/`) tem que
    conter literalmente o token `test` (`gr_db_test`, `test_gr`, etc).
    Para rodar contra um banco real propositalmente (debug raro), comente
    esta funcao — nao ha escape hatch via env var de proposito.
    """
    db_url = get_settings().DATABASE_URL
    db_name = urlparse(db_url.replace("+asyncpg", "")).path.lstrip("/")
    if "test" not in db_name.lower():
        pytest.exit(
            f"\n[conftest guard] DATABASE_URL aponta para '{db_name}', que nao "
            f"parece banco de teste (precisa conter 'test' no nome).\n"
            f"Configure DATABASE_URL para um banco isolado (ex.: gr_db_test) "
            f"antes de rodar pytest. Ver tests/conftest.py::pytest_configure.",
            returncode=2,
        )


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


# Tabelas globais (sem tenant_id) populadas via migration de seed.
# Preservar do TRUNCATE — sao parte do schema, nao dado de teste.
_PRESERVED_TABLES = frozenset(
    {
        "alembic_version",  # controle Alembic
        "source_catalog",  # seed via migration b1d9a2f7c4e8 (CLAUDE.md §13)
    }
)


@pytest.fixture(scope="session", autouse=True)
async def _truncate_and_dispose():
    """TRUNCATE all tables at session start; dispose engine at session end.

    Defense-in-depth para o gr_db_test: garante banco vazio mesmo apos
    runs anteriores que crasharam (SIGKILL, segfault, ctrl-C) e deixaram
    fixtures sem teardown. Rodando em transacao pra atomicidade.
    Tabelas globais (alembic_version, source_catalog) sao preservadas —
    sao schema/seed, nao dado de teste.
    """
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        )
        tables = [r[0] for r in result if r[0] not in _PRESERVED_TABLES]
        if tables:
            await conn.execute(
                text(
                    f"TRUNCATE TABLE {', '.join(tables)} "
                    f"RESTART IDENTITY CASCADE"
                )
            )
    yield
    await engine.dispose()
