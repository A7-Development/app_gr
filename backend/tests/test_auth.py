"""End-to-end test: login + /auth/me."""

import pytest
from httpx import AsyncClient

from app.shared.identity.user import User


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, user_in_tenant_a: User) -> None:
    """Valid credentials return a JWT."""
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": user_in_tenant_a.email, "password": "test-password"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in_minutes"] > 0


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, user_in_tenant_a: User) -> None:
    """Wrong password returns 401."""
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": user_in_tenant_a.email, "password": "wrong"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_modules_and_permissions(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    """/auth/me returns user + tenant + all modules enabled + all permissions admin."""
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user_in_tenant_a.email, "password": "test-password"},
    )
    token = login.json()["access_token"]

    r = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == user_in_tenant_a.email
    assert str(body["tenant"]["id"]) == str(user_in_tenant_a.tenant_id)
    assert len(body["enabled_modules"]) == 8
    assert all(p == "admin" for p in body["user_permissions"].values())


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient) -> None:
    """/auth/me without Authorization returns 401."""
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_health_is_public(client: AsyncClient) -> None:
    """/health does not require authentication."""
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
