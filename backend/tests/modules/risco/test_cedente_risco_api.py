"""Tests do Painel de Risco de Cedentes (consolidacao + API + isolamento §10)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType, TipoPessoa
from app.modules.risco.models import DeteccaoScore
from app.modules.risco.services.cedente_risco import consolidar
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.warehouse.entidade import WhEntidade
from app.warehouse.posicao_papel import WhPosicaoCedente
from tests.modules.risco.test_curadoria_liquidacoes_api import (  # noqa: F401
    _auth,
    _login,
    liquidacoes_tenant_a,
    modelo_catalogo,
    user_b_admin,
)

API = "/api/v1/risco/cedentes"


@pytest.mark.asyncio
async def test_painel_consolida_e_isola(
    client: AsyncClient,
    user_in_tenant_a: User,
    tenant_a: Tenant,
    modelo_catalogo,  # noqa: F811
    liquidacoes_tenant_a,  # noqa: F811
    user_b_admin: User,  # noqa: F811
):
    liq_normal, liq_baixa = liquidacoes_tenant_a
    async with AsyncSessionLocal() as db:
        # Scores de evento: 1 alto risco com padrao critico + 1 baixo.
        db.add(
            DeteccaoScore(
                tenant_id=tenant_a.id,
                modelo_id=modelo_catalogo.id,
                liquidacao_id=liq_baixa.id,
                score=0.92,
                regra_dura=True,
                regra_dura_motivo="teste",
            )
        )
        db.add(
            DeteccaoScore(
                tenant_id=tenant_a.id,
                modelo_id=modelo_catalogo.id,
                liquidacao_id=liq_normal.id,
                score=0.05,
                regra_dura=False,
            )
        )
        # Posicao em aberto do cedente (carteira atual via wh_posicao_cedente).
        ent = WhEntidade(
            tenant_id=tenant_a.id,
            documento="12345678000199",
            tipo_pessoa=TipoPessoa.PJ,
            documento_raiz="12345678",
            filial_numero="0001",
            is_matriz=True,
            nome="Cedente Teste",
            source_type=SourceType.ERP_BITFIN,
            source_id="ent:1",
            ingested_by_version="test_v0",
        )
        db.add(ent)
        await db.flush()
        db.add(
            WhPosicaoCedente(
                tenant_id=tenant_a.id,
                entidade_id=ent.id,
                papel_source_id="cli:1",
                risco_total_valor=5000,
                source_type=SourceType.ERP_BITFIN,
                source_id="pos:1",
                ingested_by_version="test_v0",
            )
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        summary = await consolidar(db, tenant_a.id, triggered_by="test")
        await db.commit()
    assert summary["cedentes"] == 1
    # 1 linha do indicador + 1 linha do composto
    assert summary["linhas"] == 2

    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(API, headers=_auth(token))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    c = rows[0]
    assert c["cedente_documento"] == "12345678000199"
    # 50% do valor em risco (1 de 2 eventos de mesmo valor) + piso critico 70.
    assert c["risco"] == 70.0
    assert c["n_criticos"] == 1
    # Carteira atual: posicao em aberto do ERP casada por documento.
    assert c["carteira_atual"] == 5000.0
    assert c["indicadores"][0]["indicador"] == "liquidacao_boleto"
    assert c["indicadores"][0]["componentes"]["piso_critico_aplicado"] is True

    # Isolamento: tenant B nao ve o painel de A.
    token_b = await _login(client, user_b_admin.email)
    r = await client.get(API, headers=_auth(token_b))
    assert r.status_code == 200
    assert r.json() == []

    # Sem token = 401.
    r = await client.get(API)
    assert r.status_code == 401
