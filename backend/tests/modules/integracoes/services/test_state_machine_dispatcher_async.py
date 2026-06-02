"""Testes do branch assincrono do state machine dispatcher.

Cobre `_process_async_report_row` — usado por endpoints com
`is_async_report=True` (hoje so `market.fidc_estoque`). Travam:
- o dispatcher NAO posta novo POST com QitechReportJob WAITING/PROCESSING ativo
  (job-storm), e a transicao final usa a LEITURA do raw, nunca o POST imediato;
- o **gate de ancora** (`_anchor_defer_at`): nao tenta antes do dado ser
  publicavel (expected_lag) NEM antes do horario de inicio do ciclo diario
  (daily_at HH:MM SP), e segura a row overnight ate a proxima ancora.

Monkeypatcha os helpers de DB do modulo + congela `now` (via `smd.datetime`)
pra testar a logica de decisao sem tocar o banco e sem depender da hora real.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.enums import Environment, SourceType
from app.modules.integracoes.public import endpoint_catalog
from app.modules.integracoes.services import state_machine_dispatcher as smd
from app.modules.integracoes.services.state_machine import EndpointDateStateValue
from app.modules.integracoes.services.tolerance import ToleranceWindow

_FIDC_ESTOQUE = "market.fidc_estoque"
_SP = ZoneInfo("America/Sao_Paulo")


def _spec():
    specs = {s.name: s for s in endpoint_catalog(SourceType.ADMIN_QITECH)}
    return specs[_FIDC_ESTOQUE]


def _sp_at(hour: int, minute: int = 0, *, day_offset: int = 0) -> datetime:
    """Instante UTC correspondente a HH:MM SP de hoje (+offset de dias)."""
    base = datetime.now(UTC).astimezone(_SP).date() + timedelta(days=day_offset)
    return datetime.combine(base, time(hour, minute), tzinfo=_SP).astimezone(UTC)


def _freeze(monkeypatch, now_utc: datetime) -> None:
    """Congela `datetime.now(...)` DENTRO do modulo smd em `now_utc` (aware UTC)."""

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return now_utc if tz is None else now_utc.astimezone(tz)

    monkeypatch.setattr(smd, "datetime", _Fixed)


def _business_days() -> frozenset[date]:
    """Dias uteis (seg-sex) dos ultimos ~40 dias ate +5, ancorados em hoje SP."""
    today = datetime.now(UTC).astimezone(_SP).date()
    start = today - timedelta(days=40)
    out = []
    d = start
    while d <= today + timedelta(days=5):
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return frozenset(out)


def _recent_business_day() -> date:
    """Ultimo dia util estritamente antes de hoje (ESPERADO/ATRASADO, nao FURO)."""
    d = datetime.now(UTC).astimezone(_SP).date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _future_business_day() -> date:
    """Proximo dia util estritamente apos hoje (seed +N d.u. a frente)."""
    d = datetime.now(UTC).astimezone(_SP).date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _fake_row(data_referencia: date):
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        source_type=SourceType.ADMIN_QITECH.value,
        environment=Environment.PRODUCTION.value,
        endpoint_name=_FIDC_ESTOQUE,
        data_referencia=data_referencia,
        unidade_administrativa_id=uuid4(),
        attempts_count=0,
    )


class _FakeDB:
    """Context manager async que aceita execute/commit como no-op."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *a, **kw):
        return None

    async def commit(self):
        return None


@pytest.fixture
def _patch_common(monkeypatch):
    """Patches compartilhados: tolerancia, calendario, schedule, sessao, clock.

    Clock default = hoje 10:00 SP (apos a ancora 09:00) — os testes de
    publicabilidade/POST nao dependem da hora real. Testes de ancora re-congelam.
    """
    window = ToleranceWindow(
        expected_lag_business_days=1,
        tolerance_business_days=2,
        give_up_business_days=7,
    )

    async def fake_window(*a, **kw):
        return window

    async def fake_business_days(*a, **kw):
        return _business_days()

    async def fake_schedule(*a, **kw):
        return ("daily_at", "09:00")

    monkeypatch.setattr(smd, "_load_tolerance_for_endpoint", fake_window)
    monkeypatch.setattr(smd, "_load_business_days", fake_business_days)
    monkeypatch.setattr(smd, "_load_schedule_for_endpoint", fake_schedule)
    monkeypatch.setattr(smd, "AsyncSessionLocal", lambda: _FakeDB())
    _freeze(monkeypatch, _sp_at(10))


