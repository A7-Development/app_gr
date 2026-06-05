"""Unit tests for revenue_analytics — pure deterministic functions.

Run isolated (no DB needed):
    pytest backend/tests/modules/credito/services/test_revenue_analytics.py --noconftest
"""

from __future__ import annotations

from datetime import date

from app.modules.credito.services.revenue_analytics import (
    analyze_revenue_series,
    attestation_signals,
)


def _series(values: list[float], start_year: int = 2024, start_month: int = 1):
    """Helper: build a [{month,value}] series of consecutive months."""
    out = []
    y, m = start_year, start_month
    for v in values:
        out.append({"month": f"{y:04d}-{m:02d}", "value": v})
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


# ─── aggregates / trend ──────────────────────────────────────────────────


def test_aggregates_and_growing_trend():
    series = _series([100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200, 210])
    a = analyze_revenue_series(series, declared_total=1860)
    assert a.agregados["n_meses"] == 12
    assert a.agregados["total"] == 1860.0
    assert a.agregados["media"] == 155.0
    assert a.agregados["mes_maior"]["mes"] == "2024-12"
    assert a.agregados["mes_menor"]["mes"] == "2024-01"
    assert a.tendencia["direcao"] == "crescente"
    assert a.tendencia["slope_mensal"] == 10.0


def test_stable_trend():
    series = _series([100, 101, 99, 100, 102, 98, 100, 101, 99, 100, 100, 100])
    a = analyze_revenue_series(series)
    assert a.tendencia["direcao"] == "estavel"


def test_declining_trend():
    series = _series([210, 200, 190, 180, 170, 160, 150, 140, 130, 120, 110, 100])
    a = analyze_revenue_series(series)
    assert a.tendencia["direcao"] == "decrescente"


# ─── outliers / picos ────────────────────────────────────────────────────


def test_outlier_peak_detected():
    # média ~ 145; o pico de 1000 é > 2.5x → outlier.
    series = _series([100, 100, 100, 1000, 100, 100, 100, 100, 100, 100, 100, 100])
    a = analyze_revenue_series(series)
    peaks = [o for o in a.outliers if o["tipo"] == "pico"]
    assert any(o["mes"] == "2024-04" for o in peaks)


def test_outlier_valley_detected():
    series = _series([100, 100, 100, 5, 100, 100, 100, 100, 100, 100, 100, 100])
    a = analyze_revenue_series(series)
    valleys = [o for o in a.outliers if o["tipo"] == "vale"]
    assert any(o["mes"] == "2024-04" for o in valleys)


# ─── qualidade ───────────────────────────────────────────────────────────


def test_sum_mismatch_flagged():
    series = _series([100, 100, 100])
    a = analyze_revenue_series(series, declared_total=999)
    assert a.qualidade["soma_confere"] is False
    assert a.qualidade["soma_meses"] == 300.0


def test_sum_matches_within_tolerance():
    series = _series([100, 100, 100])
    a = analyze_revenue_series(series, declared_total=300)
    assert a.qualidade["soma_confere"] is True


def test_missing_months_detected():
    series = [
        {"month": "2024-01", "value": 100},
        {"month": "2024-02", "value": 100},
        {"month": "2024-05", "value": 100},  # gap: mar, abr faltam
    ]
    a = analyze_revenue_series(series)
    assert a.qualidade["meses_faltantes"] == ["2024-03", "2024-04"]


def test_zero_month_detected():
    series = _series([100, 0, 100])
    a = analyze_revenue_series(series)
    assert a.qualidade["meses_zerados"] == ["2024-02"]


def test_missing_months_across_year_boundary():
    series = [
        {"month": "2024-11", "value": 100},
        {"month": "2025-02", "value": 100},  # dez/jan faltam
    ]
    a = analyze_revenue_series(series)
    assert a.qualidade["meses_faltantes"] == ["2024-12", "2025-01"]


# ─── yoy ─────────────────────────────────────────────────────────────────


def test_yoy_computed_with_two_years():
    series = _series([100] * 12, start_year=2023) + _series([120] * 12, start_year=2024)
    a = analyze_revenue_series(series)
    assert a.yoy is not None
    assert a.yoy["media_pct"] == 20.0


def test_yoy_none_with_single_year():
    a = analyze_revenue_series(_series([100] * 12))
    assert a.yoy is None


# ─── seasonality confidence ──────────────────────────────────────────────


def test_seasonality_not_reliable_under_24_months():
    a = analyze_revenue_series(_series([100] * 12))
    assert a.sazonalidade["confiavel"] is False


def test_seasonality_reliable_with_24_months():
    a = analyze_revenue_series(_series([100] * 24))
    assert a.sazonalidade["confiavel"] is True


# ─── empty ───────────────────────────────────────────────────────────────


def test_empty_series_is_coherent():
    a = analyze_revenue_series([], declared_total=None)
    assert a.agregados["n_meses"] == 0
    assert a.outliers == []
    assert a.yoy is None
    assert a.serie == []


def test_non_list_input_is_safe():
    a = analyze_revenue_series(None)
    assert a.agregados["n_meses"] == 0


# ─── attestation signals ─────────────────────────────────────────────────


def test_attestation_full():
    documento = {
        "data_documento": "2024-03-15",
        "assinado": True,
        "signatarios": [
            {"nome": "João Contador", "cargo": "contador", "documento": "CRC-1234"}
        ],
        "observacoes": ["Valores sujeitos a revisão"],
        "emitente": {"nome": "Contabilidade X", "cnpj": "11.222.333/0001-44", "tipo": "contabilidade"},
        "papel_timbrado": True,
    }
    sig = attestation_signals(
        documento, target_cnpj="55.666.777/0001-88", ref_date=date(2024, 6, 15)
    )
    assert sig["assinado"] is True
    assert sig["qtd_signatarios"] == 1
    assert sig["idade_meses"] == 3
    assert sig["recente"] is True
    assert sig["emitente_confere"] is False  # emitente != alvo (contabilidade terceira)
    assert sig["tem_ressalva"] is True


def test_attestation_emitente_matches_target():
    documento = {
        "data_documento": "2026-01-01",
        "emitente": {"cnpj": "55666777000188"},
    }
    sig = attestation_signals(
        documento, target_cnpj="55.666.777/0001-88", ref_date=date(2026, 2, 1)
    )
    assert sig["emitente_confere"] is True


def test_attestation_stale_document():
    sig = attestation_signals(
        {"data_documento": "2023-01-01"},
        target_cnpj=None,
        ref_date=date(2026, 6, 1),
    )
    assert sig["recente"] is False
    assert sig["idade_meses"] == 41


def test_attestation_absent_block_is_conservative():
    sig = attestation_signals(None, target_cnpj="123", ref_date=date(2026, 1, 1))
    assert sig["assinado"] is False
    assert sig["idade_meses"] is None
    assert sig["recente"] is None
    assert sig["emitente_confere"] is None
    assert sig["tem_ressalva"] is False
