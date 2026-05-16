"""Testes puros pro candidate set 'retryable' compartilhado entre
reconciler, watermark_scanner e oneshot CLI.

Fix A (2026-05-16): PARTIAL e NOT_PUBLISHED entraram no candidate set
junto com GAP. Sem isso, qualquer dia com http=200+completeness=partial
ficava grudado pra sempre (caso MEC 14/05).
"""

from __future__ import annotations

from datetime import date

from app.modules.integracoes.services.coverage import (
    CoverageStatus,
    _classify_day,
    _compute_tolerance_state,
)
from app.modules.integracoes.services.tolerance import (
    PublicationState,
    ToleranceWindow,
)


def _business_days() -> frozenset[date]:
    return frozenset(
        date(2026, 5, d) for d in range(1, 32) if date(2026, 5, d).weekday() < 5
    )


# ──────────────────────────────────────────────────────────────────────────
# _classify_day
# ──────────────────────────────────────────────────────────────────────────


def test_classify_day_partial_when_200_with_partial_completeness():
    """200 + completeness=partial → CoverageStatus.PARTIAL (nao OK)."""
    status = _classify_day(
        day=date(2026, 5, 14),
        today=date(2026, 5, 16),
        raw_status=200,
        calendar_entry=(True, False, False),
        first_data_in_endpoint=date(2026, 5, 1),
        completeness="partial",
    )
    assert status == CoverageStatus.PARTIAL


def test_classify_day_partial_when_200_with_empty_completeness():
    status = _classify_day(
        day=date(2026, 5, 14),
        today=date(2026, 5, 16),
        raw_status=200,
        calendar_entry=(True, False, False),
        first_data_in_endpoint=date(2026, 5, 1),
        completeness="empty",
    )
    assert status == CoverageStatus.PARTIAL


def test_classify_day_ok_when_200_complete():
    status = _classify_day(
        day=date(2026, 5, 14),
        today=date(2026, 5, 16),
        raw_status=200,
        calendar_entry=(True, False, False),
        first_data_in_endpoint=date(2026, 5, 1),
        completeness="complete",
    )
    assert status == CoverageStatus.OK


def test_classify_day_not_published_when_4xx():
    status = _classify_day(
        day=date(2026, 5, 14),
        today=date(2026, 5, 16),
        raw_status=400,
        calendar_entry=(True, False, False),
        first_data_in_endpoint=date(2026, 5, 1),
        completeness="empty",
    )
    assert status == CoverageStatus.NOT_PUBLISHED


def test_classify_day_gap_when_no_row_and_business_day():
    status = _classify_day(
        day=date(2026, 5, 14),
        today=date(2026, 5, 16),
        raw_status=None,
        calendar_entry=(True, False, False),
        first_data_in_endpoint=date(2026, 5, 1),
        completeness=None,
    )
    assert status == CoverageStatus.GAP


# ──────────────────────────────────────────────────────────────────────────
# _compute_tolerance_state — PARTIAL deve receber estado
# ──────────────────────────────────────────────────────────────────────────


def _window() -> ToleranceWindow:
    return ToleranceWindow(
        expected_lag_business_days=1,
        tolerance_business_days=3,
        give_up_business_days=10,
    )


def test_tolerance_state_assigned_to_partial():
    """PARTIAL agora recebe tolerance_state — reconciler precisa pra modular cooldown."""
    state = _compute_tolerance_state(
        status=CoverageStatus.PARTIAL,
        day=date(2026, 5, 14),
        today=date(2026, 5, 18),  # 2 dias uteis depois (15, 18)
        business_days_set=_business_days(),
        window=_window(),
    )
    # 2 uteis > expected=1, <= tolerance=3 → ATRASADO
    assert state == PublicationState.ATRASADO


def test_tolerance_state_assigned_to_gap():
    state = _compute_tolerance_state(
        status=CoverageStatus.GAP,
        day=date(2026, 5, 14),
        today=date(2026, 5, 18),
        business_days_set=_business_days(),
        window=_window(),
    )
    assert state == PublicationState.ATRASADO


def test_tolerance_state_assigned_to_not_published():
    state = _compute_tolerance_state(
        status=CoverageStatus.NOT_PUBLISHED,
        day=date(2026, 5, 14),
        today=date(2026, 5, 18),
        business_days_set=_business_days(),
        window=_window(),
    )
    assert state == PublicationState.ATRASADO


def test_tolerance_state_none_for_ok():
    state = _compute_tolerance_state(
        status=CoverageStatus.OK,
        day=date(2026, 5, 14),
        today=date(2026, 5, 18),
        business_days_set=_business_days(),
        window=_window(),
    )
    assert state is None


def test_tolerance_state_none_for_weekend():
    state = _compute_tolerance_state(
        status=CoverageStatus.WEEKEND,
        day=date(2026, 5, 9),
        today=date(2026, 5, 16),
        business_days_set=_business_days(),
        window=_window(),
    )
    assert state is None


# ──────────────────────────────────────────────────────────────────────────
# _RETRYABLE_STATUSES — cross-module consistency
# ──────────────────────────────────────────────────────────────────────────


def test_retryable_statuses_shared_across_modules():
    """Reconciler e watermark devem usar o mesmo candidate set.

    Se isso divergir, o sistema fica inconsistente: reconciler retenta
    PARTIAL mas o scanner do dia seguinte refila como se fosse gap.
    """
    from app.modules.integracoes.services.reconciler import (
        _RETRYABLE_STATUSES as RECON_SET,
    )
    from app.scheduler.jobs.watermark_scanner import (
        _RETRYABLE_STATUSES as SCANNER_SET,
    )

    assert set(RECON_SET) == set(SCANNER_SET)
    assert CoverageStatus.GAP in RECON_SET
    assert CoverageStatus.PARTIAL in RECON_SET
    assert CoverageStatus.NOT_PUBLISHED in RECON_SET
    # OK explicitamente fora — refresher cuida (Fix B).
    assert CoverageStatus.OK not in RECON_SET
