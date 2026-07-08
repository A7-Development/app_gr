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
from app.warehouse.dim import DimProduto
from app.warehouse.liquidacao import Liquidacao
from app.warehouse.operacao import Operacao

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


def _liquidacao(
    tenant_id, titulo_id: int, operacao_id: int, *, canal: str, evidencia: str | None = None
) -> Liquidacao:
    """Evento de desfecho declarado (F3) como o sync do Bitfin gravaria."""
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
    """Perfil observado le os eventos DECLARADOS de wh_liquidacao (F3).

    FAT com 3 liquidacoes: 1 bancaria + 1 baixa manual com boleto
    (baixa_confirmada) + 1 baixa manual sem boleto (sem_registro)
    -> 66,7% com boleto (< 90% obrigatorio) e 50% de baixa manual nos
    com-boleto. CSG (em aberto) com 1 liquidacao. Recompra NAO entra no
    universo do perfil.
    """
    async with AsyncSessionLocal() as db:
        db.add(_operacao(tenant_a.id, 100, "FAT-DM"))
        db.add(_operacao(tenant_a.id, 200, "CSG-DM"))
        db.add(_liquidacao(tenant_a.id, 1, 100, canal="bancaria"))
        db.add(
            _liquidacao(
                tenant_a.id, 2, 100, canal="baixa_manual", evidencia="baixa_confirmada"
            )
        )
        db.add(
            _liquidacao(
                tenant_a.id, 3, 100, canal="baixa_manual", evidencia="sem_registro"
            )
        )
        db.add(_liquidacao(tenant_a.id, 4, 200, canal="bancaria"))
        # Recompra fica FORA do universo do perfil (canal proprio).
        db.add(_liquidacao(tenant_a.id, 5, 100, canal="recompra", evidencia="recompra_efetivada"))
        await db.commit()

    token = await _login(client, user_in_tenant_a.email)
    r = await client.put(f"{API_BASE}/FAT", headers=_auth(token), json=_BODY_FAT)
    assert r.status_code == 200

    r = await client.get(API_BASE, headers=_auth(token))
    rows = {row["produto_sigla"]: row for row in r.json()}

    fat = rows["FAT"]
    assert fat["observado"]["qtd_titulos"] == 3
    assert fat["observado"]["qtd_bancarizados"] == 2
    assert fat["observado"]["pct_bancarizado"] == 66.7
    assert fat["observado"]["qtd_baixa_manual_bancarizados"] == 1
    assert fat["observado"]["pct_baixa_manual_bancarizados"] == 50.0
    # boleto obrigatorio com 66,7% + baixa manual em produto anomalo.
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
