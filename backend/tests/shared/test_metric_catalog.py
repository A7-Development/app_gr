"""Sanidade do primitivo MetricSpec — Fase 3a do refactor de proveniencia."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.shared.metric_catalog import (
    MetricCategory,
    MetricSpec,
    _looks_like_semver,
    _looks_like_snake_atom,
)

# ─────────────────────────────────────────────────────────────────────────────
# Construcao valida
# ─────────────────────────────────────────────────────────────────────────────


def _valid_spec(**overrides):
    """Helper: spec valido base, sobreescreve campos por kwarg."""
    base = dict(
        module_code="controladoria",
        name="cota_sub.driver.pdd",
        label="PDD",
        description="Variacao da provisao de devedores duvidosos.",
        category=MetricCategory.DRIVER,
        formula_description="-d valor_pdd",
        silver_tables_required=("wh_estoque_recebivel",),
        endpoints_required=("qitech.market.fidc_estoque",),
        version="1.0.0",
    )
    base.update(overrides)
    return MetricSpec(**base)


def test_construct_valid():
    spec = _valid_spec()
    assert spec.global_id == "controladoria.cota_sub.driver.pdd"
    assert spec.category == MetricCategory.DRIVER


def test_global_id_format():
    spec = _valid_spec(module_code="bi", name="vop.acumulado_mes")
    assert spec.global_id == "bi.vop.acumulado_mes"


def test_is_frozen():
    spec = _valid_spec()
    with pytest.raises(FrozenInstanceError):
        spec.label = "nope"  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# Validacoes — module_code
# ─────────────────────────────────────────────────────────────────────────────


def test_rejects_empty_module_code():
    with pytest.raises(ValueError, match="module_code must be"):
        _valid_spec(module_code="")


def test_rejects_uppercase_module_code():
    with pytest.raises(ValueError, match="module_code must be"):
        _valid_spec(module_code="Controladoria")


def test_rejects_module_code_with_dot():
    with pytest.raises(ValueError, match="module_code must be"):
        _valid_spec(module_code="modulo.sub")


# ─────────────────────────────────────────────────────────────────────────────
# Validacoes — name
# ─────────────────────────────────────────────────────────────────────────────


def test_rejects_empty_name():
    with pytest.raises(ValueError, match="name cannot be empty"):
        _valid_spec(name="")


def test_rejects_name_without_dot():
    with pytest.raises(ValueError, match="at least 2 atoms"):
        _valid_spec(name="pdd")


def test_rejects_uppercase_atom_in_name():
    with pytest.raises(ValueError, match="snake_case"):
        _valid_spec(name="cota_sub.Driver.pdd")


def test_rejects_kebab_in_name():
    with pytest.raises(ValueError, match="snake_case"):
        _valid_spec(name="cota-sub.driver.pdd")


# ─────────────────────────────────────────────────────────────────────────────
# Validacoes — version
# ─────────────────────────────────────────────────────────────────────────────


def test_rejects_invalid_semver():
    with pytest.raises(ValueError, match="semver"):
        _valid_spec(version="v1")


def test_rejects_partial_semver():
    with pytest.raises(ValueError, match="semver"):
        _valid_spec(version="1.0")


def test_rejects_prerelease_semver():
    with pytest.raises(ValueError, match="semver"):
        _valid_spec(version="1.0.0-rc1")


def test_accepts_double_digit_semver():
    spec = _valid_spec(version="10.20.30")
    assert spec.version == "10.20.30"


# ─────────────────────────────────────────────────────────────────────────────
# Validacoes — endpoints_required
# ─────────────────────────────────────────────────────────────────────────────


def test_rejects_endpoint_without_dot():
    with pytest.raises(ValueError, match="endpoints_required"):
        _valid_spec(endpoints_required=("xpto",))


def test_rejects_empty_endpoint_string():
    with pytest.raises(ValueError, match="endpoints_required"):
        _valid_spec(endpoints_required=("",))


def test_accepts_multiple_endpoints():
    spec = _valid_spec(
        endpoints_required=(
            "qitech.market.fidc_estoque",
            "qitech.custodia.aquisicao_consolidada",
            "qitech.custodia.liquidados_baixados",
        )
    )
    assert len(spec.endpoints_required) == 3


# ─────────────────────────────────────────────────────────────────────────────
# Validacoes — silver_tables_required
# ─────────────────────────────────────────────────────────────────────────────


def test_rejects_empty_silver_table_string():
    with pytest.raises(ValueError, match="silver_tables_required"):
        _valid_spec(silver_tables_required=("",))


def test_accepts_empty_silver_tuple():
    """Metrica sem silver e valida (ex.: constante, output de IA)."""
    spec = _valid_spec(silver_tables_required=())
    assert spec.silver_tables_required == ()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def test_looks_like_snake_atom():
    assert _looks_like_snake_atom("controladoria")
    assert _looks_like_snake_atom("v2")
    assert _looks_like_snake_atom("cota_sub")
    assert not _looks_like_snake_atom("")
    assert not _looks_like_snake_atom("Cota")
    assert not _looks_like_snake_atom("1cota")
    assert not _looks_like_snake_atom("cota.sub")
    assert not _looks_like_snake_atom("cota-sub")


def test_looks_like_semver():
    assert _looks_like_semver("1.0.0")
    assert _looks_like_semver("0.1.0")
    assert _looks_like_semver("10.20.30")
    assert not _looks_like_semver("1.0")
    assert not _looks_like_semver("1.0.0.0")
    assert not _looks_like_semver("v1.0.0")
    assert not _looks_like_semver("1.0.0-rc1")
