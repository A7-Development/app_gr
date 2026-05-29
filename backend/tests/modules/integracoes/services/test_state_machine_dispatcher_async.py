"""Testes do branch assincrono do state machine dispatcher.

Cobre `_process_async_report_row` — usado por endpoints com
`is_async_report=True` (hoje so `market.fidc_estoque`). O risco que esses
testes travam: o dispatcher NAO pode disparar um POST novo enquanto ja ha
um QitechReportJob WAITING/PROCESSING pra mesma data (job-storm), e a
transicao final tem que usar a LEITURA do raw (webhook anterior), nunca o
resultado imediato do POST.

Monkeypatcha os helpers de DB do modulo pra testar a logica de decisao
(POSTar ou nao + estado resultante) sem tocar o banco.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.enums import Environment, SourceType
from app.modules.integracoes.public import endpoint_catalog
from app.modules.integracoes.services import state_machine_dispatcher as smd
from app.modules.integracoes.services.state_machine import EndpointDateStateValue
from app.modules.integracoes.services.tolerance import ToleranceWindow

_FIDC_ESTOQUE = "market.fidc_estoque"


def _spec():
    specs = {s.name: s for s in endpoint_catalog(SourceType.ADMIN_QITECH)}
    return specs[_FIDC_ESTOQUE]


def _business_days() -> frozenset[date]:
    """Dias uteis (seg-sex) dos ultimos ~40 dias ate +5, ancorados em hoje."""
    today = datetime.now(UTC).date()
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
    d = datetime.now(UTC).date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
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
    """Patches compartilhados: tolerancia, calendario, AsyncSessionLocal."""
    window = ToleranceWindow(
        expected_lag_business_days=1,
        tolerance_business_days=2,
        give_up_business_days=7,
    )

    async def fake_window(*a, **kw):
        return window

    async def fake_business_days(*a, **kw):
        return _business_days()

    monkeypatch.setattr(smd, "_load_tolerance_for_endpoint", fake_window)
    monkeypatch.setattr(smd, "_load_business_days", fake_business_days)
    monkeypatch.setattr(smd, "AsyncSessionLocal", lambda: _FakeDB())


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
    """Sem dado e sem job ativo -> dispara exatamente 1 POST; estado
    retentavel (NOT_PUBLISHED) ate o webhook chegar no proximo poll."""
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
    row = _fake_row(datetime.now(UTC).date() - timedelta(days=30))

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
