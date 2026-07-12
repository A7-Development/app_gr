"""Testes do tolerance service — funcoes puras, sem DB."""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.integracoes.services.tolerance import (
    PublicationState,
    ToleranceWindow,
    compute_publication_state,
    count_business_days_between,
    resolve_tolerance_window,
)

# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def _business_days_2026_05() -> frozenset[date]:
    """Conjunto de dias uteis em maio/2026 (segunda a sexta, sem feriado)."""
    return frozenset(
        date(2026, 5, d)
        for d in range(1, 32)
        if date(2026, 5, d).weekday() < 5  # 0..4 = seg..sex
    )


# ──────────────────────────────────────────────────────────────────────────
# ToleranceWindow validation
# ──────────────────────────────────────────────────────────────────────────


def test_tolerance_window_accepts_monotonic():
    w = ToleranceWindow(
        expected_lag_business_days=1,
        tolerance_business_days=3,
        give_up_business_days=10,
    )
    assert w.expected_lag_business_days == 1


def test_tolerance_window_rejects_negative_expected():
    with pytest.raises(ValueError, match="expected_lag must be >= 0"):
        ToleranceWindow(
            expected_lag_business_days=-1,
            tolerance_business_days=3,
            give_up_business_days=10,
        )


def test_tolerance_window_rejects_tolerance_below_expected():
    with pytest.raises(ValueError, match="tolerance .* < expected"):
        ToleranceWindow(
            expected_lag_business_days=5,
            tolerance_business_days=3,
            give_up_business_days=10,
        )


def test_tolerance_window_rejects_give_up_below_tolerance():
    with pytest.raises(ValueError, match="give_up .* < tolerance"):
        ToleranceWindow(
            expected_lag_business_days=1,
            tolerance_business_days=5,
            give_up_business_days=3,
        )


# ──────────────────────────────────────────────────────────────────────────
# resolve_tolerance_window — combinacao override + default
# ──────────────────────────────────────────────────────────────────────────


def test_resolve_all_null_uses_defaults():
    w = resolve_tolerance_window(
        expected_lag_override=None,
        tolerance_override=None,
        give_up_override=None,
        default_expected_lag=1,
        default_tolerance=3,
        default_give_up=10,
    )
    assert w.expected_lag_business_days == 1
    assert w.tolerance_business_days == 3
    assert w.give_up_business_days == 10


def test_resolve_partial_override_mixes():
    """Override apenas de tolerance — outros herdam catalogo."""
    w = resolve_tolerance_window(
        expected_lag_override=None,
        tolerance_override=5,
        give_up_override=None,
        default_expected_lag=1,
        default_tolerance=3,
        default_give_up=10,
    )
    assert w.expected_lag_business_days == 1
    assert w.tolerance_business_days == 5
    assert w.give_up_business_days == 10


def test_resolve_combination_breaks_monotonicity():
    """Override que viola monotonicidade contra defaults: erro."""
    with pytest.raises(ValueError, match="give_up .* < tolerance"):
        resolve_tolerance_window(
            expected_lag_override=None,
            tolerance_override=15,
            give_up_override=None,
            default_expected_lag=1,
            default_tolerance=3,
            default_give_up=10,
        )


# ──────────────────────────────────────────────────────────────────────────
# count_business_days_between
# ──────────────────────────────────────────────────────────────────────────


def test_count_today_equals_reference_is_zero():
    days = count_business_days_between(
        reference_date=date(2026, 5, 14),
        today=date(2026, 5, 14),
        business_days_set=_business_days_2026_05(),
    )
    assert days == 0


def test_count_today_before_reference_is_zero():
    days = count_business_days_between(
        reference_date=date(2026, 5, 14),
        today=date(2026, 5, 13),
        business_days_set=_business_days_2026_05(),
    )
    assert days == 0


def test_count_d_plus_one_business_day():
    """Caso real: relatorio do dia 14 (quinta), hoje 15 (sexta) = 1 dia util."""
    days = count_business_days_between(
        reference_date=date(2026, 5, 14),
        today=date(2026, 5, 15),
        business_days_set=_business_days_2026_05(),
    )
    assert days == 1


def test_count_across_weekend():
    """Sexta -> segunda = 1 dia util (sexta foi a referencia, segunda e D+1)."""
    days = count_business_days_between(
        reference_date=date(2026, 5, 15),  # sexta
        today=date(2026, 5, 18),  # segunda
        business_days_set=_business_days_2026_05(),
    )
    assert days == 1


def test_count_weekend_only_is_zero():
    """Sabado -> domingo: zero dias uteis."""
    days = count_business_days_between(
        reference_date=date(2026, 5, 16),  # sabado
        today=date(2026, 5, 17),  # domingo
        business_days_set=_business_days_2026_05(),
    )
    assert days == 0


# ──────────────────────────────────────────────────────────────────────────
# compute_publication_state — cenarios canonicos
# ──────────────────────────────────────────────────────────────────────────


def _conta_corrente_window() -> ToleranceWindow:
    """Default do catalogo pra market reports: expected=1, tolerance=3, give_up=10."""
    return ToleranceWindow(
        expected_lag_business_days=1,
        tolerance_business_days=3,
        give_up_business_days=10,
    )


