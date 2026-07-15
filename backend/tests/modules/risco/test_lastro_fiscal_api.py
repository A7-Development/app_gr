"""Tests do lastro fiscal (/risco/lastro-fiscal) — F4 da integracao SERPRO.

Cobre: classificacao FIS-*, feed (evento x nota de titulo ABERTO), resumo,
RBAC (403 sem permissao de risco) e isolamento §10 (B nao ve dado de A).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import count
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType
from app.modules.risco.services.lastro_fiscal import classificar_evento
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.warehouse.fiscal_nfe import Nfe, NfeRawDocumento
from app.warehouse.nfe_estado import NfeEvento, NfeSituacao
from app.warehouse.operacao import Operacao
from app.warehouse.serpro_raw_nfe import SerproRawNfe
from app.warehouse.titulo import Titulo
from app.warehouse.titulo_fiscal import WhTituloFiscal
from tests.modules.risco.test_curadoria_liquidacoes_api import (  # noqa: F401
    _auth,
    _login,
    user_b_admin,
)
from tests.modules.risco.test_padroes_liquidacao_api import (  # noqa: F401
    user_a_sem_risco,
)

API = "/api/v1/risco/lastro-fiscal"

_SEQ = count(910_000_000)


def _chave() -> str:
    return f"352607{uuid4().int % 10**38:038d}"


async def _seed_nota_com_evento(
    tenant_id,
    *,
    situacao_titulo: int = 0,
    tp_evento: int = 110111,
    ret_c_stat: int = 155,
    dh_evento: datetime | None = None,
    efetivacao: datetime | None = None,
) -> str:
    """wh_titulo + ponte + operacao + bronze/silver SERPRO + 1 evento."""
    chave = _chave()
    tid = next(_SEQ)
    agora = datetime.now(UTC)
    dh = dh_evento or agora
    async with AsyncSessionLocal() as db:
        db.add(
            Operacao(
                tenant_id=tenant_id,
                operacao_id=tid,
                data_de_cadastro=agora - timedelta(days=10),
                data_de_efetivacao=efetivacao or (agora - timedelta(days=9)),
                efetivada=True,
                quantidade_de_titulos=1,
                origem=1,
                modalidade="FAT-DM",
                coobrigacao=True,
                conta_operacional_id=1,
                unidade_administrativa_id=1,
                source_type=SourceType.ERP_BITFIN,
                source_id=f"op-{tid}",
                ingested_by_version="test",
            )
        )
        db.add(
            Titulo(
                tenant_id=tenant_id,
                titulo_id=tid,
                sigla="DM",
                numero=f"{tid}/1",
                data_de_emissao=agora - timedelta(days=10),
                data_de_vencimento=agora + timedelta(days=20),
                data_de_vencimento_efetiva=agora + timedelta(days=20),
                data_de_cadastro=agora - timedelta(days=10),
                data_da_situacao=agora,
                valor=1000,
                saldo_devedor=1000,
                situacao=situacao_titulo,
                sacado_id=1,
                conta_operacional_id=1,
                unidade_administrativa_id=1,
                operacao_id=tid,
                source_type=SourceType.ERP_BITFIN,
                source_id=str(tid),
                ingested_by_version="test",
            )
        )
        db.add(
            WhTituloFiscal(
                tenant_id=tenant_id,
                titulo_id=tid,
                nota_fiscal_eletronica_id=tid,
                chave_acesso=chave,
                source_type=SourceType.ERP_BITFIN,
                source_id=f"{tid}:{tid}",
                ingested_by_version="test",
            )
        )
        raw = SerproRawNfe(
            tenant_id=tenant_id,
            chave_acesso=chave,
            payload={"nfeProc": {}},
            qtd_eventos=1,
            trigger="bancada",
            payload_sha256=uuid4().hex + uuid4().hex,
            fetched_by_version="test",
        )
        db.add(raw)
        await db.flush()
        db.add(
            NfeEvento(
                tenant_id=tenant_id,
                raw_id=raw.id,
                chave_acesso=chave,
                tp_evento=tp_evento,
                n_seq_evento=1,
                ret_c_stat=ret_c_stat,
                desc_evento="Cancelamento" if tp_evento == 110111 else "Evento",
                x_just="teste",
                dh_evento=dh,
                evento_json={},
                source_type=SourceType.DATA_SERPRO_NFE,
                source_id=f"{chave}:{tp_evento}:1",
                ingested_by_version="test",
            )
        )
        db.add(
            NfeSituacao(
                tenant_id=tenant_id,
                last_raw_id=raw.id,
                chave_acesso=chave,
                situacao=(
                    "cancelada_fora_prazo" if tp_evento == 110111 else "autorizada"
                ),
                cancelada=tp_evento == 110111,
                qtd_eventos=1,
                source_type=SourceType.DATA_SERPRO_NFE,
                source_id=chave,
                ingested_by_version="test",
            )
        )
        await db.commit()
    return chave


# ---- Classificacao (funcao pura) ---------------------------------------------


def test_classificacao_fis() -> None:
    assert classificar_evento(110111, 135) == ("FIS-01", "critica")
    assert classificar_evento(110111, 155) == ("FIS-02", "critica")
    assert classificar_evento(210240, 135) == ("FIS-03", "critica")
    assert classificar_evento(210220, 135) == ("FIS-04", "critica")
    assert classificar_evento(210200, 135) == ("FIS-06", "positiva")
    assert classificar_evento(110110, 135) == ("FIS-07", "baixa")
    assert classificar_evento(210210, 135) == ("FIS-09", "info")
    # Zero ocultacao: tipo desconhecido nao some do feed.
    assert classificar_evento(610600, None) == ("FIS-99", "info")


# ---- Feed + resumo -------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_titulo_aberto_aparece_liquidado_nao(
    client: AsyncClient, tenant_a: Tenant, user_in_tenant_a: User
) -> None:
    chave_aberta = await _seed_nota_com_evento(tenant_a.id, situacao_titulo=0)
    await _seed_nota_com_evento(tenant_a.id, situacao_titulo=1)  # liquidado

    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(f"{API}/ocorrencias", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    chaves = {o["chave_acesso"] for o in body["ocorrencias"]}
    assert chave_aberta in chaves
    assert body["total"] == len(body["ocorrencias"])  # paginacao reconcilia

    oc = next(o for o in body["ocorrencias"] if o["chave_acesso"] == chave_aberta)
    assert oc["codigo"] == "FIS-02"
    assert oc["severidade"] == "critica"
    assert oc["pos_cessao"] is True
    assert oc["qtd_titulos_abertos"] == 1
    assert oc["saldo_devedor_aberto"] == 1000.0


@pytest.mark.asyncio
async def test_resumo_conta_mortas_e_confirmadas(
    client: AsyncClient, tenant_a: Tenant, user_in_tenant_a: User
) -> None:
    await _seed_nota_com_evento(tenant_a.id, tp_evento=110111, ret_c_stat=155)
    await _seed_nota_com_evento(tenant_a.id, tp_evento=210200, ret_c_stat=135)

    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(f"{API}/resumo", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["notas_vigiadas"] == 2
    assert body["notas_mortas"] == 1
    assert body["notas_mortas_saldo"] == 1000.0
    assert body["confirmadas"] == 1
    assert body["pct_confirmada"] == 50.0


@pytest.mark.asyncio
async def test_filtro_severidade(
    client: AsyncClient, tenant_a: Tenant, user_in_tenant_a: User
) -> None:
    await _seed_nota_com_evento(tenant_a.id, tp_evento=110111, ret_c_stat=135)
    await _seed_nota_com_evento(tenant_a.id, tp_evento=210210, ret_c_stat=135)

    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(
        f"{API}/ocorrencias?severidade=critica", headers=_auth(token)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["ocorrencias"][0]["codigo"] == "FIS-01"


# ---- RBAC + isolamento ---------------------------------------------------------


@pytest.mark.asyncio
async def test_403_sem_permissao_de_risco(
    client: AsyncClient, tenant_a: Tenant, user_a_sem_risco: User  # noqa: F811
) -> None:
    token = await _login(client, user_a_sem_risco.email)
    for path in ("/resumo", "/ocorrencias"):
        r = await client.get(f"{API}{path}", headers=_auth(token))
        assert r.status_code == 403, f"{path}: {r.status_code}"


@pytest.mark.asyncio
async def test_documento_360_titulo_vencimento_serializa(
    client: AsyncClient, tenant_a: Tenant, user_in_tenant_a: User
) -> None:
    """Regressao: wh_titulo.data_de_vencimento e timestamptz com hora != 0
    (meia-noite -03 = 03:00 UTC); o Documento360Out expoe `date`. Sem o
    .date() no service o Pydantic rejeitava (date_from_datetime_inexact)
    e o endpoint respondia 500 em prod."""
    chave = await _seed_nota_com_evento(tenant_a.id, situacao_titulo=0)
    async with AsyncSessionLocal() as db:
        raw = NfeRawDocumento(
            tenant_id=tenant_a.id,
            chave_acesso=chave,
            documento={"nfeProc": {}},
            nome_arquivo_xml=f"{chave}.xml",
            payload_sha256="0" * 64,
            fetched_by_version="test",
        )
        db.add(raw)
        await db.flush()
        db.add(
            Nfe(
                tenant_id=tenant_a.id,
                raw_documento_id=raw.id,
                chave_acesso=chave,
                numero=123,
                emitente_documento="12345678000199",
                source_type=SourceType.DOCUMENT_NFE,
                source_id=chave,
                ingested_by_version="test",
            )
        )
        await db.commit()

    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(f"{API}/documento/{chave}", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nota"]["numero"] == 123
    assert len(body["titulos"]) == 1
    venc = date.fromisoformat(body["titulos"][0]["vencimento"])
    # seed poe vencimento em agora+20d; tolera cruzar meia-noite UTC no teste
    assert 19 <= (venc - datetime.now(UTC).date()).days <= 21
    # timeline de eventos presente (historia do documento)
    assert len(body["eventos"]) == 1


@pytest.mark.asyncio
async def test_isolamento_tenant_b_nao_ve_a(
    client: AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    user_in_tenant_a: User,
    user_b_admin: User,  # noqa: F811
) -> None:
    await _seed_nota_com_evento(tenant_a.id)

    token_b = await _login(client, user_b_admin.email)
    r = await client.get(f"{API}/ocorrencias", headers=_auth(token_b))
    assert r.status_code == 200
    assert r.json()["total"] == 0
    r = await client.get(f"{API}/resumo", headers=_auth(token_b))
    assert r.json()["notas_vigiadas"] == 0
