"""Tests E2E do contrato de liquidacao por produto (modulo risco).

Cobre:
- Listagem dirigida por wh_dim_produto (produto sem contrato = em aberto)
- Definir contrato cria versao 1; redefinir cria versao 2 (append-only)
- Historico de versoes + decision_log CONFIGURATION_CHANGE
- Perfil observado (bancarizado / baixa manual) calculado do silver
- Divergencias declarado x observado
- RBAC: READ nao define contrato (403)
- Isolamento: contrato do tenant A invisivel ao tenant B; sigla de A = 404 em B
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Module, Permission
from app.core.security import hash_password
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission
from app.warehouse.boleto_vigente import BoletoVigente
from app.warehouse.dim import DimProduto
from app.warehouse.operacao import Operacao
from app.warehouse.titulo import Titulo

API_BASE = "/api/v1/risco/contratos-liquidacao"


async def _login(client: AsyncClient, email: str, password: str = "test-password") -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _dim_produto(tenant_id, sigla: str, nome: str, produto_id: int) -> DimProduto:
    return DimProduto(
        tenant_id=tenant_id,
        produto_id=produto_id,
        sigla=sigla,
        nome=nome,
        source_type="erp:bitfin",
        source_id=f"produto:{produto_id}",
        ingested_by_version="test",
    )


def _operacao(tenant_id, operacao_id: int, modalidade: str) -> Operacao:
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
        source_type="erp:bitfin",
        source_id=f"operacao:{operacao_id}",
        ingested_by_version="test",
    )


def _titulo(tenant_id, titulo_id: int, operacao_id: int, numero: str, situacao: int) -> Titulo:
    now = datetime.now(UTC)
    return Titulo(
        tenant_id=tenant_id,
        titulo_id=titulo_id,
        sigla="DM",
        numero=numero,
        data_de_emissao=now,
        data_de_vencimento=now,
        data_de_vencimento_efetiva=now,
        data_de_cadastro=now,
        data_da_situacao=now,
        valor=1000,
        situacao=situacao,
        sacado_id=1,
        conta_operacional_id=1,
        unidade_administrativa_id=1,
        operacao_id=operacao_id,
        source_type="erp:bitfin",
        source_id=f"titulo:{titulo_id}",
        ingested_by_version="test",
    )


def _boleto_vigente(tenant_id, numero_documento: str, estado: str) -> BoletoVigente:
    now = datetime.now(UTC)
    return BoletoVigente(
        tenant_id=tenant_id,
        banco_origem="237",
        nosso_numero=f"nn-{uuid4().hex[:10]}",
        numero_documento=numero_documento,
        estado=estado,
        tipo_evento_vigente="retorno",
        data_ocorrencia_vigente=now.date(),
        n_eventos=1,
        projected_at=now,
        projected_by_version="test",
    )


@pytest.fixture
async def produtos_tenant_a(tenant_a: Tenant) -> None:
    """FAT + CSG na dimensao do tenant A (CSG fica sem contrato = em aberto)."""
    async with AsyncSessionLocal() as db:
        db.add(_dim_produto(tenant_a.id, "FAT", "Faturização", 1))
        db.add(_dim_produto(tenant_a.id, "CSG", "Consignado", 2))
        await db.commit()


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


_BODY_FAT = {
    "fluxo_esperado": "boleto_bancario",
    "boleto": "obrigatorio",
    "baixa_manual": "anomala",
    "justificativa": "Contrato canonico de Faturização.",
}


# ---- Listagem + versionamento --------------------------------------------


@pytest.mark.asyncio
async def test_list_produtos_sem_contrato_em_aberto(
    client: AsyncClient, user_in_tenant_a: User, produtos_tenant_a: None
):
    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(API_BASE, headers=_auth(token))
    assert r.status_code == 200, r.text
    rows = {row["produto_sigla"]: row for row in r.json()}
    assert set(rows) == {"FAT", "CSG"}
    assert rows["FAT"]["em_aberto"] is True
    assert rows["FAT"]["produto_nome"] == "Faturização"
    assert rows["FAT"]["version"] is None
    assert rows["FAT"]["observado"]["qtd_titulos"] == 0
    # Sem volume, produto aberto NAO vira item de curadoria.
    assert rows["CSG"]["divergencias"] == []


@pytest.mark.asyncio
async def test_definir_e_redefinir_cria_versoes(
    client: AsyncClient, user_in_tenant_a: User, produtos_tenant_a: None, tenant_a: Tenant
):
    token = await _login(client, user_in_tenant_a.email)

    r = await client.put(f"{API_BASE}/FAT", headers=_auth(token), json=_BODY_FAT)
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["version"] == 1
    assert row["em_aberto"] is False
    assert row["fluxo_esperado"] == "boleto_bancario"
    assert row["boleto"] == "obrigatorio"
    assert row["baixa_manual"] == "anomala"

    # Redefinir = NOVA versao (append-only), nunca UPDATE.
    r = await client.put(
        f"{API_BASE}/FAT",
        headers=_auth(token),
        json={**_BODY_FAT, "boleto": "permitido", "justificativa": "Revisao."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    assert r.json()["boleto"] == "permitido"

    r = await client.get(f"{API_BASE}/FAT/versoes", headers=_auth(token))
    assert r.status_code == 200
    versoes = r.json()
    assert [v["version"] for v in versoes] == [2, 1]
    assert versoes[1]["boleto"] == "obrigatorio"

    # Auditoria: cada definicao gravou decision_log CONFIGURATION_CHANGE.
    async with AsyncSessionLocal() as db:
        logs = (
            (
                await db.execute(
                    select(DecisionLog).where(
                        DecisionLog.tenant_id == tenant_a.id,
                        DecisionLog.decision_type == DecisionType.CONFIGURATION_CHANGE,
                        DecisionLog.rule_or_model == "produto_contrato_liquidacao",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(logs) == 2


@pytest.mark.asyncio
async def test_definir_sigla_inexistente_404(
    client: AsyncClient, user_in_tenant_a: User, produtos_tenant_a: None
):
    token = await _login(client, user_in_tenant_a.email)
    r = await client.put(f"{API_BASE}/XXX", headers=_auth(token), json=_BODY_FAT)
    assert r.status_code == 404


# ---- Perfil observado + divergencias --------------------------------------


@pytest.mark.asyncio
async def test_perfil_observado_e_divergencias(
    client: AsyncClient, user_in_tenant_a: User, produtos_tenant_a: None, tenant_a: Tenant
):
    """FAT com 2 titulos: #1 bancarizado liquidado por baixa manual (boleto
    vigente segue 'ativo'), #2 sem boleto. CSG (em aberto) com 1 titulo.
    """
    async with AsyncSessionLocal() as db:
        db.add(_operacao(tenant_a.id, 100, "FAT-DM"))
        db.add(_operacao(tenant_a.id, 200, "CSG-DM"))
        db.add(_titulo(tenant_a.id, 1, 100, "DOC-1", situacao=1))
        db.add(_titulo(tenant_a.id, 2, 100, "DOC-2", situacao=0))
        db.add(_titulo(tenant_a.id, 3, 200, "DOC-3", situacao=0))
        db.add(_boleto_vigente(tenant_a.id, "DOC-1", estado="ativo"))
        await db.commit()

    token = await _login(client, user_in_tenant_a.email)
    r = await client.put(f"{API_BASE}/FAT", headers=_auth(token), json=_BODY_FAT)
    assert r.status_code == 200

    r = await client.get(API_BASE, headers=_auth(token))
    rows = {row["produto_sigla"]: row for row in r.json()}

    fat = rows["FAT"]
    assert fat["observado"]["qtd_titulos"] == 2
    assert fat["observado"]["qtd_bancarizados"] == 1
    assert fat["observado"]["pct_bancarizado"] == 50.0
    assert fat["observado"]["qtd_baixa_manual_bancarizados"] == 1
    assert fat["observado"]["pct_baixa_manual_bancarizados"] == 100.0
    # boleto obrigatorio com 50% bancarizado + baixa manual em produto anomalo.
    assert "boleto_abaixo_do_esperado" in fat["divergencias"]
    assert "baixa_manual_em_produto_anomalo" in fat["divergencias"]

    csg = rows["CSG"]
    assert csg["em_aberto"] is True
    assert csg["observado"]["qtd_titulos"] == 1
    assert csg["divergencias"] == ["volume_em_produto_aberto"]


# ---- RBAC + isolamento -----------------------------------------------------


@pytest.mark.asyncio
async def test_read_only_nao_define_contrato_403(
    client: AsyncClient, user_a_read_only: User, produtos_tenant_a: None
):
    token = await _login(client, user_a_read_only.email)
    # Listar pode (READ)...
    r = await client.get(API_BASE, headers=_auth(token))
    assert r.status_code == 200
    # ...definir nao (WRITE).
    r = await client.put(f"{API_BASE}/FAT", headers=_auth(token), json=_BODY_FAT)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_isolamento_tenant(
    client: AsyncClient,
    user_in_tenant_a: User,
    user_b_admin: User,
    produtos_tenant_a: None,
):
    token_a = await _login(client, user_in_tenant_a.email)
    r = await client.put(f"{API_BASE}/FAT", headers=_auth(token_a), json=_BODY_FAT)
    assert r.status_code == 200

    token_b = await _login(client, user_b_admin.email)
    # Tenant B nao tem produtos na dimensao -> lista vazia (nao ve os de A).
    r = await client.get(API_BASE, headers=_auth(token_b))
    assert r.status_code == 200
    assert r.json() == []
    # Sigla que so existe no tenant A = 404 para B (definir e historico).
    r = await client.put(f"{API_BASE}/FAT", headers=_auth(token_b), json=_BODY_FAT)
    assert r.status_code == 404
    r = await client.get(f"{API_BASE}/FAT/versoes", headers=_auth(token_b))
    assert r.status_code == 404