def test_state_caso_real_2026_05_15_ainda_esperado():
    """Cenario do usuario: relatorio do dia 14, hoje dia 15. D+1 = ESPERADO."""
    state = compute_publication_state(
        reference_date=date(2026, 5, 14),  # quinta
        today=date(2026, 5, 15),  # sexta
        business_days_set=_business_days_2026_05(),
        window=_conta_corrente_window(),
    )
    assert state == PublicationState.ESPERADO


def test_state_atrasado_d_plus_3():
    """Hoje 19/05 (terca), relatorio do dia 14: D+3 util = ATRASADO."""
    state = compute_publication_state(
        reference_date=date(2026, 5, 14),
        today=date(2026, 5, 19),
        business_days_set=_business_days_2026_05(),
        window=_conta_corrente_window(),
    )
    # Dias uteis entre 14 (excl) e 19 (incl): 15, 18, 19 = 3 dias uteis
    assert state == PublicationState.ATRASADO


def test_state_suspeito_d_plus_5():
    """5 dias uteis depois — passou da tolerancia, virou SUSPEITO."""
    state = compute_publication_state(
        reference_date=date(2026, 5, 14),
        today=date(2026, 5, 21),  # quinta
        business_days_set=_business_days_2026_05(),
        window=_conta_corrente_window(),
    )
    # Dias uteis: 15, 18, 19, 20, 21 = 5 (acima de tolerance=3, abaixo de give_up=10)
    assert state == PublicationState.SUSPEITO


def test_state_furo_definitivo_passa_give_up():
    """11 dias uteis depois — desistir."""
    # Em maio/2026 + junho/2026, 14/05 + 11 uteis = ~01/06
    business_days = frozenset(
        date(2026, m, d)
        for m in (5, 6)
        for d in range(1, 32)
        if d <= 30 or m == 5  # maio tem 31, junho 30
        for _ in [None]
        if date(2026, m, d).weekday() < 5
    )
    state = compute_publication_state(
        reference_date=date(2026, 5, 14),
        today=date(2026, 6, 1),  # ~11 dias uteis depois
        business_days_set=business_days,
        window=_conta_corrente_window(),
    )
    assert state == PublicationState.FURO_DEFINITIVO


def test_state_balance_d_plus_zero_esperado():
    """bank_account.balance: expected=0, tolerance=1, give_up=5. D+0 = ESPERADO."""
    window = ToleranceWindow(
        expected_lag_business_days=0,
        tolerance_business_days=1,
        give_up_business_days=5,
    )
    state = compute_publication_state(
        reference_date=date(2026, 5, 15),
        today=date(2026, 5, 15),
        business_days_set=_business_days_2026_05(),
        window=window,
    )
    assert state == PublicationState.ESPERADO


def test_state_balance_d_plus_one_atrasado():
    """balance D+1 = ATRASADO (expected=0 já foi excedido)."""
    window = ToleranceWindow(
        expected_lag_business_days=0,
        tolerance_business_days=1,
        give_up_business_days=5,
    )
    state = compute_publication_state(
        reference_date=date(2026, 5, 14),
        today=date(2026, 5, 15),
        business_days_set=_business_days_2026_05(),
        window=window,
    )
    assert state == PublicationState.ATRASADO


def test_state_fronteira_inclusiva_no_expected():
    """No limite exato de expected, ainda e ESPERADO."""
    window = ToleranceWindow(
        expected_lag_business_days=1,
        tolerance_business_days=3,
        give_up_business_days=10,
    )
    state = compute_publication_state(
        reference_date=date(2026, 5, 14),
        today=date(2026, 5, 15),  # 1 dia util depois
        business_days_set=_business_days_2026_05(),
        window=window,
    )
    assert state == PublicationState.ESPERADO


def test_state_fronteira_inclusiva_no_tolerance():
    """No limite exato de tolerance, ainda e ATRASADO."""
    window = _conta_corrente_window()  # tolerance=3
    state = compute_publication_state(
        reference_date=date(2026, 5, 14),
        today=date(2026, 5, 19),  # 3 dias uteis (15, 18, 19)
        business_days_set=_business_days_2026_05(),
        window=window,
    )
    assert state == PublicationState.ATRASADO


def test_state_fronteira_furo_no_give_up_plus_one():
    """Logo apos give_up: FURO_DEFINITIVO."""
    business_days = frozenset(
        date(y, m, d)
        for y in [2026]
        for m in range(5, 7)
        for d in range(1, 32)
        if (m, d) != (6, 31) and not (m == 6 and d > 30)
        if date(y, m, d).weekday() < 5
    )
    window = _conta_corrente_window()  # give_up=10
    # 11 dias uteis depois de 14/05: 15, 18, 19, 20, 21, 22, 25, 26, 27, 28, 29
    state = compute_publication_state(
        reference_date=date(2026, 5, 14),
        today=date(2026, 5, 29),
        business_days_set=business_days,
        window=window,
    )
    assert state == PublicationState.FURO_DEFINITIVO
