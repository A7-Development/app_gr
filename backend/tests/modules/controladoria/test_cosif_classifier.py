"""Tests do classifier COSIF — cascata override -> rule -> pendente.

Mocks dos caches (sem DB) — valida apenas a lógica de cascata e
serializacao do CosifResolution.
"""

from __future__ import annotations

from uuid import uuid4

from app.modules.controladoria.services.cosif.classifier import (
    CosifResolution,
    _CachedOverride,
    _CachedRule,
    classify,
)


def _rule(
    silver: str, predicate: dict, cosif: str | None, *,
    priority: int = 10, confidence: str = "alta",
    rule_id_humano: str = "test_rule",
    classe: str | None = None,
) -> _CachedRule:
    return _CachedRule(
        id=uuid4(),
        silver_origin=silver,
        predicate=predicate,
        cosif_codigo=cosif,
        classe_sr_mez_sub=classe,
        priority=priority,
        confidence=confidence,
        rule_id_humano=rule_id_humano,
    )


def _override(cosif: str, classe: str | None = None) -> _CachedOverride:
    return _CachedOverride(id=uuid4(), cosif_override=cosif, classe_sr_mez_sub=classe)


# ─── Override wins ───────────────────────────────────────────────────────────

def test_override_wins_over_rule() -> None:
    rules = {
        "wh_x": [_rule("wh_x", {"all": []}, "1.0", rule_id_humano="rule_default")]
    }
    overrides = {("wh_x", "REALIAVE"): _override("9.9.9")}
    res = classify("wh_x", {"codigo": "REALIAVE"}, rules, overrides)
    assert res.cosif == "9.9.9"
    assert res.source == "override"
    assert res.confidence == "alta"


def test_override_lookup_uppercases_identificador() -> None:
    """Identificador do row normalizado para upper antes do lookup."""
    overrides = {("wh_x", "BRADESCO"): _override("1.2.3")}
    res = classify("wh_x", {"codigo": "bradesco"}, {}, overrides)
    assert res.cosif == "1.2.3"
    assert res.source == "override"


def test_override_uses_k_field_as_fallback() -> None:
    """Quando `codigo` nao existe, classify usa `k`."""
    overrides = {("wh_x", "FOO"): _override("1.2.3")}
    res = classify("wh_x", {"k": "FOO"}, {}, overrides)
    assert res.source == "override"


# ─── Rule cascade ────────────────────────────────────────────────────────────

def test_first_matching_rule_wins() -> None:
    """Lista assumida ordenada por priority desc — primeira match vence."""
    rules = {
        "wh_x": [
            _rule("wh_x",
                  {"field": "papel", "op": "starts_with", "value": "SR"},
                  "6.1.1", priority=100, rule_id_humano="rule_sr"),
            _rule("wh_x",
                  {"all": []},
                  "9.9.9", priority=10, rule_id_humano="rule_fallback"),
        ]
    }
    res = classify("wh_x", {"papel": "SRP", "codigo": "abc"}, rules, {})
    assert res.cosif == "6.1.1"
    assert res.source == "rule:rule_sr"


def test_falls_back_when_no_rule_matches_predicate() -> None:
    """Se primeira regra nao matcha, tenta a proxima."""
    rules = {
        "wh_x": [
            _rule("wh_x",
                  {"field": "papel", "op": "starts_with", "value": "ZZ"},
                  "1.1", priority=100, rule_id_humano="zz_only"),
            _rule("wh_x",
                  {"all": []},
                  "9.9", priority=10, rule_id_humano="fallback"),
        ]
    }
    res = classify("wh_x", {"papel": "AAA"}, rules, {})
    assert res.cosif == "9.9"
    assert res.source == "rule:fallback"


def test_rule_with_null_cosif_returns_none() -> None:
    """Regra de compensacao (rf.contrapartida_compensacao) retorna cosif None."""
    rules = {
        "wh_x": [
            _rule("wh_x",
                  {"all": []},
                  None, classe="compensacao",
                  rule_id_humano="compensacao_rule"),
        ]
    }
    res = classify("wh_x", {"papel": "SRP"}, rules, {})
    assert res.cosif is None
    assert res.source == "rule:compensacao_rule"
    assert res.classe_sr_mez_sub == "compensacao"


# ─── Pendente fallback ───────────────────────────────────────────────────────

def test_returns_pendente_when_no_rules() -> None:
    """Sem regras nem override — fica pendente."""
    res = classify("wh_x", {"codigo": "FOO"}, {}, {})
    assert res.cosif is None
    assert res.source == "pendente"
    assert res.confidence == "baixa"


def test_returns_pendente_when_no_rule_matches() -> None:
    """Tem regras mas nenhuma matcha — fica pendente."""
    rules = {
        "wh_x": [
            _rule("wh_x",
                  {"field": "papel", "op": "eq", "value": "ESPECIFICO"},
                  "1.1.1", rule_id_humano="only_especifico"),
        ]
    }
    res = classify("wh_x", {"papel": "OUTRO"}, rules, {})
    assert res.source == "pendente"


# ─── Classe Sr/Mez/Sub ───────────────────────────────────────────────────────

def test_classe_from_rule_is_propagated() -> None:
    rules = {
        "wh_x": [
            _rule("wh_x", {"all": []}, "6.1.1",
                  classe="senior", rule_id_humano="r_sr"),
        ]
    }
    res = classify("wh_x", {"codigo": "X"}, rules, {})
    assert res.classe_sr_mez_sub == "senior"


def test_classe_from_override_is_propagated() -> None:
    overrides = {("wh_x", "MEU_PAPEL"): _override("6.1.1", classe="mezanino")}
    res = classify("wh_x", {"codigo": "MEU_PAPEL"}, {}, overrides)
    assert res.classe_sr_mez_sub == "mezanino"
