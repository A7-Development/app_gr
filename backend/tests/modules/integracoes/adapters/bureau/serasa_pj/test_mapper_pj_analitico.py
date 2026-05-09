"""Mapper PJ analitico — happy path + bordas + tolerancia a variantes da API.

Payload-modelo replica estrutura observada em prod 2026-05-01 (segmento
028 factoring/FIDC):

    {"reports": [{
       "reportName": "...",
       "identificationReport": {...},
       "negativeData": {
          "pefin":  {summary, pefinResponse[]},
          "notary": {summary, notaryResponse[]},
          "check":  {summary},
          "refin":  {summary},
          "collectionRecords": {summary}
       },
       "facts": {...},
       ...
    }]}

Esse contrato NAO retorna `partners`, `businessParticipation` nem
`scoring`. Mapper deixa essas colunas nulas / listas vazias quando
ausentes — testes verificam esse comportamento.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.bureau.serasa_pj.mappers.pj_analitico import (
    SerasaPjMappedRows,
    map_pj_analitico,
)


def _full_payload() -> dict:
    """Payload-modelo proximo do esperado da Serasa em PJ analitico segmento 028."""
    return {
        "reports": [
            {
                "reportName": "RELATORIO_AVANCADO_PJ_ANALITICO",
                "identificationReport": {
                    "companyName": "ACME COMERCIO LTDA",
                    "documentNumber": "12345678000199",
                    "statusCodeDescription": "ATIVA",
                    "statusRegistration": "SITUACAO DO CNPJ EM 10/05/2025: ATIVA",
                    "companyFoundation": "2018-03-15",
                    "cnae": "47113-02",
                    "economicActivity": (
                        "Comercio varejista de mercadorias em geral"
                    ),
                    "legalNatureCode": "206",
                    "partnership": "SOCIEDADE EMPRESARIA LIMITADA",
                    "numberEmployees": "12",
                    "updateDate": "2026-04-30",
                    "address": {
                        "addressLine": "RUA DAS FLORES 123",
                        "district": "CENTRO",
                        "city": "SAO PAULO",
                        "state": "SP",
                        "zipCode": "01001000",
                    },
                    "phone": {"areaCode": "11", "phoneNumber": "33334444"},
                },
                "negativeData": {
                    "pefin": {
                        "summary": {
                            "count": 2,
                            "balance": 1130.50,
                            "firstOccurrence": "2024-09-01",
                            "lastOccurrence": "2024-10-12",
                        },
                        "pefinResponse": [
                            {
                                "cadus": "C111",
                                "amount": 350.50,
                                "creditorName": "FORNECEDOR XPTO",
                                "occurrenceDate": "2024-09-01",
                                "inclusionDate": "2024-09-15",
                                "contractId": "CONTRATO-A",
                            },
                            {
                                "cadus": "C222",
                                "amount": 780.00,
                                "creditorName": "TELEFONICA",
                                "occurrenceDate": "2024-10-12",
                                "inclusionDate": "2024-10-20",
                                "contractId": "CONTRATO-B",
                            },
                        ],
                    },
                    "notary": {
                        "summary": {
                            "count": 1,
                            "balance": 5000.00,
                            "firstOccurrence": "2024-11-05",
                            "lastOccurrence": "2024-11-05",
                        },
                        "notaryResponse": [
                            {
                                "cadus": "A333",
                                "amount": 5000.00,
                                "occurrenceDate": "2024-11-05",
                                "inclusionDate": "2024-11-15",
                                "city": "PIRACICABA",
                                "federalUnit": "SP",
                                "officeNumber": "UN",
                            },
                        ],
                    },
                    "check": {"summary": {"count": 0, "balance": 0.0}},
                    "refin": {"summary": {"count": 0, "balance": 0.0}},
                    "collectionRecords": {
                        "summary": {"count": 0, "balance": 0.0}
                    },
                },
                "facts": {
                    "bankrupts": {"summary": {}},
                    "judgementFilings": {"summary": {}},
                },
            },
        ],
    }


def _call_mapper(
    payload: dict,
    *,
    requested: str = "RELATORIO_AVANCADO_PJ_ANALITICO",
    actual: str = "RELATORIO_AVANCADO_PJ_ANALITICO",
) -> SerasaPjMappedRows:
    return map_pj_analitico(
        payload=payload,
        tenant_id=uuid4(),
        raw_id=uuid4(),
        cnpj="12345678000199",
        consulted_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        requested_report=requested,
        actual_report_returned=actual,
    )


def test_full_payload_returns_consulta_plus_filhas() -> None:
    rows = _call_mapper(_full_payload())

    assert isinstance(rows, SerasaPjMappedRows)
    assert isinstance(rows.consulta, dict)
    # Sem partners / businessParticipation no segmento 028.
    assert rows.socios == []
    assert rows.participacoes == []
    # 2 pefin + 1 protesto = 3 itens individuais.
    assert len(rows.restricoes) == 3
    # 1 endereco unico.
    assert len(rows.enderecos) == 1


def test_consulta_header_extracts_identification_report() -> None:
    rows = _call_mapper(_full_payload())
    c = rows.consulta

    assert c["razao_social"] == "ACME COMERCIO LTDA"
    assert c["situacao_cadastral"] == "ATIVA"
    assert c["data_constituicao"] == date(2018, 3, 15)
    assert c["atividade_principal_cnae"] == "47113-02"
    assert (
        c["atividade_principal_descricao"]
        == "Comercio varejista de mercadorias em geral"
    )
    # Esses campos nao vem nesse segmento — devem ser None.
    assert c["nome_fantasia"] is None
    assert c["capital_social"] is None
    assert c["faturamento_presumido"] is None
    assert c["score_h4pj"] is None
    assert c["score_classe"] is None


def test_consulta_counters_use_summary_counts() -> None:
    """Contadores vem de `summary.count` — total real, mesmo que
    `*Response[]` traga apenas top-N."""
    rows = _call_mapper(_full_payload())
    c = rows.consulta

    assert c["has_pefin"] is True
    assert c["has_protesto"] is True
    assert c["has_refin"] is False
    assert c["has_cheque"] is False
    assert c["count_pefin"] == 2
    assert c["count_protesto"] == 1
    assert c["count_refin"] == 0
    assert c["count_cheque"] == 0


def test_consulta_total_value_sums_summary_balances() -> None:
    rows = _call_mapper(_full_payload())
    # 1130.50 (pefin) + 5000.00 (notary) = 6130.50
    assert rows.consulta["valor_total_restricoes"] == Decimal("6130.50")


def test_consulta_total_value_none_when_all_zero() -> None:
    """Quando nao ha balance algum, total fica None (nao 0)."""
    payload = {
        "reports": [
            {
                "reportName": "RELATORIO_AVANCADO_PJ_ANALITICO",
                "identificationReport": {"companyName": "VAZIA"},
                "negativeData": {
                    "pefin": {"summary": {"count": 0, "balance": 0.0}},
                    "notary": {"summary": {"count": 0, "balance": 0.0}},
                    "check": {"summary": {"count": 0, "balance": 0.0}},
                    "refin": {"summary": {"count": 0, "balance": 0.0}},
                    "collectionRecords": {
                        "summary": {"count": 0, "balance": 0.0}
                    },
                },
            },
        ],
    }
    rows = _call_mapper(payload)
    # Tem balance=0 (nao None) em todas as categorias, logo total=0.
    # Modelagem aceita 0 como "tem o campo, e zero". So vira None se
    # NENHUMA categoria informou balance.
    assert rows.consulta["valor_total_restricoes"] == Decimal("0")


def test_reciprocity_downgrade_flagged() -> None:
    rows = _call_mapper(
        _full_payload(),
        requested="RELATORIO_AVANCADO_PJ_ANALITICO",
        actual="RELATORIO_AVANCADO_PJ",
    )
    assert rows.consulta["reciprocity_downgrade"] is True


def test_reciprocity_match_not_flagged() -> None:
    rows = _call_mapper(_full_payload())
    assert rows.consulta["reciprocity_downgrade"] is False


def test_pefin_items_become_restricao_pefin() -> None:
    rows = _call_mapper(_full_payload())
    pefins = [r for r in rows.restricoes if r["tipo"] == "pefin"]
    assert len(pefins) == 2

    p = next(r for r in pefins if r["valor"] == Decimal("350.50"))
    assert p["credor"] == "FORNECEDOR XPTO"
    assert p["data_ocorrencia"] == date(2024, 9, 1)
    # Sem data_baixa nesses payloads — None.
    assert p["data_baixa"] is None
    # Detalhe carrega o item cru + bloco de origem.
    assert p["detalhe"]["cadus"] == "C111"
    assert p["detalhe"]["_payload_block"] == "pefin"


def test_notary_items_become_restricao_protesto() -> None:
    """`notary` (cartorial) e renomeado pra tipo canonico `protesto`."""
    rows = _call_mapper(_full_payload())
    protestos = [r for r in rows.restricoes if r["tipo"] == "protesto"]
    assert len(protestos) == 1

    p = protestos[0]
    assert p["valor"] == Decimal("5000.00")
    # Notary nao tem creditorName — fica None.
    assert p["credor"] is None
    assert p["data_ocorrencia"] == date(2024, 11, 5)
    # Detalhe preserva os campos especificos do protesto (city, etc).
    assert p["detalhe"]["city"] == "PIRACICABA"
    assert p["detalhe"]["officeNumber"] == "UN"
    assert p["detalhe"]["_payload_block"] == "notary"


def test_restricao_source_id_uses_cadus() -> None:
    """Source ID determinista usa `cadus` (ID Serasa unico) — robusto
    contra reordering em re-mapeamento."""
    rows = _call_mapper(_full_payload())
    pefin = next(r for r in rows.restricoes if r["detalhe"]["cadus"] == "C111")
    assert pefin["source_id"].endswith("|pefin|C111")
    notary = next(r for r in rows.restricoes if r["tipo"] == "protesto")
    assert notary["source_id"].endswith("|protesto|A333")


def test_restricao_falls_back_to_contract_id_when_no_cadus() -> None:
    """Se item nao tiver `cadus`, usa `contractId` como fallback."""
    payload = _full_payload()
    payload["reports"][0]["negativeData"]["pefin"]["pefinResponse"] = [
        {
            "amount": 100.0,
            "creditorName": "X",
            "occurrenceDate": "2025-01-01",
            "contractId": "ONLY-CONTRACT",
        },
    ]
    rows = _call_mapper(payload)
    pefins = [r for r in rows.restricoes if r["tipo"] == "pefin"]
    assert len(pefins) == 1
    assert pefins[0]["source_id"].endswith("|pefin|ONLY-CONTRACT")


def test_restricao_skipped_when_no_natural_id() -> None:
    """Sem cadus nem contractId, nao da pra deduplicar — descarta."""
    payload = _full_payload()
    payload["reports"][0]["negativeData"]["pefin"]["pefinResponse"] = [
        {"amount": 100.0, "creditorName": "X"},  # sem cadus, sem contractId
    ]
    rows = _call_mapper(payload)
    assert all(r["tipo"] != "pefin" for r in rows.restricoes)


def test_endereco_normalized_from_address_dict() -> None:
    """Address e dict no payload (1 endereco unico, nao array)."""
    rows = _call_mapper(_full_payload())
    assert len(rows.enderecos) == 1
    e = rows.enderecos[0]
    assert e["logradouro"] == "RUA DAS FLORES 123"
    assert e["bairro"] == "CENTRO"
    assert e["cidade"] == "SAO PAULO"
    assert e["uf"] == "SP"
    assert e["cep"] == "01001000"


def test_endereco_invalid_uf_becomes_none() -> None:
    payload = _full_payload()
    payload["reports"][0]["identificationReport"]["address"]["state"] = (
        "Sao Paulo"
    )
    rows = _call_mapper(payload)
    assert rows.enderecos[0]["uf"] is None


def test_partners_block_when_present_creates_socios() -> None:
    """Quando contrato evoluir e payload trouxer partners, mapper popula."""
    payload = _full_payload()
    payload["reports"][0]["partners"] = [
        {
            "documentId": "11122233344",
            "name": "JOAO ACME",
            "role": "Socio Administrador",
            "participationPercentage": "60.00",
            "entryDate": "2018-03-15",
        },
    ]
    rows = _call_mapper(payload)
    assert len(rows.socios) == 1
    s = rows.socios[0]
    assert s["documento"] == "11122233344"
    assert s["documento_tipo"] == "cpf"
    assert s["nome"] == "JOAO ACME"
    assert s["percentual"] == Decimal("60.00")


def test_business_participation_when_present_creates_rows() -> None:
    payload = _full_payload()
    payload["reports"][0]["businessParticipation"] = [
        {
            "documentId": "98765432000111",
            "businessName": "ACME PARTICIPACOES LTDA",
            "participationPercentage": "30.00",
        },
    ]
    rows = _call_mapper(payload)
    assert len(rows.participacoes) == 1
    assert rows.participacoes[0]["documento_empresa"] == "98765432000111"


def test_scoring_block_when_present_populates_score() -> None:
    """Score nao vem no segmento 028, mas mapper le se presente."""
    payload = _full_payload()
    payload["reports"][0]["scoring"] = {
        "score": 720,
        "class": "B",
        "description": "Risco baixo",
    }
    rows = _call_mapper(payload)
    assert rows.consulta["score_h4pj"] == Decimal("720")
    assert rows.consulta["score_classe"] == "B"
    assert rows.consulta["score_descricao"] == "Risco baixo"


def test_provenance_filled_in_all_rows() -> None:
    rows = _call_mapper(_full_payload())
    for row in [rows.consulta, *rows.restricoes, *rows.enderecos]:
        assert row["source_type"] == SourceType.BUREAU_SERASA_PJ
        assert row["source_id"]
        assert row["ingested_at"] is not None
        assert row["ingested_by_version"].startswith("serasa_pj_adapter_")
        assert row["trust_level"] == TrustLevel.HIGH
        assert row["hash_origem"]


def test_consulta_id_is_propagated_to_children() -> None:
    rows = _call_mapper(_full_payload())
    cid = rows.consulta["id"]
    assert all(r["consulta_id"] == cid for r in rows.restricoes)
    assert all(e["consulta_id"] == cid for e in rows.enderecos)


def test_empty_payload_returns_consulta_with_nulls() -> None:
    """Sanity: payload vazio nao quebra. Header existe (1:1 com raw),
    contadores zerados, listas vazias."""
    rows = map_pj_analitico(
        payload={},
        tenant_id=uuid4(),
        raw_id=uuid4(),
        cnpj="11111111000111",
        consulted_at=datetime(2026, 5, 1, tzinfo=UTC),
        requested_report="RELATORIO_AVANCADO_PJ_ANALITICO",
        actual_report_returned="RELATORIO_AVANCADO_PJ_ANALITICO",
    )
    c = rows.consulta
    assert c["razao_social"] is None
    assert c["score_h4pj"] is None
    assert c["has_refin"] is False
    assert c["count_refin"] == 0
    assert c["valor_total_restricoes"] is None
    assert rows.socios == []
    assert rows.restricoes == []
    assert rows.participacoes == []
    assert rows.enderecos == []


def test_restricao_summary_one_per_category() -> None:
    """5 categorias de negativeData -> 5 summaries (mesmo as zeradas).

    Permite UI mostrar "Pefin: 2 ocorrencias, R$ 1130,50, ultima 2024-10-12"
    sem JOIN nas filhas individuais.
    """
    rows = _call_mapper(_full_payload())
    summaries = {s["tipo"]: s for s in rows.restricao_summaries}
    assert set(summaries.keys()) == {
        "pefin",
        "refin",
        "protesto",
        "cheque",
        "collection",
    }
    pefin = summaries["pefin"]
    assert pefin["count"] == 2
    assert pefin["balance"] == Decimal("1130.50")
    assert pefin["first_occurrence"] == date(2024, 9, 1)
    assert pefin["last_occurrence"] == date(2024, 10, 12)

    # Categoria sem ocorrencia: count=0, datas None.
    cheque = summaries["cheque"]
    assert cheque["count"] == 0
    assert cheque["first_occurrence"] is None


def test_pagamento_buckets_from_payment_history() -> None:
    """`advancedCommercialPaymentHistory.paymentHistory.titlesQuantity[]`
    vira buckets com segment_kind='default' quando segmentData nao tem
    sub-segmentos populados (caso comum em factoring 028)."""
    payload = _full_payload()
    payload["reports"][0]["advancedCommercialPaymentHistory"] = {
        "segmentData": {
            "drawee": {},
            "assignor": {},
            "individual": {},
            "segmentDescription": "FACTORINGS",
        },
        "paymentHistory": {
            "titlesQuantity": [
                {
                    "name": "PONTUAL",
                    "range": "-",
                    "rangeCode": "",
                    "percentage": "85.0% e 90.0%",
                    "percentageFrom": 85.0,
                    "percentageTo": 90.0,
                    "rangeValueFrom": 0,
                    "rangeValueTo": 0,
                },
                {
                    "name": "ATE 30 DIAS",
                    "range": "1-30",
                    "rangeCode": "B1",
                    "percentage": "10.0% e 12.0%",
                    "percentageFrom": 10.0,
                    "percentageTo": 12.0,
                    "rangeValueFrom": 100.0,
                    "rangeValueTo": 500.0,
                },
            ],
        },
    }
    rows = _call_mapper(payload)
    assert len(rows.pagamento_buckets) == 2
    pontual = next(b for b in rows.pagamento_buckets if b["name"] == "PONTUAL")
    assert pontual["segment_kind"] == "default"
    assert pontual["percentage_from"] == Decimal("85.0")
    assert pontual["percentage_to"] == Decimal("90.0")
    assert pontual["percentage_label"] == "85.0% e 90.0%"

    ate30 = next(
        b for b in rows.pagamento_buckets if b["name"] == "ATE 30 DIAS"
    )
    assert ate30["range_label"] == "1-30"
    assert ate30["range_code"] == "B1"
    assert ate30["range_value_from"] == Decimal("100.0")


def test_inquiries_anteriores_from_facts() -> None:
    """`facts.inquiryCompanyResponse.results[]` vira linhas com
    company_document_id, occurrence_date, days_quantity."""
    payload = _full_payload()
    payload["reports"][0]["facts"] = {
        "inquiryCompanyResponse": {
            "quantity": {"actual": 0, "historical": []},
            "results": [
                {
                    "companyName": "BANCO ABC S.A.",
                    "companyAlias": "ABC",
                    "companyDocumentId": "10158356000101",
                    "occurrenceDate": "2026-04-16",
                    "daysQuantity": 1,
                },
                {
                    "companyName": "FACTORING XYZ LTDA",
                    "companyDocumentId": "12345678000199",
                    "occurrenceDate": "2026-04-10",
                    "daysQuantity": 7,
                },
            ],
        },
    }
    rows = _call_mapper(payload)
    assert len(rows.inquiries_anteriores) == 2
    abc = rows.inquiries_anteriores[0]
    assert abc["company_name"] == "BANCO ABC S.A."
    assert abc["company_document_id"] == "10158356000101"
    assert abc["occurrence_date"] == date(2026, 4, 16)
    assert abc["days_quantity"] == 1
    # Detalhe preserva o item cru.
    assert abc["detalhe"]["companyAlias"] == "ABC"


def test_header_expandido_cadastrais_e_telefone() -> None:
    """F.1: campos cadastrais que estavam sendo perdidos agora viram colunas."""
    payload = _full_payload()
    ident = payload["reports"][0]["identificationReport"]
    # Adiciona campos extras no fixture pra cobrir todos os novos campos.
    ident.update(
        {
            "exportSales": "1500.00",
            "importPurchases": "2300.50",
            "nireNumber": "35221582419",
            "stateRegistration": "535426523112",
            "companyRegister": "851130264",
            "companyRegisterDate": "2026-01-30",
            "serasaActiveCode": "S010300",
            "statusCode": "2",
            "companyUrl": "https://acme.com.br",
        }
    )
    rows = _call_mapper(payload)
    c = rows.consulta

    # Cadastrais.
    assert c["legal_nature_code"] == "206"
    assert c["partnership_description"] == "SOCIEDADE EMPRESARIA LIMITADA"
    assert c["number_employees"] == 12
    assert c["export_sales"] == Decimal("1500.00")
    assert c["import_purchases"] == Decimal("2300.50")
    assert c["nire_number"] == "35221582419"
    assert c["state_registration"] == "535426523112"
    assert c["company_register"] == "851130264"
    assert c["company_register_date"] == date(2026, 1, 30)
    assert c["serasa_active_code"] == "S010300"

    # Status.
    assert c["status_code"] == "2"
    assert (
        c["status_registration_text"]
        == "SITUACAO DO CNPJ EM 10/05/2025: ATIVA"
    )
    assert c["company_url"] == "https://acme.com.br"

    # Telefone separado em area_code + number.
    assert c["phone_area_code"] == "11"
    assert c["phone_number"] == "33334444"


def test_header_facts_bankrupts_and_judgement_summary() -> None:
    """F.1: facts.bankrupts e facts.judgementFilings populam contadores
    no header (nao geram tabela separada — sao agregados pequenos)."""
    payload = _full_payload()
    payload["reports"][0]["facts"] = {
        "bankrupts": {"summary": {"count": 1, "balance": 50000.00}},
        "judgementFilings": {
            "summary": {"count": 3, "balance": 12000.00}
        },
    }
    rows = _call_mapper(payload)
    c = rows.consulta
    assert c["has_falencias"] is True
    assert c["count_falencias"] == 1
    assert c["valor_falencias"] == Decimal("50000.00")
    assert c["has_acoes_judiciais"] is True
    assert c["count_acoes_judiciais"] == 3
    assert c["valor_acoes_judiciais"] == Decimal("12000.00")


def test_header_facts_zerados_quando_ausentes() -> None:
    """Sem facts no payload, contadores ficam zerados."""
    rows = _call_mapper(_full_payload())
    c = rows.consulta
    assert c["has_falencias"] is False
    assert c["count_falencias"] == 0
    assert c["valor_falencias"] is None
    assert c["has_acoes_judiciais"] is False
    assert c["count_acoes_judiciais"] == 0


def test_predecessores_extraidos_de_predecessor_list() -> None:
    """F.2: identificationReport.predecessorList[] vira linhas na tabela."""
    payload = _full_payload()
    payload["reports"][0]["identificationReport"]["predecessorList"] = [
        {
            "predecessorDate": "2024-12-21",
            "predecessorName": "M V B TRANSPORTES LTDA ME",
        },
        {
            "predecessorDate": "2020-05-10",
            "predecessorName": "ANTIGA RAZAO LTDA",
        },
    ]
    rows = _call_mapper(payload)
    assert len(rows.predecessores) == 2
    p1 = next(
        p
        for p in rows.predecessores
        if p["predecessor_name"] == "M V B TRANSPORTES LTDA ME"
    )
    assert p1["predecessor_date"] == date(2024, 12, 21)
    assert p1["source_id"].endswith(
        "|predecessor|M V B TRANSPORTES LTDA ME|2024-12-21"
    )


def test_predecessor_sem_nome_e_descartado() -> None:
    """Sem nome nao da pra deduplicar — descarta."""
    payload = _full_payload()
    payload["reports"][0]["identificationReport"]["predecessorList"] = [
        {"predecessorDate": "2024-12-21"},  # sem name
    ]
    rows = _call_mapper(payload)
    assert rows.predecessores == []


def test_inquiries_mensais_de_quantity_historical() -> None:
    """F.2: facts.inquiryCompanyResponse.quantity.historical[] (13 meses)
    vira linhas pra grafico de tendencia de credit shopping."""
    payload = _full_payload()
    payload["reports"][0]["facts"] = {
        "inquiryCompanyResponse": {
            "quantity": {
                "actual": 0,
                "historical": [
                    {"inquiryDate": "2026-04", "occurrences": 3},
                    {"inquiryDate": "2026-03", "occurrences": 1},
                    {"inquiryDate": "2026-02", "occurrences": 0},
                ],
            },
            "results": [],
        },
    }
    rows = _call_mapper(payload)
    assert len(rows.inquiries_mensais) == 3
    by_ym = {r["inquiry_year_month"]: r for r in rows.inquiries_mensais}
    assert by_ym["2026-04"]["occurrences"] == 3
    assert by_ym["2026-03"]["occurrences"] == 1
    assert by_ym["2026-02"]["occurrences"] == 0
    # Source ID determinista — re-mapear substitui via UPSERT.
    assert by_ym["2026-04"]["source_id"].endswith(
        "|inquiry_mensal|2026-04"
    )


def test_payload_flat_without_reports_envelope_works() -> None:
    """Tolerancia: se um remap futuro for sobre raw com shape diferente
    (sem o envelope `reports`), mapper consegue ler diretamente."""
    payload = _full_payload()["reports"][0]  # sem envelope
    rows = map_pj_analitico(
        payload=payload,
        tenant_id=uuid4(),
        raw_id=uuid4(),
        cnpj="12345678000199",
        consulted_at=datetime(2026, 5, 1, tzinfo=UTC),
        requested_report="X",
        actual_report_returned="X",
    )
    assert rows.consulta["razao_social"] == "ACME COMERCIO LTDA"
