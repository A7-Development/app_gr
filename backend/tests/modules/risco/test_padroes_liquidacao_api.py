"""Tests do perfil DETERMINISTICO de liquidacoes (/risco/padroes-liquidacao).

Cobre: agregacao por cedente a partir de deteccao_score.features + regra_dura
(matriz de sinais + mix de canal + alerta), KPIs, RBAC (403 sem permissao) e
isolamento §10 (tenant B nao ve liquidacao de A).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import Module, Permission
from app.core.security import hash_password
from app.modules.risco.models import DeteccaoModelo, DeteccaoScore
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission
from app.warehouse.liquidacao import Liquidacao
from tests.modules.risco.test_curadoria_liquidacoes_api import (  # noqa: F401
    _auth,
    _login,
    liquidacoes_tenant_a,
    modelo_catalogo,
    user_b_admin,
)

API = "/api/v1/risco/padroes-liquidacao"


async def _seed_scores(
    tenant_id, modelo_id, liq1: Liquidacao, liq2: Liquidacao
) -> None:
    """liq1 = banco na praca + regra dura (conta/cidade); liq2 = baixa manual."""
    async with AsyncSessionLocal() as db:
        db.add(
            DeteccaoScore(
                tenant_id=tenant_id,
                modelo_id=modelo_id,
                liquidacao_id=liq1.id,
                score=None,
                regra_dura=True,
                regra_dura_motivo=(
                    "sacado de outra cidade pagou na agencia do cedente "
                    "(banco 237 ag 03368, Campinas/SP)"
                ),
                features={
                    "match_agencia_conta_cedente": 1.0,
                    "cidade_pgto_eq_cedente": 1.0,
                    "cidade_pgto_neq_sacado": 1.0,
                },
            )
        )
        db.add(
            DeteccaoScore(
                tenant_id=tenant_id,
                modelo_id=modelo_id,
                liquidacao_id=liq2.id,
                score=0.1,
                regra_dura=False,
                features={
                    "canal_baixa_manual": 1.0,
                    "contrato_aberto": 1.0,
                },
            )
        )
        await db.commit()


@pytest.fixture
async def user_a_sem_risco(tenant_a: Tenant) -> User:
    """User de tenant A com permissao em tudo MENOS risco -> 403 no endpoint."""
    email = f"user-a-norisco-{uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as db:
        u = User(
            tenant_id=tenant_a.id,
            email=email,
            name="User A sem risco",
            password_hash=hash_password("test-password"),
            ativo=True,
        )
        db.add(u)
        await db.flush()
        for m in Module:
            if m == Module.RISCO:
                continue
            db.add(UserModulePermission(user_id=u.id, module=m, permission=Permission.READ))
        await db.commit()
        await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_perfil_agrega_sinais_canal_e_alerta(
    client: AsyncClient,
    user_in_tenant_a: User,
    tenant_a: Tenant,
    modelo_catalogo: DeteccaoModelo,  # noqa: F811
    liquidacoes_tenant_a: list[Liquidacao],  # noqa: F811
):
    liq1, liq2 = liquidacoes_tenant_a
    await _seed_scores(tenant_a.id, modelo_catalogo.id, liq1, liq2)

    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(API, headers=_auth(token))
    assert r.status_code == 200, r.text
    data = r.json()

    kpis = data["kpis"]
    assert kpis["n_liq_total"] == 2
    assert kpis["valor_total"] == 2000.0
    assert kpis["n_cedentes"] == 1
    assert kpis["n_alerta_total"] == 1
    assert kpis["pct_banco_praca"] == 50.0
    assert kpis["pct_baixa_manual"] == 50.0
    assert kpis["pct_fora_praca"] == 50.0

    assert len(data["cedentes"]) == 1
    c = data["cedentes"][0]
    assert c["cedente_documento"] == "12345678000199"
    assert c["n_liq"] == 2
    assert c["n_alerta"] == 1
    assert c["n_alerta_conta"] == 1
    assert c["n_alerta_anel"] == 0
    # ocorrencias de sinal
    assert c["sinais"]["match_conta"] == 1
    assert c["sinais"]["match_cidade"] == 1
    assert c["sinais"]["fora_praca"] == 1
    assert c["sinais"]["contrato_aberto"] == 1
    assert c["sinais"]["anel_cedentes"] == 0
    # mix de canal: 1 banco na praca (liq1) + 1 baixa manual (liq2)
    assert c["canal"]["banco_praca"] == 1
    assert c["canal"]["baixa_manual"] == 1
    assert c["canal"]["cooperativa"] == 0
    # janela 30d default: sem janela anterior com dados -> cedente novo, sem Delta
    assert c["cedente_novo"] is True
    assert c["delta_alerta"] is None


@pytest.mark.asyncio
async def test_janela_tudo_inclui_e_sem_delta(
    client: AsyncClient,
    user_in_tenant_a: User,
    tenant_a: Tenant,
    modelo_catalogo: DeteccaoModelo,  # noqa: F811
    liquidacoes_tenant_a: list[Liquidacao],  # noqa: F811
):
    liq1, liq2 = liquidacoes_tenant_a
    await _seed_scores(tenant_a.id, modelo_catalogo.id, liq1, liq2)

    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(f"{API}?janela=tudo", headers=_auth(token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["janela"] == "tudo"
    assert data["inicio"] is None
    assert data["kpis"]["n_liq_total"] == 2
    # "tudo" nao tem janela anterior -> nenhum Delta
    assert data["kpis"]["n_alerta_anterior"] is None
    assert data["cedentes"][0]["delta_alerta"] is None


@pytest.mark.asyncio
async def test_403_sem_permissao_risco(
    client: AsyncClient,
    user_a_sem_risco: User,
):
    token = await _login(client, user_a_sem_risco.email)
    r = await client.get(API, headers=_auth(token))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_isolamento_tenant_b_nao_ve(
    client: AsyncClient,
    tenant_a: Tenant,
    user_b_admin: User,  # noqa: F811
    modelo_catalogo: DeteccaoModelo,  # noqa: F811
    liquidacoes_tenant_a: list[Liquidacao],  # noqa: F811
):
    liq1, liq2 = liquidacoes_tenant_a
    await _seed_scores(tenant_a.id, modelo_catalogo.id, liq1, liq2)

    token_b = await _login(client, user_b_admin.email)
    r = await client.get(API, headers=_auth(token_b))
    assert r.status_code == 200
    data = r.json()
    assert data["kpis"]["n_liq_total"] == 0
    assert data["cedentes"] == []


@pytest.mark.asyncio
async def test_sem_token_401(client: AsyncClient):
    r = await client.get(API)
    assert r.status_code == 401
