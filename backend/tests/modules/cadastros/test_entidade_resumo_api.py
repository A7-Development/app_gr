"""Testes — GET /cadastros/entidades/{documento}/resumo (peek da Ficha).

Cobertura: happy path (identidade + papeis), normalizacao de documento
mascarado, 404 para documento desconhecido e ISOLAMENTO DE TENANT
(entidade do tenant B nunca aparece para user do tenant A).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import EntidadePapel, SourceType, TipoPessoa
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.warehouse.entidade import WhEntidade, WhEntidadePapel

API = "/api/v1/cadastros/entidades"

CNPJ_A = "11444777000161"  # matriz (DV validos)
CNPJ_B = "00000000000191"  # Banco do Brasil — entidade do tenant B


async def _login(client: AsyncClient, email: str) -> dict:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "test-password"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed_entidade(
    tenant_id: UUID, documento: str, nome: str, *, papel: EntidadePapel | None
) -> None:
    async with AsyncSessionLocal() as db:
        ent = WhEntidade(
            tenant_id=tenant_id,
            documento=documento,
            tipo_pessoa=TipoPessoa.PJ,
            documento_raiz=documento[:8],
            filial_numero=documento[8:12],
            is_matriz=documento[8:12] == "0001",
            nome=nome,
            source_type=SourceType.ERP_BITFIN,
            source_id="999",
            ingested_by_version="test_v0",
        )
        db.add(ent)
        await db.flush()
        if papel is not None:
            db.add(
                WhEntidadePapel(
                    tenant_id=tenant_id,
                    entidade_id=ent.id,
                    papel=papel,
                    source_type=SourceType.ERP_BITFIN,
                    source_id="522",
                    ingested_by_version="test_v0",
                )
            )
        await db.commit()


@pytest.mark.asyncio
async def test_resumo_happy_path_com_papel_cedente(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    await _seed_entidade(
        user_in_tenant_a.tenant_id, CNPJ_A, "EXEMPLO LTDA", papel=EntidadePapel.CEDENTE
    )
    headers = await _login(client, user_in_tenant_a.email)

    r = await client.get(f"{API}/{CNPJ_A}/resumo", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["documento"] == CNPJ_A
    assert body["nome"] == "EXEMPLO LTDA"
    assert body["documento_raiz"] == "11444777"
    assert body["is_matriz"] is True
    assert [p["papel"] for p in body["papeis"]] == ["cedente"]
    assert body["cedente_id"] == 522  # source_id do papel cedente, numerico
    # Estabelecimentos da raiz incluem o proprio
    assert [e["documento"] for e in body["estabelecimentos"]] == [CNPJ_A]
    assert body["bureau"] is None  # sem consulta Serasa seedada


@pytest.mark.asyncio
async def test_resumo_normaliza_documento_padded_e_mascarado(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    """Aceita o formato padded-15 do Bitfin e mascara sem '/' (slash
    encodado nao roteia em path param — frontend manda digitos puros)."""
    await _seed_entidade(
        user_in_tenant_a.tenant_id, CNPJ_A, "EXEMPLO LTDA", papel=None
    )
    headers = await _login(client, user_in_tenant_a.email)

    r = await client.get(f"{API}/0{CNPJ_A}/resumo", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["documento"] == CNPJ_A

    r = await client.get(f"{API}/11.444.777_0001-61/resumo", headers=headers)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_resumo_404_para_documento_desconhecido(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    headers = await _login(client, user_in_tenant_a.email)
    r = await client.get(f"{API}/{CNPJ_A}/resumo", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_isolamento_tenant_a_nao_ve_entidade_do_tenant_b(
    client: AsyncClient, user_in_tenant_a: User, tenant_b: Tenant
) -> None:
    """Entidade existe APENAS no tenant B -> user do tenant A recebe 404."""
    await _seed_entidade(tenant_b.id, CNPJ_B, "ENTIDADE DO B", papel=None)
    headers = await _login(client, user_in_tenant_a.email)

    r = await client.get(f"{API}/{CNPJ_B}/resumo", headers=headers)
    assert r.status_code == 404