async def test_async_completo_quando_raw_presente_nao_posta(monkeypatch, _patch_common):
    """Webhook de um POST anterior ja gravou o raw (http 200) -> COMPLETE,
    e NAO dispara novo POST."""
    row = _fake_row(_recent_business_day())

    async def fake_raw(*a, **kw):
        return (200, "complete")

    posted = []

    async def fake_run_sync(*a, **kw):
        posted.append(kw)

    monkeypatch.setattr(smd, "_fetch_latest_raw_status", fake_raw)
    monkeypatch.setattr(smd, "run_sync_endpoint", fake_run_sync)

    out = await smd._process_async_report_row(row, spec=_spec())

    assert out["ok"] is True
    assert out["new_state"] == EndpointDateStateValue.COMPLETE.value
    assert posted == [], "nao deve disparar POST quando o dado ja chegou"
    assert out["async_posted"] is False


async def test_async_nao_posta_quando_job_ativo(monkeypatch, _patch_common):
    """Sem dado ainda, mas ha job WAITING/PROCESSING -> guard de in-flight:
    NAO dispara novo POST; estado fica retentavel (NOT_PUBLISHED)."""
    row = _fake_row(_recent_business_day())

    async def fake_raw(*a, **kw):
        return (None, None)

    async def fake_active(*a, **kw):
        return True

    posted = []

    async def fake_run_sync(*a, **kw):
        posted.append(kw)

    monkeypatch.setattr(smd, "_fetch_latest_raw_status", fake_raw)
    monkeypatch.setattr(smd, "_has_active_async_report_job", fake_active)
    monkeypatch.setattr(smd, "run_sync_endpoint", fake_run_sync)

    out = await smd._process_async_report_row(row, spec=_spec())

    assert out["ok"] is True
    assert posted == [], "guard de in-flight deve impedir POST com job ativo"
    assert out["async_posted"] is False
    assert out["new_state"] == EndpointDateStateValue.NOT_PUBLISHED.value


async def test_async_posta_quando_sem_dado_e_sem_job(monkeypatch, _patch_common):
    """Sem dado e sem job ativo (apos a ancora) -> dispara exatamente 1 POST;
    estado retentavel (NOT_PUBLISHED) ate o webhook chegar no proximo poll."""
    row = _fake_row(_recent_business_day())

    async def fake_raw(*a, **kw):
        return (None, None)

    async def fake_active(*a, **kw):
        return False

    posted = []

    async def fake_run_sync(*args, **kw):
        posted.append((args, kw))

    monkeypatch.setattr(smd, "_fetch_latest_raw_status", fake_raw)
    monkeypatch.setattr(smd, "_has_active_async_report_job", fake_active)
    monkeypatch.setattr(smd, "run_sync_endpoint", fake_run_sync)

    out = await smd._process_async_report_row(row, spec=_spec())

    assert out["ok"] is True
    assert len(posted) == 1, "deve disparar 1 POST quando nao ha dado nem job"
    assert out["async_posted"] is True
    assert out["new_state"] == EndpointDateStateValue.NOT_PUBLISHED.value
    # triggered_by carrega o id da row (rastreabilidade no decision_log/job).
    assert posted[0][1]["triggered_by"] == f"state_machine:{row.id}"


async def test_async_abandona_apos_give_up(monkeypatch, _patch_common):
    """Data muito antiga (> give_up_business_days) sem dado -> ABANDONED,
    e NAO dispara POST (nao martela fonte morta)."""
    row = _fake_row(datetime.now(UTC).astimezone(_SP).date() - timedelta(days=30))

    async def fake_raw(*a, **kw):
        return (None, None)

    async def fake_active(*a, **kw):
        return False

    posted = []

    async def fake_run_sync(*a, **kw):
        posted.append(kw)

    monkeypatch.setattr(smd, "_fetch_latest_raw_status", fake_raw)
    monkeypatch.setattr(smd, "_has_active_async_report_job", fake_active)
    monkeypatch.setattr(smd, "run_sync_endpoint", fake_run_sync)

    out = await smd._process_async_report_row(row, spec=_spec())

    assert out["ok"] is True
    assert out["new_state"] == EndpointDateStateValue.ABANDONED.value
    assert posted == [], "data vencida (FURO_DEFINITIVO) nao deve disparar POST"


