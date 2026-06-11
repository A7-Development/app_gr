"""Regra serasa_liminar_v1 — deteccao de supressao judicial.

Padrao validado em prod 2026-06-10 (100% match com flag Liminar do
Bitfin): liminar judicial => `negativeSummary.message == "NADA CONSTA"`
explicito; empresa genuinamente limpa vem SEM message.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.modules.integracoes.adapters.bureau.serasa_pj.liminar import (
    MSG_AUSENTE,
    MSG_DESCONHECIDA,
    MSG_NADA_CONSTA,
    MSG_RECUPERACAO_JUDICIAL,
    MSG_VAZIA,
    classify_negative_summary_message,
    extract_negative_summary_message,
    is_suspeita_liminar,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.mappers.pj_analitico import (
    map_pj_analitico,
)

# ─── Unidade: extracao + classificacao ─────────────────────────────────────


def test_extract_message_absent_block() -> None:
    assert extract_negative_summary_message({}) is None


def test_extract_message_block_without_key() -> None:
    assert extract_negative_summary_message({"negativeSummary": {}}) is None


def test_extract_message_empty_string() -> None:
    report = {"negativeSummary": {"message": "  "}}
    assert extract_negative_summary_message(report) == ""


def test_extract_message_nada_consta() -> None:
    report = {"negativeSummary": {"message": "NADA CONSTA"}}
    assert extract_negative_summary_message(report) == "NADA CONSTA"


def test_is_suspeita_liminar_only_for_nada_consta() -> None:
    assert is_suspeita_liminar("NADA CONSTA") is True
    assert is_suspeita_liminar(None) is False
    assert is_suspeita_liminar("") is False
    assert is_suspeita_liminar("EM RECUPERACAO JUDICIAL PROCESSO 123") is False


def test_classify_covers_known_universe() -> None:
    assert classify_negative_summary_message(None) == MSG_AUSENTE
    assert classify_negative_summary_message("") == MSG_VAZIA
    assert classify_negative_summary_message("NADA CONSTA") == MSG_NADA_CONSTA
    assert (
        classify_negative_summary_message(
            "EM RECUPERACAO JUDICIAL PROCESSO 00211200820238160185"
        )
        == MSG_RECUPERACAO_JUDICIAL
    )


def test_classify_unknown_value_flags_desconhecida() -> None:
    # Valor nunca visto => sentinela F2 trata como possivel mudanca de
    # comportamento da Serasa.
    assert (
        classify_negative_summary_message("INFORMACOES SUSPENSAS")
        == MSG_DESCONHECIDA
    )


# ─── Integracao: mapper popula o header ────────────────────────────────────


def _payload(negative_summary: dict | None) -> dict:
    report: dict = {
        "reportName": "RELATORIO_AVANCADO_PJ_ANALITICO",
        "identificationReport": {"companyName": "ACME LTDA"},
        "negativeData": {
            "pefin": {"summary": {"count": 0, "balance": 0.0}},
        },
        "facts": {},
    }
    if negative_summary is not None:
        report["negativeSummary"] = negative_summary
    return {"reports": [report]}


def _map(payload: dict):
    return map_pj_analitico(
        payload=payload,
        tenant_id=uuid4(),
        raw_id=uuid4(),
        cnpj="12345678000199",
        consulted_at=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        requested_report="RELATORIO_AVANCADO_PJ_ANALITICO",
        actual_report_returned="RELATORIO_AVANCADO_PJ_ANALITICO",
    )


def test_mapper_flags_suspeita_liminar_on_nada_consta() -> None:
    rows = _map(_payload({"message": "NADA CONSTA"}))
    assert rows.consulta["negative_summary_message"] == "NADA CONSTA"
    assert rows.consulta["suspeita_liminar"] is True


def test_mapper_clean_company_without_message_not_flagged() -> None:
    rows = _map(_payload({}))
    assert rows.consulta["negative_summary_message"] is None
    assert rows.consulta["suspeita_liminar"] is False


def test_mapper_absent_block_not_flagged() -> None:
    rows = _map(_payload(None))
    assert rows.consulta["negative_summary_message"] is None
    assert rows.consulta["suspeita_liminar"] is False


def test_mapper_rj_message_preserved_but_not_flagged() -> None:
    msg = "EM RECUPERACAO JUDICIAL PROCESSO 00211200820238160185"
    rows = _map(_payload({"message": msg}))
    assert rows.consulta["negative_summary_message"] == msg
    assert rows.consulta["suspeita_liminar"] is False
