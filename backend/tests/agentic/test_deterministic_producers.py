"""Unit tests for deterministic producers (Passo 2-A). Pure — no DB.

pytest tests/agentic/test_deterministic_producers.py --noconftest
"""

from __future__ import annotations

from app.agentic.playbooks.schemas.deterministic_producers import cadastral_card_to_section
from app.agentic.playbooks.schemas.section_descriptor import FichaBlock


def _card() -> dict:
    return {
        "encontrado": True,
        "enriquecido": True,
        "cnpj": "02379828000128",
        "campos": [
            {"field_path": "razao_social", "label": "Razão social", "valor": "ACTION LINE LTDA", "novo": False},
            {"field_path": "situacao", "label": "Situação", "valor": "ATIVA", "novo": False},
            {"field_path": "cnaes", "label": "CNAEs", "valor": ["8220200", "8211300"], "novo": False},
            {"field_path": "mei", "label": "MEI", "valor": False, "novo": True},
            {"field_path": "vazio", "label": "Vazio", "valor": None, "novo": False},
        ],
    }


def test_cadastral_card_builds_ficha() -> None:
    sec = cadastral_card_to_section(_card(), station_id="dados_basicos")
    assert sec is not None
    assert sec.station_id == "dados_basicos"
    assert sec.id == "det-dados_basicos"
    assert len(sec.blocks) == 1
    ficha = sec.blocks[0]
    assert isinstance(ficha, FichaBlock)
    # campo None é pulado -> 4 de 5
    assert len(ficha.campos) == 4
    labels = [c.label for c in ficha.campos]
    assert "Razão social" in labels and "Vazio" not in labels
    # lista coerida + bool coerido
    cnaes = next(c for c in ficha.campos if c.label == "CNAEs")
    assert cnaes.valor == "8220200, 8211300"
    mei = next(c for c in ficha.campos if c.label == "MEI")
    assert mei.valor == "Não"
    # proveniencia = fonte externa
    assert ficha.provenance is not None and ficha.provenance.origin == "fonte"


def test_cadastral_not_found_returns_none() -> None:
    assert cadastral_card_to_section({"encontrado": False}, "x") is None
    assert cadastral_card_to_section({}, "x") is None
    # só campos vazios -> None
    assert cadastral_card_to_section(
        {"encontrado": True, "campos": [{"label": "X", "valor": None}]}, "x"
    ) is None
