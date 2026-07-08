"""Tests E2E da curadoria de liquidacoes + espinha de deteccao (modulo risco).

Cobre:
- Listagem paginada server-side traz TODAS as liquidacoes (nao so alertas),
  com total exposto (nada cortado silenciosamente)
- Tag e append-only: re-tag cria registro novo e a vigente e a mais recente
- Catalogo de modelos + treino sem rotulos suficientes = 422
- RBAC: READ nao cria tag (403); WRITE nao treina/ativa (403)
- Isolamento (§10): tenant B nao ve liquidacao de A; tag cross-tenant = 404
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import Module, Permission
from app.core.security import hash_password
from app.modules.risco.models import DeteccaoModelo, TipoModeloDeteccao
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission
from app.warehouse.liquidacao import Liquidacao
from app.warehouse.operacao import Operacao
from app.warehouse.titulo import Titulo

API_BASE = "/api/v1/risco/curadoria-liquidacoes"
API_MODELOS = "/api/v1/risco/deteccao/modelos"


async def _login(client: AsyncClient, email: str, password: str = "test-password") -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _operacao(tenant_id, operacao_id: int, modalidade: str = "FAT-DM") -> Operacao:
    now = datetime.now(UTC)
    return Operacao(
        tenant_id=tenant_id,
        operacao_id=operacao_id,
        data_de_cadastro=now,
        efetivada=True,
        quantidade_de_titulos=1,
        origem=1,
        modalidade=modalidade,
        coobrigacao=True,
        conta_operacional_id=1,
        unidade_administrativa_id=1,
        cedente_nome="Cedente Teste Ltda",
        cedente_documento="12345678000199",
        source_type="erp:bitfin",
        source_id=f"operacao:{operacao_id}",
        ingested_by_version="test",
    )


def _titulo(tenant_id, titulo_id: int, operacao_id: int, *, status: int = 0) -> Titulo:
    now = datetime.now(UTC)
    return Titulo(
        tenant_id=tenant_id,
        titulo_id=titulo_id,
        sigla="DM",
        numero=f"DOC-{titulo_id}",
        data_de_emissao=now,
        data_de_vencimento=now,
        data_de_vencimento_efetiva=now,
        data_de_cadastro=now,
        data_da_situacao=now,
        data_do_status=now,
        valor=1000,
        situacao=1,
        status=status,
        sacado_id=555,
        conta_operacional_id=1,
        unidade_administrativa_id=1,
        operacao_id=operacao_id,
        source_type="erp:bitfin",
        source_id=f"titulo:{titulo_id}",
        ingested_by_version="test",
    )


def _liquidacao(
    tenant_id, titulo_id: int, operacao_id: int, *, canal: str = "bancaria",
    evidencia: str | None = None,
) -> Liquidacao:
    now = datetime.now(UTC)
    return Liquidacao(
        tenant_id=tenant_id,
        titulo_id=titulo_id,
        operacao_id=operacao_id,
        canal=canal,
        evidencia=evidencia,
        data_evento=now,
        valor_titulo=1000,
        situacao_titulo=1,
        source_type="erp:bitfin",
        source_id=f"test:{canal}:{titulo_id}",
        ingested_by_version="test",
        trust_level="high",
    )


@pytest.fixture
async def modelo_catalogo() -> DeteccaoModelo:
    """Catalogo global — get-or-create (TRUNCATE do conftest e por sessao,
    nao por teste; o seed da migration pode ou nao estar presente)."""
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        m = (
            await db.execute(
                select(DeteccaoModelo).where(DeteccaoModelo.nome == "liquidacao_boleto")
            )
        ).scalar_one_or_none()
        if m is None:
            m = DeteccaoModelo(
                nome="liquidacao_boleto",
                alvo="liquidacao anomala",
                tipo=TipoModeloDeteccao.SUPERVISIONADO,
                modulo="risco",
                unidade="wh_liquidacao",
            )
            db.add(m)
            await db.commit()
            await db.refresh(m)
    return m


@pytest.fixture
async def liquidacoes_tenant_a(tenant_a: Tenant) -> list[Liquidacao]:
    async with AsyncSessionLocal() as db:
        db.add(_operacao(tenant_a.id, 100))
        db.add(_titulo(tenant_a.id, 1001, 100))
        db.add(_titulo(tenant_a.id, 1002, 100, status=3))  # candidato lastro
        liq1 = _liquidacao(tenant_a.id, 1001, 100)
        liq2 = _liquidacao(
            tenant_a.id, 1002, 100, canal="baixa_manual", evidencia="baixa_confirmada"
        )
        db.add_all([liq1, liq2])
        await db.commit()
        await db.refresh(liq1)
        await db.refresh(liq2)
    return [liq1, liq2]


@pytest.fixture
async def user_a_read_only(tenant_a: Tenant) -> User:
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
        for m in Module:
            db.add(UserModulePermission(user_id=u.id, module=m, permission=Permission.READ))
        await db.commit()
        await db.refresh(u)
    return u


@pytest.fixture
async def user_b_admin(tenant_b: Tenant) -> User:
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


# ---- Listagem --------------------------------------------------------------


@pytest.mark.asyncio
async def test_listagem_traz_todas_com_total(
    client: AsyncClient,
    user_in_tenant_a: User,
    modelo_catalogo: DeteccaoModelo,
    liquidacoes_tenant_a: list[Liquidacao],
):
    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(API_BASE, headers=_auth(token))
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["total"] == 2
    assert len(page["rows"]) == 2
    por_titulo = {row["titulo_id"]: row for row in page["rows"]}
    # Evento sem score aparece mesmo assim (curadoria ve TUDO).
    assert por_titulo[1001]["score"] is None
    assert por_titulo[1002]["evidencia"] == "baixa_confirmada"
    # Cross-signal de lastro e FLAG, nunca tag.
    assert por_titulo[1002]["candidato_lastro"] is True
    assert por_titulo[1002]["tag_vigente"] is None
    # "Qual foi o bad": sinais legiveis derivados dos campos declarados.
    assert "baixa_confirmada" in por_titulo[1002]["sinais"]
    assert "lastro_inconsistente" in por_titulo[1002]["sinais"]
    assert por_titulo[1001]["sinais"] == []
    assert por_titulo[1001]["situacao_titulo"] == 1


@pytest.mark.asyncio
async def test_filtros_sacado_e_situacao(
    client: AsyncClient,
    user_in_tenant_a: User,
    modelo_catalogo: DeteccaoModelo,
    liquidacoes_tenant_a: list[Liquidacao],
):
    token = await _login(client, user_in_tenant_a.email)
    # Situacao do titulo: fixtures gravam situacao_titulo=1 (liq normal).
    r = await client.get(f"{API_BASE}?situacao_titulo=1", headers=_auth(token))
    assert r.json()["total"] == 2
    r = await client.get(f"{API_BASE}?situacao_titulo=3", headers=_auth(token))
    assert r.json()["total"] == 0
    # Sacado: fixtures nao tem boleto_vigente -> busca por sacado zera.
    r = await client.get(f"{API_BASE}?sacado=inexistente", headers=_auth(token))
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_filtro_sugeridos(
    client: AsyncClient,
    user_in_tenant_a: User,
    modelo_catalogo: DeteccaoModelo,
    liquidacoes_tenant_a: list[Liquidacao],
):
    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(f"{API_BASE}?sugeridos=true", headers=_auth(token))
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == 1
    assert page["rows"][0]["titulo_id"] == 1002


# ---- Tags (append-only) ----------------------------------------------------


@pytest.mark.asyncio
async def test_tag_append_only_e_vigente(
    client: AsyncClient,
    user_in_tenant_a: User,
    modelo_catalogo: DeteccaoModelo,
    liquidacoes_tenant_a: list[Liquidacao],
):
    token = await _login(client, user_in_tenant_a.email)
    liq_id = str(liquidacoes_tenant_a[1].id)

    r = await client.post(
        f"{API_BASE}/{liq_id}/tag",
        headers=_auth(token),
        json={"tag": "fraude", "nota": "Baixa confirmada sem justificativa."},
    )
    assert r.status_code == 201, r.text

    # Re-tag NAO edita: cria registro novo; a vigente e a mais recente.
    r = await client.post(
        f"{API_BASE}/{liq_id}/tag", headers=_auth(token), json={"tag": "ok"}
    )
    assert r.status_code == 201

    r = await client.get(API_BASE, headers=_auth(token))
    row = next(x for x in r.json()["rows"] if x["liquidacao_id"] == liq_id)
    assert row["tag_vigente"] == "OK"

    from sqlalchemy import func, select

    from app.modules.risco.models import CuradoriaTag

    async with AsyncSessionLocal() as db:
        n = (
            await db.execute(
                select(func.count())
                .select_from(CuradoriaTag)
                .where(CuradoriaTag.liquidacao_id == liquidacoes_tenant_a[1].id)
            )
        ).scalar_one()
    assert n == 2  # nada foi apagado


@pytest.mark.asyncio
async def test_tag_exige_write(
    client: AsyncClient,
    user_a_read_only: User,
    modelo_catalogo: DeteccaoModelo,
    liquidacoes_tenant_a: list[Liquidacao],
):
    token = await _login(client, user_a_read_only.email)
    r = await client.post(
        f"{API_BASE}/{liquidacoes_tenant_a[0].id}/tag",
        headers=_auth(token),
        json={"tag": "fraude"},
    )
    assert r.status_code == 403


# ---- Modelos / treino ------------------------------------------------------


@pytest.mark.asyncio
async def test_catalogo_modelos_e_treino_sem_rotulos(
    client: AsyncClient,
    user_in_tenant_a: User,
    modelo_catalogo: DeteccaoModelo,
    liquidacoes_tenant_a: list[Liquidacao],
):
    token = await _login(client, user_in_tenant_a.email)

    r = await client.get(API_MODELOS, headers=_auth(token))
    assert r.status_code == 200
    modelos = {m["nome"]: m for m in r.json()}
    assert "liquidacao_boleto" in modelos
    assert modelos["liquidacao_boleto"]["versao_ativa"] is None
    assert modelos["liquidacao_boleto"]["versoes"] == []

    # Sem rotulos homologados suficientes o treino recusa com mensagem clara.
    r = await client.post(
        f"{API_MODELOS}/liquidacao_boleto/treinar", headers=_auth(token), json={}
    )
    assert r.status_code == 422
    assert "Rotulos insuficientes" in r.json()["detail"]


@pytest.mark.asyncio
async def test_treino_exige_admin(
    client: AsyncClient,
    user_a_read_only: User,
    modelo_catalogo: DeteccaoModelo,
):
    token = await _login(client, user_a_read_only.email)
    r = await client.post(
        f"{API_MODELOS}/liquidacao_boleto/treinar", headers=_auth(token), json={}
    )
    assert r.status_code == 403


# ---- Isolamento (§10) ------------------------------------------------------


@pytest.mark.asyncio
async def test_isolamento_tenant_b_nao_ve_nem_tageia(
    client: AsyncClient,
    user_b_admin: User,
    modelo_catalogo: DeteccaoModelo,
    liquidacoes_tenant_a: list[Liquidacao],
):
    token_b = await _login(client, user_b_admin.email)

    r = await client.get(API_BASE, headers=_auth(token_b))
    assert r.status_code == 200
    assert r.json()["total"] == 0  # liquidacoes de A invisiveis a B

    # Tag cross-tenant: 404, nunca escreve.
    r = await client.post(
        f"{API_BASE}/{liquidacoes_tenant_a[0].id}/tag",
        headers=_auth(token_b),
        json={"tag": "fraude"},
    )
    assert r.status_code == 404

    from sqlalchemy import func, select

    from app.modules.risco.models import CuradoriaTag

    async with AsyncSessionLocal() as db:
        n = (
            await db.execute(
                select(func.count())
                .select_from(CuradoriaTag)
                .where(
                    CuradoriaTag.liquidacao_id == liquidacoes_tenant_a[0].id,
                    CuradoriaTag.tenant_id == user_b_admin.tenant_id,
                )
            )
        ).scalar_one()
    assert n == 0
