"""Service Serasa PJ query — orquestracao raw + silver + decision_log.

Testes de integracao com gr_db_test. A consulta HTTP a Serasa e mockada
via patch em `query_pj_analitico`; o resto (config decifrada, persistencia
nas 6 tabelas, decision_log) usa banco real.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.bureau.serasa_pj.client import (
    BureauQueryResult,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.errors import (
    SerasaPjAuthError,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.version import (
    ADAPTER_VERSION,
)
from app.modules.integracoes.services.serasa_pj_query import (
    execute_pj_query,
)
from app.modules.integracoes.services.source_config import upsert_config
from app.shared.audit_log.decision_log import DecisionLog
from app.shared.identity.tenant import Tenant
from app.warehouse.serasa_pj_consulta import SerasaPjConsulta
from app.warehouse.serasa_pj_endereco import SerasaPjEndereco
from app.warehouse.serasa_pj_participacao import SerasaPjParticipacao
from app.warehouse.serasa_pj_raw_relatorio import SerasaPjRawRelatorio
from app.warehouse.serasa_pj_restricao import SerasaPjRestricao
from app.warehouse.serasa_pj_socio import SerasaPjSocio


def _sample_payload() -> dict:
    """Payload minimal espelhando estrutura real Serasa PJ segmento 028."""
    return {
        "reports": [
            {
                "reportName": "RELATORIO_AVANCADO_PJ_ANALITICO",
                "identificationReport": {
                    "companyName": "TEST EMPRESA LTDA",
                    "documentNumber": "12345678000199",
                    "statusCodeDescription": "ATIVA",
                    "companyFoundation": "2018-03-15",
                    "cnae": "47113-02",
                    "economicActivity": "COMERCIO VAREJISTA",
                    "address": {
                        "addressLine": "RUA TESTE 1",
                        "city": "SAO PAULO",
                        "state": "SP",
                        "zipCode": "01001000",
                    },
                },
                "negativeData": {
                    "pefin": {
                        "summary": {
                            "count": 1,
                            "balance": 300.00,
                            "firstOccurrence": "2025-01-10",
                            "lastOccurrence": "2025-01-10",
                        },
                        "pefinResponse": [
                            {
                                "cadus": "C001",
                                "amount": 300.00,
                                "creditorName": "Y",
                                "occurrenceDate": "2025-01-10",
                            },
                        ],
                    },
                    "refin": {
                        "summary": {
                            "count": 1,
                            "balance": 500.00,
                            "firstOccurrence": "2025-02-01",
                            "lastOccurrence": "2025-02-01",
                        },
                        "refinResponse": [
                            {
                                "cadus": "C002",
                                "amount": 500.00,
                                "creditorName": "X",
                                "occurrenceDate": "2025-02-01",
                            },
                        ],
                    },
                    "notary": {"summary": {"count": 0, "balance": 0.0}},
                    "check": {"summary": {"count": 0, "balance": 0.0}},
                    "collectionRecords": {
                        "summary": {"count": 0, "balance": 0.0}
                    },
                },
            },
        ],
    }


def _make_result(
    payload: dict | None = None,
    *,
    requested: str = "RELATORIO_AVANCADO_PJ_ANALITICO",
    actual: str | None = None,
) -> BureauQueryResult:
    return BureauQueryResult(
        payload=payload or _sample_payload(),
        requested_report=requested,
        actual_report_returned=actual or requested,
        status_code=200,
        cost_center="dossie-1",
        latency_ms=123.4,
    )


async def _seed_serasa_config(tenant_id) -> None:
    async with AsyncSessionLocal() as db:
        await upsert_config(
            db,
            tenant_id,
            SourceType.BUREAU_SERASA_PJ,
            {
                "base_url": "https://api.test",
                "client_id": "u",
                "client_secret": "p",
                "retailer_document_id": "11111111000111",
            },
            environment=Environment.PRODUCTION,
            enabled=True,
        )


@pytest.mark.asyncio
async def test_happy_path_persists_raw_silver_and_audit(
    tenant_a: Tenant,
) -> None:
    await _seed_serasa_config(tenant_a.id)

    fake_result = _make_result()
    with patch(
        "app.modules.integracoes.services.serasa_pj_query.query_pj_analitico",
        return_value=fake_result,
    ):
        summary = await execute_pj_query(
            tenant_id=tenant_a.id,
            cnpj="12345678000199",
            triggered_by="user:test",
        )

    assert summary["ok"] is True, summary["errors"]
    assert summary["raw_id"] is not None
    assert summary["consulta_id"] is not None
    # Segmento 028 nao retorna socios nem participacoes — pefin + refin = 2
    # restricoes individuais, 1 endereco unico em address dict, 5 summaries
    # (1 por categoria de negativeData, mesmo as zeradas), 0 pagamentos /
    # inquiries (sample minimo nao inclui esses blocos).
    assert summary["counts"] == {
        "socios": 0,
        "restricoes": 2,
        "restricao_summaries": 5,
        "participacoes": 0,
        "enderecos": 1,
        "pagamento_buckets": 0,
        "consultas_listadas_detalhe": 0,
        "predecessores": 0,
        "consultas_total_12m": 0,
        "business_references": 0,
        "pagamento_evolucao_mensal": 0,
        "atraso_medio_mensal": 0,
        "payment_comparatives": 0,
    }
    assert summary["adapter_version"] == ADAPTER_VERSION

    # Bronze: 1 linha com payload completo + sha + cost_center.
    async with AsyncSessionLocal() as db:
        raws = (
            await db.execute(
                select(SerasaPjRawRelatorio).where(
                    SerasaPjRawRelatorio.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(raws) == 1
        raw = raws[0]
        assert raw.cnpj == "12345678000199"
        assert raw.cost_center == "dossie-1"
        assert raw.triggered_by == "user:test"
        # Estrutura real: payload tem envelope `reports[0]`.
        assert raw.payload["reports"][0]["identificationReport"][
            "companyName"
        ] == "TEST EMPRESA LTDA"
        assert raw.payload_sha256

    # Silver consulta: 1 linha com header preenchido.
    async with AsyncSessionLocal() as db:
        consultas = (
            await db.execute(
                select(SerasaPjConsulta).where(
                    SerasaPjConsulta.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(consultas) == 1
        c = consultas[0]
        assert c.cnpj == "12345678000199"
        assert c.razao_social == "TEST EMPRESA LTDA"
        assert c.has_refin is True
        assert c.has_pefin is True
        assert c.has_protesto is False
        assert c.count_refin == 1
        assert c.count_pefin == 1
        assert c.reciprocity_downgrade is False

    # Silver filhas: somente restricoes + endereco neste contrato.
    async with AsyncSessionLocal() as db:
        socios = (
            await db.execute(
                select(SerasaPjSocio).where(
                    SerasaPjSocio.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(socios) == 0  # nao retorna no segmento 028

        restricoes = (
            await db.execute(
                select(SerasaPjRestricao).where(
                    SerasaPjRestricao.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(restricoes) == 2
        tipos = sorted(r.tipo for r in restricoes)
        assert tipos == ["pefin", "refin"]

        participacoes = (
            await db.execute(
                select(SerasaPjParticipacao).where(
                    SerasaPjParticipacao.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(participacoes) == 0  # nao retorna no segmento 028

        enderecos = (
            await db.execute(
                select(SerasaPjEndereco).where(
                    SerasaPjEndereco.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(enderecos) == 1
        assert enderecos[0].uf == "SP"

    # Decision_log: 1 entrada com rule_or_model + output ok.
    async with AsyncSessionLocal() as db:
        logs = (
            await db.execute(
                select(DecisionLog).where(
                    DecisionLog.tenant_id == tenant_a.id,
                    DecisionLog.rule_or_model == "serasa_pj_adapter",
                )
            )
        ).scalars().all()
        assert len(logs) == 1
        assert logs[0].rule_or_model_version == ADAPTER_VERSION
        assert logs[0].triggered_by == "user:test"
        assert logs[0].output["ok"] is True
        assert logs[0].output["counts"]["restricoes"] == 2


@pytest.mark.asyncio
async def test_fails_when_tenant_has_no_config(tenant_a: Tenant) -> None:
    """Sem tenant_source_config, retorna ok=False sem chamar Serasa."""
    with patch(
        "app.modules.integracoes.services.serasa_pj_query.query_pj_analitico"
    ) as mock_query:
        summary = await execute_pj_query(
            tenant_id=tenant_a.id,
            cnpj="12345678000199",
            triggered_by="user:test",
        )

    assert summary["ok"] is False
    assert summary["raw_id"] is None
    assert any("sem tenant_source_config" in e for e in summary["errors"])
    mock_query.assert_not_called()


@pytest.mark.asyncio
async def test_query_error_is_audited_and_returns_ok_false(
    tenant_a: Tenant,
) -> None:
    await _seed_serasa_config(tenant_a.id)

    async def _raise(*_a, **_kw):
        raise SerasaPjAuthError("rejeitada")

    with patch(
        "app.modules.integracoes.services.serasa_pj_query.query_pj_analitico",
        side_effect=_raise,
    ):
        summary = await execute_pj_query(
            tenant_id=tenant_a.id,
            cnpj="12345678000199",
            triggered_by="user:test",
        )

    assert summary["ok"] is False
    assert any("SerasaPjAuthError" in e for e in summary["errors"])

    # Decision_log e gravado mesmo na falha — auditoria nao some.
    async with AsyncSessionLocal() as db:
        logs = (
            await db.execute(
                select(DecisionLog).where(
                    DecisionLog.tenant_id == tenant_a.id,
                    DecisionLog.rule_or_model == "serasa_pj_adapter",
                )
            )
        ).scalars().all()
        assert len(logs) == 1
        assert logs[0].output["ok"] is False
        assert logs[0].output["errors"]


@pytest.mark.asyncio
async def test_reciprocity_downgrade_flagged_in_silver(
    tenant_a: Tenant,
) -> None:
    """Quando Serasa devolve reportName diferente do solicitado, silver marca."""
    await _seed_serasa_config(tenant_a.id)

    fake = _make_result(
        actual="RELATORIO_AVANCADO_PJ"  # sintetico, nao analitico
    )
    with patch(
        "app.modules.integracoes.services.serasa_pj_query.query_pj_analitico",
        return_value=fake,
    ):
        summary = await execute_pj_query(
            tenant_id=tenant_a.id,
            cnpj="12345678000199",
            triggered_by="user:test",
        )

    assert summary["ok"] is True
    assert summary["reciprocity_downgrade"] is True

    async with AsyncSessionLocal() as db:
        consulta = (
            await db.execute(
                select(SerasaPjConsulta).where(
                    SerasaPjConsulta.tenant_id == tenant_a.id
                )
            )
        ).scalar_one()
        assert consulta.reciprocity_downgrade is True
        assert consulta.actual_report_returned == "RELATORIO_AVANCADO_PJ"


@pytest.mark.asyncio
async def test_two_consultas_same_cnpj_create_two_rows(
    tenant_a: Tenant,
) -> None:
    """Cada consulta e evento — re-executar gera nova linha bronze + nova consulta.
    A target table e UNique por (tenant_id, source_id), e source_id = raw_id
    (novo a cada execucao), entao nao ha colisao.
    """
    await _seed_serasa_config(tenant_a.id)

    with patch(
        "app.modules.integracoes.services.serasa_pj_query.query_pj_analitico",
        return_value=_make_result(),
    ):
        await execute_pj_query(
            tenant_id=tenant_a.id,
            cnpj="12345678000199",
            triggered_by="user:test",
        )
        await execute_pj_query(
            tenant_id=tenant_a.id,
            cnpj="12345678000199",
            triggered_by="user:test",
        )

    async with AsyncSessionLocal() as db:
        n_raw = (
            await db.execute(
                select(SerasaPjRawRelatorio).where(
                    SerasaPjRawRelatorio.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        n_consulta = (
            await db.execute(
                select(SerasaPjConsulta).where(
                    SerasaPjConsulta.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
    assert len(n_raw) == 2
    assert len(n_consulta) == 2  # cada consulta e evento separado


@pytest.mark.asyncio
async def test_tenant_isolation(
    tenant_a: Tenant, tenant_b: Tenant
) -> None:
    """Consulta do tenant A nao aparece nas tabelas escopadas pelo tenant B."""
    await _seed_serasa_config(tenant_a.id)
    await _seed_serasa_config(tenant_b.id)

    with patch(
        "app.modules.integracoes.services.serasa_pj_query.query_pj_analitico",
        return_value=_make_result(),
    ):
        await execute_pj_query(
            tenant_id=tenant_a.id,
            cnpj="12345678000199",
            triggered_by="user:test",
        )

    async with AsyncSessionLocal() as db:
        a_count = (
            await db.execute(
                select(SerasaPjConsulta).where(
                    SerasaPjConsulta.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        b_count = (
            await db.execute(
                select(SerasaPjConsulta).where(
                    SerasaPjConsulta.tenant_id == tenant_b.id
                )
            )
        ).scalars().all()
        # Filhas tambem devem isolar.
        b_socios = (
            await db.execute(
                select(SerasaPjSocio).where(
                    SerasaPjSocio.tenant_id == tenant_b.id
                )
            )
        ).scalars().all()

    assert len(a_count) == 1
    assert len(b_count) == 0
    assert len(b_socios) == 0
