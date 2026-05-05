"""sync_dispatcher — logica de "deve disparar?" e isolamento por linha.

Testes unitarios: nao tocam DB nem APScheduler. Mocam:
  - list_enabled_configs (devolve as configs hipoteticas)
  - last_sync_attempt_at (devolve o timestamp da ultima tentativa)
  - run_sync_one (verifica que foi chamado com argumentos corretos)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.enums import Environment, SourceType
from app.scheduler import sync_dispatcher


def _make_cfg(
    *,
    sync_frequency_minutes: int | None,
    tenant_id=None,
    ua_id=None,
    last_sync_started_at=None,
):
    """Mock de TenantSourceConfig com so os campos que o dispatcher usa."""
    return SimpleNamespace(
        tenant_id=tenant_id or uuid4(),
        unidade_administrativa_id=ua_id,
        sync_frequency_minutes=sync_frequency_minutes,
        last_sync_started_at=last_sync_started_at,
    )


@pytest.fixture(autouse=True)
def _isolate_known_sources_cache():
    """Reset do cache de _known_sources entre testes — evita vazamento."""
    sync_dispatcher._KNOWN_SOURCES_CACHE = None
    yield
    sync_dispatcher._KNOWN_SOURCES_CACHE = None


@pytest.fixture(autouse=True)
def _isolate_inflight_keys():
    """Reset do lock in-flight entre testes — set global no modulo."""
    sync_dispatcher._INFLIGHT_KEYS.clear()
    yield
    sync_dispatcher._INFLIGHT_KEYS.clear()


async def _gather_pending_tasks() -> None:
    """Espera tasks de fundo (asyncio.create_task) terminarem."""
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_dispatch_quando_nunca_rodou() -> None:
    """last_sync_attempt_at=None -> dispara imediatamente."""
    cfg = _make_cfg(sync_frequency_minutes=30)

    # list_enabled_configs sera chamado 1x por (env, source_type). Mockamos
    # pra devolver a config so para BITFIN, vazio pros outros.
    async def fake_list_enabled(db, source_type, env):
        if source_type == SourceType.ERP_BITFIN:
            return [cfg]
        return []

    with (
        patch.object(
            sync_dispatcher, "list_enabled_configs", side_effect=fake_list_enabled
        ),
        patch.object(
            sync_dispatcher, "last_sync_attempt_at", new=AsyncMock(return_value=None)
        ),
        patch.object(
            sync_dispatcher, "run_sync_one", new=AsyncMock()
        ) as mock_run,
        patch.object(sync_dispatcher, "AsyncSessionLocal"),
    ):
        summary = await sync_dispatcher.run()
        await _gather_pending_tasks()

    assert summary["dispatched"] == 1
    assert summary["skipped_not_due"] == 0
    mock_run.assert_awaited_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs["environment"] == Environment.PRODUCTION
    assert kwargs["triggered_by"] == "system:scheduler"


@pytest.mark.asyncio
async def test_skip_quando_intervalo_nao_passou() -> None:
    """last_attempt foi ha 5 min e freq=30 -> nao dispara."""
    cfg = _make_cfg(sync_frequency_minutes=30)
    recent = datetime.now(UTC) - timedelta(minutes=5)

    async def fake_list_enabled(db, source_type, env):
        return [cfg] if source_type == SourceType.ERP_BITFIN else []

    with (
        patch.object(
            sync_dispatcher, "list_enabled_configs", side_effect=fake_list_enabled
        ),
        patch.object(
            sync_dispatcher,
            "last_sync_attempt_at",
            new=AsyncMock(return_value=recent),
        ),
        patch.object(
            sync_dispatcher, "run_sync_one", new=AsyncMock()
        ) as mock_run,
        patch.object(sync_dispatcher, "AsyncSessionLocal"),
    ):
        summary = await sync_dispatcher.run()
        await _gather_pending_tasks()

    assert summary["dispatched"] == 0
    assert summary["skipped_not_due"] == 1
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_quando_intervalo_passou() -> None:
    """last_attempt foi ha 35 min e freq=30 -> dispara."""
    cfg = _make_cfg(sync_frequency_minutes=30)
    old = datetime.now(UTC) - timedelta(minutes=35)

    async def fake_list_enabled(db, source_type, env):
        return [cfg] if source_type == SourceType.ERP_BITFIN else []

    with (
        patch.object(
            sync_dispatcher, "list_enabled_configs", side_effect=fake_list_enabled
        ),
        patch.object(
            sync_dispatcher,
            "last_sync_attempt_at",
            new=AsyncMock(return_value=old),
        ),
        patch.object(
            sync_dispatcher, "run_sync_one", new=AsyncMock()
        ) as mock_run,
        patch.object(sync_dispatcher, "AsyncSessionLocal"),
    ):
        summary = await sync_dispatcher.run()
        await _gather_pending_tasks()

    assert summary["dispatched"] == 1
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_ignora_config_com_freq_null() -> None:
    """sync_frequency_minutes=None significa sob demanda — dispatcher nao toca."""
    cfg = _make_cfg(sync_frequency_minutes=None)

    async def fake_list_enabled(db, source_type, env):
        return [cfg] if source_type == SourceType.BUREAU_SERASA_PJ else []

    with (
        patch.object(
            sync_dispatcher, "list_enabled_configs", side_effect=fake_list_enabled
        ),
        patch.object(
            sync_dispatcher, "last_sync_attempt_at", new=AsyncMock(return_value=None)
        ),
        patch.object(
            sync_dispatcher, "run_sync_one", new=AsyncMock()
        ) as mock_run,
        patch.object(sync_dispatcher, "AsyncSessionLocal"),
    ):
        summary = await sync_dispatcher.run()
        await _gather_pending_tasks()

    assert summary["dispatched"] == 0
    assert summary["configs_scanned"] == 1
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_isolamento_por_tenant_e_ua() -> None:
    """Multi-config: 2 tenants distintos com BITFIN configurado, ambos elegiveis,
    ambos disparados — cada um com seu tenant_id."""
    tenant_a = uuid4()
    tenant_b = uuid4()
    cfg_a = _make_cfg(sync_frequency_minutes=30, tenant_id=tenant_a)
    cfg_b = _make_cfg(sync_frequency_minutes=30, tenant_id=tenant_b)

    async def fake_list_enabled(db, source_type, env):
        return [cfg_a, cfg_b] if source_type == SourceType.ERP_BITFIN else []

    with (
        patch.object(
            sync_dispatcher, "list_enabled_configs", side_effect=fake_list_enabled
        ),
        patch.object(
            sync_dispatcher, "last_sync_attempt_at", new=AsyncMock(return_value=None)
        ),
        patch.object(
            sync_dispatcher, "run_sync_one", new=AsyncMock()
        ) as mock_run,
        patch.object(sync_dispatcher, "AsyncSessionLocal"),
    ):
        summary = await sync_dispatcher.run()
        await _gather_pending_tasks()

    assert summary["dispatched"] == 2
    assert mock_run.await_count == 2
    tenants_chamados = {c.args[0] for c in mock_run.call_args_list}
    assert tenants_chamados == {tenant_a, tenant_b}


@pytest.mark.asyncio
async def test_falha_de_uma_nao_quebra_outras() -> None:
    """run_sync_one falhar pra cfg_a nao impede dispatch de cfg_b."""
    cfg_a = _make_cfg(sync_frequency_minutes=30)
    cfg_b = _make_cfg(sync_frequency_minutes=30)

    async def fake_list_enabled(db, source_type, env):
        return [cfg_a, cfg_b] if source_type == SourceType.ERP_BITFIN else []

    async def flaky(*args, **kwargs):
        if args[0] == cfg_a.tenant_id:
            raise RuntimeError("upstream offline")
        return {"ok": True}

    with (
        patch.object(
            sync_dispatcher, "list_enabled_configs", side_effect=fake_list_enabled
        ),
        patch.object(
            sync_dispatcher, "last_sync_attempt_at", new=AsyncMock(return_value=None)
        ),
        patch.object(sync_dispatcher, "run_sync_one", side_effect=flaky),
        patch.object(sync_dispatcher, "AsyncSessionLocal"),
    ):
        summary = await sync_dispatcher.run()
        await _gather_pending_tasks()

    # Ambos foram disparados. A falha de cfg_a foi capturada por _run_one_safe.
    assert summary["dispatched"] == 2


@pytest.mark.asyncio
async def test_skip_quando_chave_em_flight() -> None:
    """Lock previne reentrada: se (tenant, source, ua) ja esta rodando,
    o tick subsequente nao dispara — espera proximo tick.

    Cenario: sync demora mais que o `sync_frequency_minutes`. Sem lock, o
    tick subsequente disparava paralela e saturava o thread pool. Esta era
    a causa raiz do deadlock no shutdown do uvicorn (worker zumbi 2026-05-05).
    """
    cfg = _make_cfg(sync_frequency_minutes=30)

    async def fake_list_enabled(db, source_type, env):
        return [cfg] if source_type == SourceType.ERP_BITFIN else []

    # Pre-popula a chave como "em voo" — simula sync anterior ainda rodando.
    sync_dispatcher._INFLIGHT_KEYS.add(
        (cfg.tenant_id, SourceType.ERP_BITFIN, cfg.unidade_administrativa_id)
    )

    with (
        patch.object(
            sync_dispatcher, "list_enabled_configs", side_effect=fake_list_enabled
        ),
        patch.object(
            sync_dispatcher, "last_sync_attempt_at", new=AsyncMock(return_value=None)
        ),
        patch.object(
            sync_dispatcher, "run_sync_one", new=AsyncMock()
        ) as mock_run,
        patch.object(sync_dispatcher, "AsyncSessionLocal"),
    ):
        summary = await sync_dispatcher.run()
        await _gather_pending_tasks()

    assert summary["dispatched"] == 0
    assert summary["skipped_in_flight"] == 1
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_skip_quando_started_at_recente_mesmo_sem_attempt() -> None:
    """`last_sync_started_at` na config bloqueia mesmo se decision_log estiver
    vazio (entry SYNC so e gravada no FIM, mas started_at e carimbado no inicio).

    Cobre o caso de operador admin disparando sync sob demanda em outro processo
    (API /integracoes/sources/{source}/sync) — `_mark_sync_started` no
    `sync_runner` carimba a config; tick do dispatcher neste processo deve
    respeitar.
    """
    recent_started = datetime.now(UTC) - timedelta(minutes=5)
    cfg = _make_cfg(
        sync_frequency_minutes=30, last_sync_started_at=recent_started
    )

    async def fake_list_enabled(db, source_type, env):
        return [cfg] if source_type == SourceType.ERP_BITFIN else []

    with (
        patch.object(
            sync_dispatcher, "list_enabled_configs", side_effect=fake_list_enabled
        ),
        patch.object(
            sync_dispatcher, "last_sync_attempt_at", new=AsyncMock(return_value=None)
        ),
        patch.object(
            sync_dispatcher, "run_sync_one", new=AsyncMock()
        ) as mock_run,
        patch.object(sync_dispatcher, "AsyncSessionLocal"),
    ):
        summary = await sync_dispatcher.run()
        await _gather_pending_tasks()

    assert summary["dispatched"] == 0
    assert summary["skipped_not_due"] == 1
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_libera_inflight_apos_task_terminar() -> None:
    """done_callback remove a chave do lock — proximo tick consegue dispatch."""
    cfg = _make_cfg(sync_frequency_minutes=30)

    async def fake_list_enabled(db, source_type, env):
        return [cfg] if source_type == SourceType.ERP_BITFIN else []

    with (
        patch.object(
            sync_dispatcher, "list_enabled_configs", side_effect=fake_list_enabled
        ),
        patch.object(
            sync_dispatcher, "last_sync_attempt_at", new=AsyncMock(return_value=None)
        ),
        patch.object(
            sync_dispatcher, "run_sync_one", new=AsyncMock()
        ),
        patch.object(sync_dispatcher, "AsyncSessionLocal"),
    ):
        summary = await sync_dispatcher.run()
        # No momento em que `run()` retorna, a task pode estar em flight ainda.
        assert summary["dispatched"] == 1
        key = (cfg.tenant_id, SourceType.ERP_BITFIN, cfg.unidade_administrativa_id)
        assert key in sync_dispatcher._INFLIGHT_KEYS

        # Espera task acabar -> done_callback dispara -> chave sai do set.
        await _gather_pending_tasks()
        assert key not in sync_dispatcher._INFLIGHT_KEYS
