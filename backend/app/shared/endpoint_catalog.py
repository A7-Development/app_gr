"""Endpoint catalog primitives — shared across all integration adapters.

CLAUDE.md §13 introduces granularity: each adapter declares a catalog of the
endpoints it consumes (e.g. QiTech market reports, bank-account balance/statement),
each with its own default sync cadence. The catalog is **per-source, not
per-tenant** — endpoints are defined by the upstream API, not by who is calling
it. Per-tenant overrides live in `tenant_source_endpoint_config` (DB).

Why this exists:
    Until 2026-05-05, sync cadence was a single value per (tenant, source) in
    `tenant_source_config.sync_frequency_minutes`. That was too coarse for
    QiTech, which has ~12 endpoints with different natural cadences (daily
    market reports vs hourly bank statement vs end-of-day balance). The
    refactor (`docs/...`) moves cadence to the endpoint level.

Design notes:
    - `EndpointSpec` is **frozen** — adapters declare a static list at module
      load time. Catalog evolution = code change + migration.
    - `ScheduleKind` is intentionally narrow (interval / daily_at / on_demand).
      Cron support deliberately rejected to avoid dragging `croniter` as a new
      dep (CLAUDE.md §2). Cover 95% of real cases; promote to cron only when
      a concrete need shows up.
    - `default_schedule_value` semantics depend on `default_schedule_kind`:
        * INTERVAL  → string of integer minutes, range 15..1440
        * DAILY_AT  → string "HH:MM" in São Paulo timezone (the default tz of
          the scheduler — see `app/scheduler/scheduler.py`)
        * ON_DEMAND → must be None
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ScheduleKind(StrEnum):
    """How an endpoint is scheduled.

    Values are persisted as strings in `tenant_source_endpoint_config.schedule_kind`
    and validated by a CHECK constraint at the DB level. Adding a new kind
    requires both an enum entry here AND a CHECK constraint update via Alembic.
    """

    INTERVAL = "interval"
    DAILY_AT = "daily_at"
    ON_DEMAND = "on_demand"


@dataclass(frozen=True)
class EndpointSpec:
    """One endpoint of an integration adapter.

    Attributes:
        name: Source-prefixed unique identifier (e.g. "market.outros_fundos",
            "bank_account.balance"). Used as a key in `_HANDLERS` dicts inside
            adapters and stored in `tenant_source_endpoint_config.endpoint_name`.
            Convention: `<area>.<snake_case_label>`.
        label: pt-BR human-readable label rendered in the UI.
        description: Short pt-BR description (1-2 sentences).
        default_schedule_kind: Default cadence kind when a tenant has not
            overridden the endpoint config. See ScheduleKind doc for semantics
            of `default_schedule_value`.
        default_schedule_value: Default value matching `default_schedule_kind`.
            See ScheduleKind doc for format.
        canonical_table: Name of the silver table populated by this endpoint.
            Mostly for observability (UI showing "this endpoint feeds wh_X")
            and audit traceability.
        default_expected_lag_business_days: When reference-date data is
            expected to be published, counted in ANBIMA business days. For a
            D-1 market report fetched in D+1 morning, this is 1. For an
            intraday balance fetched same-day, this is 0. Tolerance state
            classifier (`compute_publication_state`) treats a row as
            ESPERADO while business_days_since_reference <= this value.
        default_tolerance_business_days: Upper bound, in business days, of
            the "slightly late but still expected" window. Once
            business_days_since_reference exceeds this, the row turns
            ATRASADO -> SUSPEITO (frontend shows amber/red). Must be
            >= default_expected_lag_business_days.
        default_give_up_business_days: After this many business days the
            row turns FURO_DEFINITIVO and the reconciler stops retrying
            automatically. Operator can reopen manually from the UI. Must
            be >= default_tolerance_business_days.
    """

    name: str
    label: str
    description: str
    default_schedule_kind: ScheduleKind
    default_schedule_value: str | None
    canonical_table: str
    default_expected_lag_business_days: int = 1
    default_tolerance_business_days: int = 3
    default_give_up_business_days: int = 10

    def __post_init__(self) -> None:
        # Self-validation: catch typos at module load time, before any DB
        # write happens. Anything caught here is a programming error in the
        # adapter's catalog file.
        if self.default_schedule_kind == ScheduleKind.ON_DEMAND:
            if self.default_schedule_value is not None:
                raise ValueError(
                    f"EndpointSpec({self.name!r}): ON_DEMAND must have "
                    f"default_schedule_value=None, got {self.default_schedule_value!r}"
                )
        elif self.default_schedule_kind == ScheduleKind.INTERVAL:
            if not (self.default_schedule_value or "").isdigit():
                raise ValueError(
                    f"EndpointSpec({self.name!r}): INTERVAL requires "
                    f"default_schedule_value to be integer string, got "
                    f"{self.default_schedule_value!r}"
                )
            n = int(self.default_schedule_value or "0")
            if not (15 <= n <= 1440):
                raise ValueError(
                    f"EndpointSpec({self.name!r}): INTERVAL value must be "
                    f"in [15, 1440], got {n}"
                )
        elif self.default_schedule_kind == ScheduleKind.DAILY_AT:
            v = self.default_schedule_value or ""
            if not _looks_like_hhmm(v):
                raise ValueError(
                    f"EndpointSpec({self.name!r}): DAILY_AT requires "
                    f"default_schedule_value HH:MM, got {v!r}"
                )

        # Tolerance window monotonicity — out-of-order values are programming
        # errors, not config typos. Catch at module load.
        if self.default_expected_lag_business_days < 0:
            raise ValueError(
                f"EndpointSpec({self.name!r}): expected_lag must be >= 0, got "
                f"{self.default_expected_lag_business_days}"
            )
        if (
            self.default_tolerance_business_days
            < self.default_expected_lag_business_days
        ):
            raise ValueError(
                f"EndpointSpec({self.name!r}): tolerance "
                f"({self.default_tolerance_business_days}) must be >= "
                f"expected ({self.default_expected_lag_business_days})"
            )
        if (
            self.default_give_up_business_days
            < self.default_tolerance_business_days
        ):
            raise ValueError(
                f"EndpointSpec({self.name!r}): give_up "
                f"({self.default_give_up_business_days}) must be >= "
                f"tolerance ({self.default_tolerance_business_days})"
            )


def _looks_like_hhmm(value: str) -> bool:
    """Light-weight HH:MM check — DB CHECK constraint is the authoritative regex.

    Accepts 00:00..23:59. Used in __post_init__ to fail fast on typos.
    """
    if len(value) != 5 or value[2] != ":":
        return False
    hh, mm = value.split(":")
    if not (hh.isdigit() and mm.isdigit()):
        return False
    return 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59
