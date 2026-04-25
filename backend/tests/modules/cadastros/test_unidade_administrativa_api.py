"""Tests E2E do CRUD de UnidadeAdministrativa.

Cobre:
- CRUD basico (create, list, get, update, delete)
- Isolamento de tenant (tenant A nao ve UAs do tenant B)
- Validacoes (CNPJ, nome unique, etc)
- RBAC (READ vs WRITE)
- 404 / 409 corretos
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

API_BASE = "/api/v1/cadastros/unidades-administrativas"


async def _login(client: AsyncClient, email: str, password: str = "test-password") -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- Fixtures locais (READ-only e WRITE-less users do tenant B p/ isolamento) ---


@pytest.fixture
async def user_b_admin(tenant_b: Tenant) -> User:
    """User no tenant B com ADMIN em todos os modulos. Usado em testes de isolamento."""
    email = f"user-b-{uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as db:
        u = User(
            tenant_id=tenant_b.id,
            email=email,
            name="User B",
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


@pytest.fixture
async def user_a_read_only(tenant_a: Tenant) -> User:
    """User no tenant A com READ em CADASTROS (sem WRITE). Usado em RBAC negativo."""
    email = f"user-a-ro-{uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as db:
        u = User(
            tenant_id=tenant_a.id,
            email=email,
            name="User A RO",
            password_hash=hash_password("test-password"),
            ativo=True,
        )
        db.add(u)
        await db.flush()
        # Concede READ em todos os modulos. RBAC fica: pode listar, nao pode criar.
        for m in Module:
            db.add(UserModulePermission(user_id=u.id, module=m, permission=Permission.READ))
        await db.commit()
        await db.refresh(u)
    return u


# ---- CRUD basico ---------------------------------------------------------


@pytest.mark.asyncio
async def test_create_then_list_then_get_ua(client: AsyncClient, user_in_tenant_a: User):
    token = await _login(client, user_in_tenant_a.email)

    # Create
    r = await client.post(
        API_BASE,
        headers=_auth(token),
        json={
            "nome": "TESTUA FIDC",
            "cnpj": "11222333000181",
            "tipo": "fidc",
        },
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["nome"] == "TESTUA FIDC"
    assert created["cnpj"] == "11222333000181"
    assert created["tipo"] == "fidc"
    assert created["ativa"] is True
    assert created["bitfin_ua_id"] is None
    assert "id" in created
    ua_id = created["id"]

    # List
    r = await client.get(API_BASE, headers=_auth(token))
    assert r.status_code == 200
    nomes = {u["nome"] for u in r.json()}
    assert "TESTUA FIDC" in nomes

    # Get
    r = await client.get(f"{API_BASE}/{ua_id}", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["id"] == ua_id


@pytest.mark.asyncio
async def test_update_partial_preserva_campos_omitidos(
    client: AsyncClient, user_in_tenant_a: User
):
    token = await _login(client, user_in_tenant_a.email)
    create = await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA PATCH", "tipo": "factoring", "cnpj": "22333444000172"},
    )
    ua_id = create.json()["id"]

    # PATCH so o nome — cnpj e tipo devem sobreviver.
    r = await client.patch(
        f"{API_BASE}/{ua_id}",
        headers=_auth(token),
        json={"nome": "UA PATCH RENAMED"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nome"] == "UA PATCH RENAMED"
    assert body["cnpj"] == "22333444000172"
    assert body["tipo"] == "factoring"


@pytest.mark.asyncio
async def test_delete_ua(client: AsyncClient, user_in_tenant_a: User):
    token = await _login(client, user_in_tenant_a.email)
    create = await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA DELETE", "tipo": "consultoria"},
    )
    ua_id = create.json()["id"]

    r = await client.delete(f"{API_BASE}/{ua_id}", headers=_auth(token))
    assert r.status_code == 204

    # Idempotencia: 2a chamada da 404
    r = await client.delete(f"{API_BASE}/{ua_id}", headers=_auth(token))
    assert r.status_code == 404


# ---- Validacoes / conflitos ---------------------------------------------


@pytest.mark.asyncio
async def test_cnpj_aceita_com_pontuacao_e_normaliza(
    client: AsyncClient, user_in_tenant_a: User
):
    """CNPJ '11.222.333/0001-81' deve normalizar pra '11222333000181'."""
    token = await _login(client, user_in_tenant_a.email)
    r = await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA NORM", "tipo": "fidc", "cnpj": "11.222.333/0001-81"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["cnpj"] == "11222333000181"


@pytest.mark.asyncio
async def test_cnpj_invalido_retorna_422(
    client: AsyncClient, user_in_tenant_a: User
):
    token = await _login(client, user_in_tenant_a.email)
    r = await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA INVALID", "tipo": "fidc", "cnpj": "12345"},
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_nome_duplicado_retorna_409(
    client: AsyncClient, user_in_tenant_a: User
):
    token = await _login(client, user_in_tenant_a.email)
    payload = {"nome": "UA DUP NOME", "tipo": "gestora"}
    r1 = await client.post(API_BASE, headers=_auth(token), json=payload)
    assert r1.status_code == 201
    r2 = await client.post(API_BASE, headers=_auth(token), json=payload)
    assert r2.status_code == 409, r2.text
    assert "nome" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cnpj_duplicado_retorna_409(
    client: AsyncClient, user_in_tenant_a: User
):
    token = await _login(client, user_in_tenant_a.email)
    cnpj = "33444555000163"
    r1 = await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA CNPJ A", "tipo": "fidc", "cnpj": cnpj},
    )
    assert r1.status_code == 201
    r2 = await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA CNPJ B", "tipo": "fidc", "cnpj": cnpj},
    )
    assert r2.status_code == 409, r2.text
    assert "cnpj" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cnpj_nullable_permite_multiplas_uas_sem_cnpj(
    client: AsyncClient, user_in_tenant_a: User
):
    """Duas UAs sem CNPJ no mesmo tenant — partial unique index ignora NULL."""
    token = await _login(client, user_in_tenant_a.email)
    r1 = await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA SEM CNPJ 1", "tipo": "consultoria"},
    )
    r2 = await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA SEM CNPJ 2", "tipo": "consultoria"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201


# ---- Isolamento de tenant -----------------------------------------------


@pytest.mark.asyncio
async def test_tenant_a_nao_ve_ua_do_tenant_b(
    client: AsyncClient, user_in_tenant_a: User, user_b_admin: User
):
    """User do tenant B cria UA — user do tenant A nao deve ver no list nem em get."""
    token_a = await _login(client, user_in_tenant_a.email)
    token_b = await _login(client, user_b_admin.email)

    # B cria UA
    rb = await client.post(
        API_BASE,
        headers=_auth(token_b),
        json={"nome": "UA EXCLUSIVA TENANT B", "tipo": "fidc"},
    )
    assert rb.status_code == 201, rb.text
    ua_b_id = rb.json()["id"]

    # A lista — nao deve ver UA de B
    r_list = await client.get(API_BASE, headers=_auth(token_a))
    assert r_list.status_code == 200
    nomes_a = {u["nome"] for u in r_list.json()}
    assert "UA EXCLUSIVA TENANT B" not in nomes_a

    # A tenta GET por ID — 404
    r_get = await client.get(f"{API_BASE}/{ua_b_id}", headers=_auth(token_a))
    assert r_get.status_code == 404


# ---- RBAC ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_read_only_nao_consegue_criar(
    client: AsyncClient, user_a_read_only: User
):
    token = await _login(client, user_a_read_only.email)
    r = await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA RO BLOCK", "tipo": "fidc"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_user_read_only_consegue_listar(
    client: AsyncClient, user_a_read_only: User
):
    token = await _login(client, user_a_read_only.email)
    r = await client.get(API_BASE, headers=_auth(token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_endpoint_sem_token_retorna_401(client: AsyncClient):
    r = await client.get(API_BASE)
    assert r.status_code == 401


# ---- Filtros de listagem ------------------------------------------------


@pytest.mark.asyncio
async def test_list_filtra_por_ativa(client: AsyncClient, user_in_tenant_a: User):
    token = await _login(client, user_in_tenant_a.email)
    # cria 1 ativa + 1 inativa
    await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA ATIVA F", "tipo": "fidc", "ativa": True},
    )
    inativa = await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA INATIVA F", "tipo": "fidc", "ativa": False},
    )
    assert inativa.status_code == 201

    r_so_ativas = await client.get(
        f"{API_BASE}?ativa=true", headers=_auth(token)
    )
    nomes = {u["nome"] for u in r_so_ativas.json()}
    assert "UA ATIVA F" in nomes
    assert "UA INATIVA F" not in nomes


@pytest.mark.asyncio
async def test_list_filtra_por_tipo(client: AsyncClient, user_in_tenant_a: User):
    token = await _login(client, user_in_tenant_a.email)
    await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA TIPO FIDC", "tipo": "fidc"},
    )
    await client.post(
        API_BASE,
        headers=_auth(token),
        json={"nome": "UA TIPO FACT", "tipo": "factoring"},
    )

    r = await client.get(f"{API_BASE}?tipo=factoring", headers=_auth(token))
    assert r.status_code == 200
    nomes = {u["nome"] for u in r.json()}
    assert "UA TIPO FACT" in nomes
    assert "UA TIPO FIDC" not in nomes
