"""Compute functions dos 11 drivers da Cota Sub — sanidade estrutural.

Testes sem banco (smoke do dispatcher + DriverResult shape). Validacao
funcional com dado real fica pra teste de integracao separado contra
fixture de REALINVEST 13/05/2026 (Task #20 do plano, Fase 4).
"""

from __future__ import annotations

import inspect
from decimal import Decimal

from app.modules.controladoria.services.cota_sub_drivers import (
    COMPUTE_FNS,
    COTA_SUB_DRIVERS,
    DriverResult,
    Evidence,
    compute_drivers,
)
from app.modules.controladoria.services.cota_sub_drivers.compute import (
    CotaSubDriversComputation,
    ComputeFn,
)
from app.modules.controladoria.schemas.cota_sub import (
    DriverResultOut,
    VariacaoDiariaResponse,
)


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────


def test_compute_fns_cobre_todos_os_drivers():
    """Cada MetricSpec do catalog tem compute_fn registrada."""
    missing = [d.name for d in COTA_SUB_DRIVERS if d.name not in COMPUTE_FNS]
    assert missing == [], f"Drivers sem compute_fn: {missing}"


def test_compute_fns_nao_tem_chave_extra():
    """Nao tem compute_fn registrada pra driver que nao existe no catalog."""
    catalog_names = {d.name for d in COTA_SUB_DRIVERS}
    extra = [name for name in COMPUTE_FNS if name not in catalog_names]
    assert extra == [], f"Compute_fns sem driver no catalog: {extra}"


def test_compute_fns_count_eh_11():
    assert len(COMPUTE_FNS) == 11


def test_todas_compute_fns_sao_async():
    """Toda compute_fn deve ser corotina (async def)."""
    not_async = [
        name for name, fn in COMPUTE_FNS.items()
        if not inspect.iscoroutinefunction(fn)
    ]
    assert not_async == [], f"Funcoes nao-async: {not_async}"


def test_todas_compute_fns_tem_7_parametros():
    """Assinatura uniforme: (db, tenant_id, ua_id, fundo_doc, ua_nome, d_prev, d0)."""
    errs = []
    for name, fn in COMPUTE_FNS.items():
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        if len(params) != 7:
            errs.append(f"{name}: {len(params)} params (esperado 7): {params}")
    assert errs == [], "\n".join(errs)


# ─────────────────────────────────────────────────────────────────────────────
# DriverResult shape
# ─────────────────────────────────────────────────────────────────────────────


def test_driver_result_has_expected_fields():
    expected = {
        "metric_global_id",
        "label",
        "formula_description",
        "valor_brl",
        "valor_d_prev",
        "valor_d0",
        "evidencias",
        "endpoints_required",
        "indeterminado_por_dado",
        "motivo_indeterminado",
        "endpoints_unavailable",
        # Fase 4b (2026-05-18): evidencias especializadas por driver. Cada
        # driver popula 0-1 campo; demais ficam vazios. Quando o numero
        # crescer, refactor pra discriminated union (kind="pdd"|"mtm"|...).
        "pdd_evidencias",
        "mtm_evidencias",
        "cpr_evidencias",
        "remuneracao_evidencias",
        "movimento_carteira_evidencias",
    }
    actual = set(DriverResult.__dataclass_fields__.keys())
    assert actual == expected, f"Diff: missing={expected-actual} extra={actual-expected}"


def test_driver_result_eh_frozen():
    from dataclasses import FrozenInstanceError
    import pytest

    r = DriverResult(
        metric_global_id="x",
        label="X",
        formula_description="",
        valor_brl=Decimal("0"),
    )
    with pytest.raises(FrozenInstanceError):
        r.valor_brl = Decimal("1")  # type: ignore[misc]


def test_driver_result_defaults():
    """Campos opcionais tem defaults sensatos."""
    r = DriverResult(
        metric_global_id="x",
        label="X",
        formula_description="",
        valor_brl=Decimal("100"),
    )
    assert r.valor_d_prev is None
    assert r.valor_d0 is None
    assert r.evidencias == ()
    assert r.endpoints_required == ()
    assert r.indeterminado_por_dado is False
    assert r.motivo_indeterminado is None
    assert r.endpoints_unavailable == ()


def test_evidence_shape():
    e = Evidence(label="NC 12345", valor_brl=Decimal("1500"), source="wh_x")
    assert e.label == "NC 12345"
    assert e.valor_brl == Decimal("1500")
    assert e.source == "wh_x"


# ─────────────────────────────────────────────────────────────────────────────
# CotaSubDriversComputation shape
# ─────────────────────────────────────────────────────────────────────────────


def test_computation_has_expected_fields():
    expected = {
        "data_d0",
        "data_d_prev",
        "drivers",
        "pl_sub_d_prev",
        "pl_sub_d0",
        "pl_sub_delta",
        "soma_drivers",
        "residuo",
        "indeterminados",
    }
    actual = set(CotaSubDriversComputation.__dataclass_fields__.keys())
    assert actual == expected, f"Diff: missing={expected-actual} extra={actual-expected}"


# ─────────────────────────────────────────────────────────────────────────────
# compute_drivers signature
# ─────────────────────────────────────────────────────────────────────────────


def test_compute_drivers_signature():
    sig = inspect.signature(compute_drivers)
    params = list(sig.parameters.keys())
    assert params == ["db", "tenant_id", "ua_id", "data_d0", "data_d_prev"]
    assert sig.parameters["data_d_prev"].default is None


# ─────────────────────────────────────────────────────────────────────────────
# Schema Pydantic (DriverResultOut em VariacaoDiariaResponse)
# ─────────────────────────────────────────────────────────────────────────────


def test_variacao_diaria_response_has_drivers_field():
    fields = VariacaoDiariaResponse.model_fields
    assert "drivers" in fields
    assert "soma_drivers" in fields
    assert "residuo_modelo" in fields


def test_driver_result_out_round_trip():
    """Conversao DriverResult -> DriverResultOut -> dict json e estavel."""
    r = DriverResult(
        metric_global_id="controladoria.cota_sub.driver.pdd",
        label="PDD",
        formula_description="-d valor_pdd",
        valor_brl=Decimal("-12345.67"),
        valor_d_prev=Decimal("100000"),
        valor_d0=Decimal("112345.67"),
        endpoints_required=("qitech.market.fidc_estoque",),
    )
    out = DriverResultOut(
        metric_global_id=r.metric_global_id,
        label=r.label,
        formula_description=r.formula_description,
        valor_brl=r.valor_brl,
        valor_d_prev=r.valor_d_prev,
        valor_d0=r.valor_d0,
        endpoints_required=list(r.endpoints_required),
        indeterminado_por_dado=r.indeterminado_por_dado,
        motivo_indeterminado=r.motivo_indeterminado,
        endpoints_unavailable=list(r.endpoints_unavailable),
    )
    j = out.model_dump(mode="json")
    assert j["metric_global_id"] == "controladoria.cota_sub.driver.pdd"
    assert j["valor_brl"] == "-12345.67"
    assert j["endpoints_required"] == ["qitech.market.fidc_estoque"]
