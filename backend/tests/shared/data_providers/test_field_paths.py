"""Unit tests for field_paths (extract_by_path + flatten_paths). Pure.

Run: pytest backend/tests/shared/data_providers/test_field_paths.py --noconftest
"""

from __future__ import annotations

from app.shared.data_providers.field_paths import extract_by_path, flatten_paths

PAYLOAD = {
    "TaxIdStatus": "ATIVA",
    "LegalNature": {"Code": "2062", "Activity": "SOCIEDADE EMPRESARIA LIMITADA"},
    "Activities": [
        {"Code": "8220200", "IsMain": True, "Activity": "TELEATENDIMENTO"},
        {"Code": "4619200", "IsMain": False, "Activity": "REPRESENTANTES"},
    ],
    "AdditionalOutputData": {"CapitalRS": "250755.00"},
}


def test_extract_scalar():
    assert extract_by_path(PAYLOAD, "TaxIdStatus") == "ATIVA"


def test_extract_nested():
    assert extract_by_path(PAYLOAD, "LegalNature.Activity") == "SOCIEDADE EMPRESARIA LIMITADA"
    assert extract_by_path(PAYLOAD, "AdditionalOutputData.CapitalRS") == "250755.00"


def test_extract_array_field():
    assert extract_by_path(PAYLOAD, "Activities[].Code") == ["8220200", "4619200"]
    assert extract_by_path(PAYLOAD, "Activities[].IsMain") == [True, False]


def test_extract_missing():
    assert extract_by_path(PAYLOAD, "Nope") is None
    assert extract_by_path(PAYLOAD, "LegalNature.Nope") is None
    assert extract_by_path(PAYLOAD, "Nope[].X") is None


def test_flatten_paths():
    paths = flatten_paths(PAYLOAD)
    assert "TaxIdStatus" in paths
    assert "LegalNature.Code" in paths
    assert "LegalNature.Activity" in paths
    assert "Activities[].Code" in paths
    assert "Activities[].Activity" in paths
    assert "Activities[].IsMain" in paths
    assert "AdditionalOutputData.CapitalRS" in paths
    # não enumera contêineres intermediários
    assert "LegalNature" not in paths
    assert "Activities" not in paths


def test_new_field_detection():
    catalogued = {"TaxIdStatus", "LegalNature.Activity", "Activities[].Code"}
    novos = flatten_paths(PAYLOAD) - catalogued
    assert "LegalNature.Code" in novos
    assert "Activities[].IsMain" in novos
    assert "TaxIdStatus" not in novos
