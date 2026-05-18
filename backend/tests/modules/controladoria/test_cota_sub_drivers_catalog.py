"""Catalogo dos 11 drivers da Cota Sub — sanidade + cross-ref."""

from __future__ import annotations

from app.modules.controladoria.services.cota_sub_drivers import (
    COTA_SUB_DRIVERS,
    COTA_SUB_DRIVERS_BY_NAME,
    get_driver_spec,
)
from app.modules.integracoes.adapters.admin.qitech.endpoint_catalog import (
    QITECH_ENDPOINTS_BY_NAME,
)
from app.shared.metric_catalog import MetricCategory
from app.warehouse.silver_catalog import SILVER_CATALOG_BY_TABLE


def test_has_11_drivers():
    """Memo `project_cota_sub_metodo_gestor` define 11 categorias do gestor."""
    assert len(COTA_SUB_DRIVERS) == 11


def test_all_drivers_are_driver_category():
    for d in COTA_SUB_DRIVERS:
        assert d.category == MetricCategory.DRIVER, (
            f"{d.name}: category={d.category} (esperado DRIVER)"
        )


def test_all_drivers_belong_to_controladoria():
    for d in COTA_SUB_DRIVERS:
        assert d.module_code == "controladoria"


def test_driver_names_follow_convention():
    """Convencao: `cota_sub.driver.<nome>`."""
    for d in COTA_SUB_DRIVERS:
        assert d.name.startswith("cota_sub.driver."), (
            f"{d.name} fora da convencao"
        )


def test_driver_names_unique():
    names = [d.name for d in COTA_SUB_DRIVERS]
    assert len(names) == len(set(names))


def test_global_ids_unique():
    ids = [d.global_id for d in COTA_SUB_DRIVERS]
    assert len(ids) == len(set(ids))


def test_all_silver_tables_exist_in_silver_catalog():
    """Cada driver referencia silvers que existem no SILVER_CATALOG."""
    errs = []
    for d in COTA_SUB_DRIVERS:
        for tbl in d.silver_tables_required:
            if tbl not in SILVER_CATALOG_BY_TABLE:
                errs.append(f"{d.name}: silver {tbl!r} nao existe")
    assert errs == [], "\n".join(errs)


def test_all_endpoints_exist_in_qitech_catalog():
    """Cada driver referencia endpoints que existem no QITECH_ENDPOINTS."""
    errs = []
    for d in COTA_SUB_DRIVERS:
        for ep_id in d.endpoints_required:
            ep_short = ep_id.replace("qitech.", "", 1)
            if ep_short not in QITECH_ENDPOINTS_BY_NAME:
                errs.append(f"{d.name}: endpoint {ep_id!r} nao existe")
    assert errs == [], "\n".join(errs)


def test_silver_endpoint_coherence_per_driver():
    """Se driver requer silver X, deve requerer todos os endpoints que alimentam X."""
    from app.warehouse.silver_catalog import get_silver_spec

    errs = []
    for d in COTA_SUB_DRIVERS:
        for tbl in d.silver_tables_required:
            silver = get_silver_spec(tbl)
            assert silver is not None
            for ep_id in silver.fed_by_endpoints:
                if ep_id not in d.endpoints_required:
                    errs.append(
                        f"{d.name}: silver {tbl} alimentado por {ep_id} mas "
                        f"driver nao declara este endpoint em endpoints_required"
                    )
    assert errs == [], "\n".join(errs)


def test_canonical_drivers_present():
    """Os 11 nomes especificos do metodo do gestor existem no catalogo."""
    expected = {
        "cota_sub.driver.pdd",
        "cota_sub.driver.apropriacao_dc",
        "cota_sub.driver.apropriacao_despesas",
        "cota_sub.driver.fundos_di",
        "cota_sub.driver.compromissada",
        "cota_sub.driver.titulos_publicos",
        "cota_sub.driver.senior",
        "cota_sub.driver.mezanino",
        "cota_sub.driver.tesouraria",
        "cota_sub.driver.op_estruturadas",
        "cota_sub.driver.outros_ativos",
    }
    actual = set(COTA_SUB_DRIVERS_BY_NAME.keys())
    assert actual == expected, f"Diff: missing={expected-actual} extra={actual-expected}"


def test_get_driver_spec_accepts_short_name():
    spec = get_driver_spec("cota_sub.driver.pdd")
    assert spec is not None
    assert spec.name == "cota_sub.driver.pdd"


def test_get_driver_spec_accepts_global_id():
    spec = get_driver_spec("controladoria.cota_sub.driver.pdd")
    assert spec is not None
    assert spec.name == "cota_sub.driver.pdd"


def test_get_driver_spec_returns_none_when_unknown():
    assert get_driver_spec("cota_sub.driver.inexistente") is None
    assert get_driver_spec("controladoria.foo.bar") is None