async def test_async_data_futura_reagenda_sem_postar(monkeypatch, _patch_common):
    """Data de referencia A FRENTE de hoje (seed +N d.u.) ainda nao atingiu
    `expected_lag` -> nao dispara POST (geraria 0-byte); re-agenda e fica
    retentavel (NOT_STARTED). Era o vazamento: ~70% das chamadas queimadas."""
    row = _fake_row(_future_business_day())

    async def fake_raw(*a, **kw):
        return (None, None)

    async def fake_active(*a, **kw):
        return False

    posted = []

    async def fake_run_sync(*a, **kw):
        posted.append(kw)

    monkeypatch.setattr(smd, "_fetch_latest_raw_status", fake_raw)
    monkeypatch.setattr(smd, "_has_active_async_report_job", fake_active)
    monkeypatch.setattr(smd, "run_sync_endpoint", fake_run_sync)

    out = await smd._process_async_report_row(row, spec=_spec())

    assert out["ok"] is True
    assert out["new_state"] == EndpointDateStateValue.NOT_STARTED.value
    assert out["deferred_future_reference"] is True
    assert posted == [], "data futura nao deve disparar POST"


async def test_anchor_defer_antes_das_0900(monkeypatch, _patch_common):
    """ref=D-1 (publicavel hoje) mas `now`=02:00 SP < ancora 09:00 -> nao POSTa,
    re-agenda. O ciclo do dia comeca na ancora, nao na meia-noite."""
    _freeze(monkeypatch, _sp_at(2))
    row = _fake_row(_recent_business_day())

    async def fake_raw(*a, **kw):
        return (None, None)

    async def fake_active(*a, **kw):
        return False

    posted = []

    async def fake_run_sync(*a, **kw):
        posted.append(kw)

    monkeypatch.setattr(smd, "_fetch_latest_raw_status", fake_raw)
    monkeypatch.setattr(smd, "_has_active_async_report_job", fake_active)
    monkeypatch.setattr(smd, "run_sync_endpoint", fake_run_sync)

    out = await smd._process_async_report_row(row, spec=_spec())

    assert out["ok"] is True
    assert out["deferred_future_reference"] is True
    assert posted == [], "antes das 09:00 SP nao deve POSTar"


async def test_anchor_posta_apos_0900(monkeypatch, _patch_common):
    """ref=D-1, `now`=09:30 SP >= ancora, sem dado e sem job -> POSTa."""
    _freeze(monkeypatch, _sp_at(9, 30))
    row = _fake_row(_recent_business_day())

    async def fake_raw(*a, **kw):
        return (None, None)

    async def fake_active(*a, **kw):
        return False

    posted = []

    async def fake_run_sync(*a, **kw):
        posted.append(kw)

    monkeypatch.setattr(smd, "_fetch_latest_raw_status", fake_raw)
    monkeypatch.setattr(smd, "_has_active_async_report_job", fake_active)
    monkeypatch.setattr(smd, "run_sync_endpoint", fake_run_sync)

    out = await smd._process_async_report_row(row, spec=_spec())

    assert out["ok"] is True
    assert out["async_posted"] is True
    assert len(posted) == 1


async def test_anchor_hold_overnight(monkeypatch, _patch_common):
    """Row que rolou pro novo dia (`now`=D+1 00:20 SP) fica retida ate a
    proxima ancora 09:00 — nao tenta de madrugada."""
    _freeze(monkeypatch, _sp_at(0, 20, day_offset=1))
    row = _fake_row(_recent_business_day())

    async def fake_raw(*a, **kw):
        return (None, None)

    async def fake_active(*a, **kw):
        return False

    posted = []

    async def fake_run_sync(*a, **kw):
        posted.append(kw)

    monkeypatch.setattr(smd, "_fetch_latest_raw_status", fake_raw)
    monkeypatch.setattr(smd, "_has_active_async_report_job", fake_active)
    monkeypatch.setattr(smd, "run_sync_endpoint", fake_run_sync)

    out = await smd._process_async_report_row(row, spec=_spec())

    assert out["ok"] is True
    assert out["deferred_future_reference"] is True
    assert posted == [], "madrugada (antes da ancora do novo dia) segura a row"


