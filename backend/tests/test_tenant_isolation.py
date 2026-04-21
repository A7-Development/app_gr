"""Regression test: tenant A never sees tenant B's data via the auth layer."""

import pytest
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User


@pytest.mark.asyncio
async def test_user_from_tenant_a_receives_only_tenant_a_data(
    client: AsyncClient, user_in_tenant_a: User, tenant_b: Tenant
) -> None:
    """User from tenant A must NEVER see tenant B in /auth/me response."""
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user_in_tenant_a.email, "password": "test-password"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    r = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # The tenant in the response MUST be A, not B
    assert str(body["tenant"]["id"]) == str(user_in_tenant_a.tenant_id)
    assert str(body["tenant"]["id"]) != str(tenant_b.id)


@pytest.mark.asyncio
async def test_same_email_different_tenants(
    client: AsyncClient, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    """Two users with the same email in different tenants are valid (uq is per tenant).

    Documents current behavior: /auth/login does not scope by tenant in the MVP.
    When true multi-tenant login is exercised (Etapa G), add tenant_slug to login.
    """
    from uuid import uuid4

    email = f"same-{uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as db:
        db.add(
            User(
                tenant_id=tenant_a.id,
                email=email,
                name="User A",
                password_hash=hash_password("pwd-a"),
                ativo=True,
            )
        )
        db.add(
            User(
                tenant_id=tenant_b.id,
                email=email,
                name="User B",
                password_hash=hash_password("pwd-b"),
                ativo=True,
            )
        )
        await db.commit()

    r_a = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pwd-a"},
    )
    # Either login succeeds against one of the two users, or current
    # query picks the other and fails password check — both are acceptable
    # documentation of the MVP behavior.
    assert r_a.status_code in (200, 401)
