"""CRUD de coletores (/api/v1/integracoes/coletores) -- 403 + isolamento (§10).

Cobre o checklist do CLAUDE.md para endpoint/service novo:
- 403 para usuario sem permissao ADMIN no modulo integracoes;
- isolamento: tenant B nao lista/edita/revoga coletor de A (404, nao 403 —
  nao vazamos a existencia do recurso);
- token plaintext aparece SO no create/rotate; rotate invalida o antigo e
  reativa credencial revogada; revoke derruba o agente no gateway.
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

BASE = "/api/v1/integracoes/coletores"

WATCH_CONFIG = {
    "scan_interval_minutes": 10,
    "watches": [
        {"path": "C:/Bitfin/Retorno", "glob": "*.RET", "source_label": "cobranca_cnab"},
        {
            "path": "C:/Backup/Diario",
            "glob": "*.zip",
            "source_label": "movimento_diario",
            "container": "zip",
        },
    ],
}


async def _login(client: AsyncClient, email: str, password: str = "test-password") -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_user(tenant: Tenant, *, integracoes: Permission | None) -> User:
    """User com ADMIN em tudo, exceto o nivel dado em INTEGRACOES."""
    email = f"coletor-{uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as db:
        u = User(
            tenant_id=tenant.id,
            email=email,
            name="User Coletores",
            password_hash=hash_password("test-password"),
            ativo=True,
        )
        db.add(u)
        await db.flush()
        for m in Module:
            if m == Module.INTEGRACOES:
                if integracoes is not None:
                    db.add(
                        UserModulePermission(
                            user_id=u.id, module=m, permission=integracoes
                        )
                    )
                continue
            db.add(UserModulePermission(user_id=u.id, module=m, permission=Permission.ADMIN))
        await db.commit()
        await db.refresh(u)
    return u


async def _create_coletor(client: AsyncClient, token: str, name: str = "Servidor X") -> dict:
    r = await client.post(
        BASE,
        headers=_auth(token),
        json={"name": name, "watch_config": WATCH_CONFIG},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---- Guarda de modulo (403) ----------------------------------------------------


@pytest.mark.asyncio
async def test_user_sem_permissao_integracoes_recebe_403(
    client: AsyncClient, tenant_a: Tenant
) -> None:
    user = await _make_user(tenant_a, integracoes=None)
    token = await _login(client, user.email)
    r = await client.get(BASE, headers=_auth(token))
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_permissao_read_nao_basta_para_admin_endpoints(
    client: AsyncClient, tenant_a: Tenant
) -> None:
    user = await _make_user(tenant_a, integracoes=Permission.READ)
    token = await _login(client, user.email)
    assert (await client.get(BASE, headers=_auth(token))).status_code == 403
    r = await client.post(
        BASE, headers=_auth(token), json={"name": "X", "watch_config": WATCH_CONFIG}
    )
    assert r.status_code == 403


# ---- CRUD basico ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_devolve_token_uma_unica_vez(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    token = await _login(client, user_in_tenant_a.email)
    created = await _create_coletor(client, token, "Servidor Bitfin")
    assert created["token"].startswith("strata_agt_")
    assert created["watch_config"]["watches"][1]["container"] == "zip"

    listed = (await client.get(BASE, headers=_auth(token))).json()
    match = [c for c in listed if c["id"] == created["id"]]
    assert len(match) == 1
    assert "token" not in match[0], "token plaintext vazou no GET"
    assert match[0]["arquivos_total"] == 0


@pytest.mark.asyncio
async def test_watch_config_invalida_rejeitada(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    token = await _login(client, user_in_tenant_a.email)
    r = await client.post(
        BASE,
        headers=_auth(token),
        json={
            "name": "X",
            "watch_config": {
                "watches": [{"path": "C:/x", "source_label": "Label Invalido!"}]
            },
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_edita_watch_config(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    token = await _login(client, user_in_tenant_a.email)
    created = await _create_coletor(client, token)
    nova = {
        "scan_interval_minutes": 3,
        "watches": [{"path": "D:/Nova", "glob": "*.xml", "source_label": "cte"}],
    }
    r = await client.put(
        f"{BASE}/{created['id']}",
        headers=_auth(token),
        json={"name": "Renomeado", "watch_config": nova},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renomeado"
    assert body["watch_config"]["scan_interval_minutes"] == 3
    assert body["watch_config"]["watches"][0]["source_label"] == "cte"


# ---- Ciclo de vida do token ------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_derruba_agente_e_rotate_reativa(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    token = await _login(client, user_in_tenant_a.email)
    created = await _create_coletor(client, token)
    agent_token = created["token"]

    # Token recem-criado funciona no gateway.
    ping = await client.get(
        "/api/v1/filedrop/ping", headers={"Authorization": f"Bearer {agent_token}"}
    )
    assert ping.status_code == 200, ping.text

    # Revoke -> gateway passa a recusar.
    r = await client.post(f"{BASE}/{created['id']}/revoke", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["revoked_at"] is not None
    ping = await client.get(
        "/api/v1/filedrop/ping", headers={"Authorization": f"Bearer {agent_token}"}
    )
    assert ping.status_code == 401

    # Rotate -> token novo funciona, antigo continua morto, credencial reativa.
    r = await client.post(f"{BASE}/{created['id']}/rotate", headers=_auth(token))
    assert r.status_code == 200
    rotated = r.json()
    assert rotated["revoked_at"] is None
    assert rotated["token"] != agent_token
    assert (
        await client.get(
            "/api/v1/filedrop/ping",
            headers={"Authorization": f"Bearer {rotated['token']}"},
        )
    ).status_code == 200
    assert (
        await client.get(
            "/api/v1/filedrop/ping",
            headers={"Authorization": f"Bearer {agent_token}"},
        )
    ).status_code == 401


# ---- Isolamento multi-tenant (§10) ------------------------------------------------


@pytest.mark.asyncio
async def test_isolamento_tenant_b_nao_ve_nem_mexe_em_coletor_de_a(
    client: AsyncClient, user_in_tenant_a: User, tenant_b: Tenant
) -> None:
    token_a = await _login(client, user_in_tenant_a.email)
    created = await _create_coletor(client, token_a, "Coletor do A")

    user_b = await _make_user(tenant_b, integracoes=Permission.ADMIN)
    token_b = await _login(client, user_b.email)

    listed_b = (await client.get(BASE, headers=_auth(token_b))).json()
    assert all(c["id"] != created["id"] for c in listed_b), "coletor de A vazou pro B"

    # Update/rotate/revoke cross-tenant: 404 (sem vazar existencia).
    r = await client.put(
        f"{BASE}/{created['id']}", headers=_auth(token_b), json={"name": "hack"}
    )
    assert r.status_code == 404
    assert (
        await client.post(f"{BASE}/{created['id']}/rotate", headers=_auth(token_b))
    ).status_code == 404
    assert (
        await client.post(f"{BASE}/{created['id']}/revoke", headers=_auth(token_b))
    ).status_code == 404

    # E nada disso afetou o coletor de A.
    listed_a = (await client.get(BASE, headers=_auth(token_a))).json()
    match = [c for c in listed_a if c["id"] == created["id"]]
    assert match and match[0]["name"] == "Coletor do A"
    assert match[0]["revoked_at"] is None