async def test_anchor_respeita_override_tsec(monkeypatch, _patch_common):
    """Override de schedule do tenant (11:00) e respeitado: `now`=10:00 SP <
    11:00 -> defer (nao usa o default 09:00 do catalogo)."""
    _freeze(monkeypatch, _sp_at(10))

    async def fake_schedule_11(*a, **kw):
        return ("daily_at", "11:00")

    monkeypatch.setattr(smd, "_load_schedule_for_endpoint", fake_schedule_11)
    row = _fake_row(_recent_business_day())

    async def fake_raw(*a, **kw):
        return (None, None)

    async def fake_active(*a, **kw):
        return False

    posted = []

    async def fake_run_sync(*a, **kw):
        posted.append(kw)

    monkeypatch.setattr(smd, "_fetch_latest_raw_status", fake_raw)
    monkeypatch.setattr(smd, "_has_active_async_report_job", fake_active)
    monkeypatch.setattr(smd, "run_sync_endpoint", fake_run_sync)

    out = await smd._process_async_report_row(row, spec=_spec())

    assert out["ok"] is True
    assert out["deferred_future_reference"] is True
    assert posted == [], "10:00 SP < ancora 11:00 do override -> defer"


# ── Unit do gate puro `_anchor_defer_at` (recebe `now` explicito) ──────────────


def test_anchor_defer_at_barra_futuro_e_libera_passado():
    """Data futura -> defer na ancora (09:00 SP) de um dia futuro; data ja
    publicavel, apos a ancora de hoje -> None (segue fluxo normal)."""
    window = ToleranceWindow(1, 2, 7)
    bdays = _business_days()
    now = _sp_at(10)  # hoje 10:00 SP, apos a ancora
    today_sp = now.astimezone(_SP).date()

    futuro = smd._anchor_defer_at(
        reference_date=_future_business_day(),
        now=now,
        business_days_set=bdays,
        window=window,
        schedule_kind="daily_at",
        schedule_value="09:00",
    )
    assert futuro is not None
    assert futuro.astimezone(_SP).hour == 9
    assert futuro.astimezone(_SP).date() > today_sp

    passado = smd._anchor_defer_at(
        reference_date=today_sp - timedelta(days=7),
        now=now,
        business_days_set=bdays,
        window=window,
        schedule_kind="daily_at",
        schedule_value="09:00",
    )
    assert passado is None, "dado publicavel e apos a ancora -> nao barra"


def test_anchor_floor_antes_da_ancora_mesmo_publicavel():
    """Mesmo com dado ja publicavel, antes da ancora do dia -> segura ate HH:MM."""
    window = ToleranceWindow(1, 2, 7)
    bdays = _business_days()
    now = _sp_at(7)  # 07:00 SP, antes da ancora 09:00
    today_sp = now.astimezone(_SP).date()

    res = smd._anchor_defer_at(
        reference_date=today_sp - timedelta(days=7),
        now=now,
        business_days_set=bdays,
        window=window,
        schedule_kind="daily_at",
        schedule_value="09:00",
    )
    assert res is not None
    assert res.astimezone(_SP).hour == 9
    assert res.astimezone(_SP).date() == today_sp


def test_anchor_lag_zero_respeita_ancora():
    """Endpoint same-day (expected_lag=0) NAO e isento da ancora: apos 09:00 ->
    None; antes -> defer."""
    window = ToleranceWindow(0, 1, 5)
    bdays = _business_days()
    today_sp = datetime.now(UTC).astimezone(_SP).date()

    assert (
        smd._anchor_defer_at(
            reference_date=today_sp,
            now=_sp_at(10),
            business_days_set=bdays,
            window=window,
            schedule_kind="daily_at",
            schedule_value="09:00",
        )
        is None
    )
    antes = smd._anchor_defer_at(
        reference_date=today_sp,
        now=_sp_at(7),
        business_days_set=bdays,
        window=window,
        schedule_kind="daily_at",
        schedule_value="09:00",
    )
    assert antes is not None


def test_anchor_kind_nao_daily_usa_floor_publicabilidade():
    """schedule_kind != daily_at -> floor de publicabilidade (09:00 SP fixo),
    equivalente ao comportamento anterior do gate de data-futura."""
    window = ToleranceWindow(1, 2, 7)
    bdays = _business_days()
    now = _sp_at(10)
    today_sp = now.astimezone(_SP).date()

    assert (
        smd._anchor_defer_at(
            reference_date=today_sp - timedelta(days=7),
            now=now,
            business_days_set=bdays,
            window=window,
            schedule_kind="interval",
            schedule_value="60",
        )
        is None
    )
    futuro = smd._anchor_defer_at(
        reference_date=_future_business_day(),
        now=now,
        business_days_set=bdays,
        window=window,
        schedule_kind="interval",
        schedule_value="60",
    )
    assert futuro is not None
    assert futuro.astimezone(_SP).hour == 9
