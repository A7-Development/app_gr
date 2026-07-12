"""Sanidade do primitivo SilverSpec + catalogo QiTech-alimentado."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.shared.silver_catalog import SilverSpec, _is_snake_case
from app.warehouse.silver_catalog import (
    SILVER_CATALOG,
    SILVER_CATALOG_BY_TABLE,
    get_silver_spec,
    silvers_fed_by_endpoint,
)

# ─────────────────────────────────────────────────────────────────────────────
# Primitivo
# ─────────────────────────────────────────────────────────────────────────────


def _valid(**overrides):
    base = dict(
        table_name="wh_estoque_recebivel",
        label="Estoque",
        description="...",
        fed_by_endpoints=("qitech.market.fidc_estoque",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_referencia",
    )
    base.update(overrides)
    return SilverSpec(**base)


def test_construct_valid():
    spec = _valid()
    assert spec.table_name == "wh_estoque_recebivel"
    assert spec.tenant_scoped is True


def test_is_frozen():
    spec = _valid()
    with pytest.raises(FrozenInstanceError):
        spec.label = "nope"  # type: ignore[misc]


def test_rejects_missing_wh_prefix():
    with pytest.raises(ValueError, match="wh_"):
        _valid(table_name="estoque")


def test_rejects_uppercase_table_name():
    with pytest.raises(ValueError, match="snake_case"):
        _valid(table_name="wh_Estoque")


def test_rejects_empty_primary_key():
    with pytest.raises(ValueError, match="primary_key cannot be empty"):
        _valid(primary_key=())


def test_rejects_empty_pk_column():
    with pytest.raises(ValueError, match="primary_key"):
        _valid(primary_key=("",))


def test_rejects_temporal_without_date_column():
    with pytest.raises(ValueError, match="temporal=True requires"):
        _valid(temporal=True, date_column=None)


def test_rejects_date_column_without_temporal():
    with pytest.raises(ValueError, match="incoherent"):
        _valid(temporal=False, date_column="data_x")


def test_rejects_invalid_endpoint_id():
    with pytest.raises(ValueError, match="fed_by_endpoints"):
        _valid(fed_by_endpoints=("xpto",))


def test_accepts_empty_fed_by_endpoints():
    """Silver derivado (computado de outro silver) e valido."""
    spec = _valid(fed_by_endpoints=())
    assert spec.fed_by_endpoints == ()


def test_is_snake_case_helper():
    assert _is_snake_case("wh_estoque_recebivel")
    assert _is_snake_case("wh_x1_y2")
    assert not _is_snake_case("")
    assert not _is_snake_case("wh_X")
    assert not _is_snake_case("wh-estoque")


# ─────────────────────────────────────────────────────────────────────────────
# Catalogo QiTech-alimentado
# ─────────────────────────────────────────────────────────────────────────────


def test_silver_catalog_has_17_entries():
    """1:1 com endpoints QiTech (17)."""
    assert len(SILVER_CATALOG) == 17


def test_silver_catalog_table_names_unique():
    names = [s.table_name for s in SILVER_CATALOG]
    assert len(names) == len(set(names))


def test_silver_catalog_index_matches():
    assert len(SILVER_CATALOG_BY_TABLE) == len(SILVER_CATALOG)
    for s in SILVER_CATALOG:
        assert SILVER_CATALOG_BY_TABLE[s.table_name] is s


def test_silver_catalog_cross_references_endpoint_catalog():
    """Cada canonical_table do EndpointSpec QiTech tem SilverSpec correspondente."""
    from app.modules.integracoes.adapters.admin.qitech.endpoint_catalog import (
        QITECH_ENDPOINTS,
    )

    endpoint_tables = {ep.canonical_table for ep in QITECH_ENDPOINTS}
    silver_tables = {s.table_name for s in SILVER_CATALOG}
    missing = endpoint_tables - silver_tables
    extra = silver_tables - endpoint_tables
    assert missing == set(), f"Endpoints sem SilverSpec: {missing}"
    assert extra == set(), f"Silvers nao referenciados por endpoint: {extra}"


def test_silver_catalog_endpoint_global_ids_resolve():
    """Cada fed_by_endpoints aponta pra global_id que existe."""
    from app.modules.integracoes.adapters.admin.qitech.endpoint_catalog import (
        QITECH_ENDPOINTS,
    )

    valid_global_ids = {ep.global_id for ep in QITECH_ENDPOINTS}
    errs = []
    for s in SILVER_CATALOG:
        for ep_id in s.fed_by_endpoints:
            if ep_id not in valid_global_ids:
                errs.append(f"{s.table_name}: ref a {ep_id!r} nao existe")
    assert errs == [], "\n".join(errs)


def test_get_silver_spec_returns_none_when_unknown():
    assert get_silver_spec("wh_inexistente") is None


def test_silvers_fed_by_endpoint_reverse_lookup():
    """Reverse lookup: endpoint → silvers downstream."""
    silvers = silvers_fed_by_endpoint("qitech.market.fidc_estoque")
    assert len(silvers) == 1
    assert silvers[0].table_name == "wh_estoque_recebivel"


def test_silvers_fed_by_unknown_endpoint_returns_empty():
    silvers = silvers_fed_by_endpoint("xpto.market.foo")
    assert silvers == ()
