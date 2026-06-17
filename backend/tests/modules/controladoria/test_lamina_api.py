"""Tests E2E -- Controladoria · Lamina mensal do FIDC.

Cobre o contrato/escopo do endpoint:
- RBAC: sem permissao em CONTROLADORIA -> 403.
- Escopo de tenant: tenant sem FIDC (sem UA/MEC) -> 404 (nao vaza dado).
- Wiring dos dois endpoints (/lamina e /lamina/competencias).

O caminho de dados (payload com os numeros do REALINVEST: PL, razao de
garantia, aging que reconcilia, concentracao) foi validado rodando o service
`compute_lamina` direto contra o gr_db real. Um smoke seedado com silver
sintetica (MEC + estoque + rentabilidade + saldo) e follow-up natural deste
arquivo quando houver fixtures de warehouse.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import Module, Permission
from app.core.security import hash_password
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission

LAMINA = "/api/v1/controladoria/lamina"
COMPETENCIAS = "/api/v1/controladoria/lamina/competencias"


async def _login(client: AsyncClient, email: str, password: str = "test-password") -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def user_sem_controladoria(tenant_a: Tenant) -> User:
    """User no tenant A com READ em todos os modulos EXCETO controladoria."""
    email = f"user-a-noctrl-{uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as db:
        u = User(
            tenant_id=tenant_a.id,
            email=email,
            name="User A sem controladoria",
            password_hash=hash_password("test-password"),
            ativo=True,
        )
        db.add(u)
        await db.flush()
        for m in Module:
            if m == Module.CONTROLADORIA:
                continue  # sem permissao -> guard nega (403)
            db.add(
                UserModulePermission(user_id=u.id, module=m, permission=Permission.READ)
            )
        await db.commit()
        await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_lamina_forbidden_sem_permissao(
    client: AsyncClient, user_sem_controladoria: User
) -> None:
    token = await _login(client, user_sem_controladoria.email)
    r1 = await client.get(LAMINA, headers=_auth(token))
    assert r1.status_code == 403, r1.text
    r2 = await client.get(COMPETENCIAS, headers=_auth(token))
    assert r2.status_code == 403, r2.text


@pytest.mark.asyncio
async def test_lamina_404_sem_fundo(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    """Tenant com permissao mas sem FIDC cadastrado -> 404 (escopo, sem vazar)."""
    token = await _login(client, user_in_tenant_a.email)
    r1 = await client.get(LAMINA, headers=_auth(token))
    assert r1.status_code == 404, r1.text
    r2 = await client.get(COMPETENCIAS, headers=_auth(token))
    assert r2.status_code == 404, r2.text


@pytest.mark.asyncio
async def test_lamina_requires_auth(client: AsyncClient) -> None:
    r = await client.get(LAMINA)
    assert r.status_code in (401, 403), r.text
