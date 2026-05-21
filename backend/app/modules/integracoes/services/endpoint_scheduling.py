"""Endpoint scheduling helpers — used by `sync_dispatcher` modo per-endpoint.

Quando `INTEGRACOES_USE_ENDPOINT_SCHEDULING=True`, o dispatcher chama
`list_due_endpoints(db, now)` a cada tick para pegar quais TSEC linhas
estao "due" (passaram o intervalo, ou cruzaram o HH:MM do daily_at).

Logica due:
    - `interval`: now - last_sync_started_at >= timedelta(minutes=value),
      OU last_sync_started_at IS NULL (nunca rodou).
    - `daily_at`: hoje em SP passou de HH:MM (now SP >= today SP HH:MM)
      AND last_sync_started_at < hoje SP 00:00 (nao rodou hoje ainda).
    - `on_demand`: nunca aparece — caller filtra na query.

Multi-UA caveat (mesmo do modo legado): lock in-flight do dispatcher e
in-memory + last_sync_started_at SQL evitam reentrada. Linha em
`em_progresso` ha mais de 2h e flagada como zumbi (ver
`is_likely_zombie_sync`) — dispatcher pode optar por pular ou disparar
de novo.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Environment, SourceType
from app.modules.integracoes.models.endpoint_date_state import EndpointDateState
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
)
from app.modules.integracoes.services.endpoint_routing import (
    is_state_machine_enabled,
)

# Timezone do schedule daily_at — todos os HH:MM viajam em America/Sao_Paulo
# (alinhado com o scheduler em `app/scheduler/scheduler.py`).
SP_TZ = ZoneInfo("America/Sao_Paulo")

# Timeout de sync zumbi — `last_sync_status='em_progresso'` ha mais de N
# horas considera zombi. Default 2h cobre 99% dos casos sem ficar agressivo
# (sync de Bitfin pode levar 30-60min em volume grande).
ZOMBIE_SYNC_HOURS = 2


def _is_due_interval(
    *,
    schedule_value: str,
    last_started_at: datetime | None,
    now: datetime,
) -> bool:
    """Interval e 'a cada N min'. Roda se nunca rodou ou se passou o intervalo."""
    if last_started_at is None:
        return True
    minutes = int(schedule_value)
    return (now - last_started_at) >= timedelta(minutes=minutes)


def _is_due_daily_at(
    *,
    schedule_value: str,
    last_started_at: datetime | None,
    now: datetime,
) -> bool:
    """daily_at HH:MM em SP. Roda se hoje SP passou do HH:MM AND nao rodou
    hoje ainda."""
    now_sp = now.astimezone(SP_TZ)
    today_sp = now_sp.date()

    hh, mm = schedule_value.split(":")
    target_today_sp = datetime.combine(
        today_sp, time(hour=int(hh), minute=int(mm)), tzinfo=SP_TZ
    )
    if now_sp < target_today_sp:
        return False  # ainda nao chegou no horario

    # Passou o horario. Ja rodou hoje?
    if last_started_at is None:
        return True
    last_sp = last_started_at.astimezone(SP_TZ)
    return last_sp.date() < today_sp


def _is_likely_zombie(
    *,
    last_status: str | None,
    last_started_at: datetime | None,
    now: datetime,
) -> bool:
    """Sync com last_sync_status='em_progresso' ha > ZOMBIE_SYNC_HOURS e
    suspeito de ter morrido (kill -9, OOM, deploy no meio do ciclo). Caller
    decide se dispara de novo OU pula por seguranca."""
    if last_status != "em_progresso":
        return False
    if last_started_at is None:
        return False
    return (now - last_started_at) >= timedelta(hours=ZOMBIE_SYNC_HOURS)


async def list_due_endpoints(
    db: AsyncSession,
    *,
    now: datetime,
    environments: tuple[Environment, ...] = (Environment.PRODUCTION,),
) -> list[TenantSourceEndpointConfig]:
    """Retorna TSEC linhas que estao due para sincronizar AGORA.

    Filtros:
        - enabled=True
        - environment in environments
        - schedule_kind != 'on_demand'
        - schedule logic (interval/daily_at) acha que e hora de rodar

    Filtra zombies em-progresso ha menos de ZOMBIE_SYNC_HOURS — sync de fato
    ainda rodando, nao dispara em paralelo. Em-progresso ha mais de 2h passa
    a ser tratado como tentativa expirada (libera novo dispatch).
    """
    stmt = select(TenantSourceEndpointConfig).where(
        TenantSourceEndpointConfig.enabled.is_(True),
        TenantSourceEndpointConfig.environment.in_(environments),
        TenantSourceEndpointConfig.schedule_kind != "on_demand",
    )
    result = await db.execute(stmt)
    rows: list[TenantSourceEndpointConfig] = list(result.scalars().all())

    due: list[TenantSourceEndpointConfig] = []
    for row in rows:
        # State machine gate (F3, 2026-05-21): endpoints com
        # `state_machine_enabled=True` no catalogo sao processados pelo
        # `state_machine_dispatcher` — caminho legado pula pra nao causar
        # double-fetch (rate limit + custo duplicado).
        if is_state_machine_enabled(row.source_type, row.endpoint_name):
            continue

        # Zombi vivo: em_progresso recente — pula (sync ainda em curso).
        if (
            row.last_sync_status == "em_progresso"
            and row.last_sync_started_at is not None
            and not _is_likely_zombie(
                last_status=row.last_sync_status,
                last_started_at=row.last_sync_started_at,
                now=now,
            )
        ):
            continue

        # Outros kinds nao previstos sao ignorados (Postgres CHECK ja
        # blocked, mas defesa em profundidade).
        is_due = (
            row.schedule_kind == "interval"
            and _is_due_interval(
                schedule_value=row.schedule_value or "0",
                last_started_at=row.last_sync_started_at,
                now=now,
            )
        ) or (
            row.schedule_kind == "daily_at"
            and _is_due_daily_at(
                schedule_value=row.schedule_value or "00:00",
                last_started_at=row.last_sync_started_at,
                now=now,
            )
        )
        if is_due:
            due.append(row)

    return due


def compute_next_sync_legacy(
    *,
    schedule_kind: str | None,
    schedule_value: str | None,
    last_started_at: datetime | None,
    now: datetime,
) -> datetime | None:
    """Proximo sync esperado para endpoint NO REGIME LEGADO.

    Para endpoints em `state_machine_enabled=True`, use
    `load_state_machine_next_attempts` — o "proximo" la e MIN(next_attempt_at)
    em endpoint_date_state, nao derivado de schedule.

    Regras:
        - `on_demand` ou kind ausente: None (sem agendamento automatico).
        - `interval`: max(last_started_at + minutes, now).
        - `daily_at`: hoje SP HH:MM se ainda nao rodou hoje, senao amanha SP HH:MM.

    Retorna datetime em UTC.
    """
    if schedule_kind == "on_demand" or schedule_kind is None:
        return None
    if not schedule_value:
        return None

    if schedule_kind == "interval":
        try:
            minutes = int(schedule_value)
        except ValueError:
            return None
        if last_started_at is None:
            return now
        candidate = last_started_at + timedelta(minutes=minutes)
        # Se o intervalo ja passou, proximo tick processa agora.
        return max(candidate, now)

    if schedule_kind == "daily_at":
        try:
            hh, mm = schedule_value.split(":")
            target_time = time(hour=int(hh), minute=int(mm))
        except (ValueError, TypeError):
            return None
        now_sp = now.astimezone(SP_TZ)
        today_sp = now_sp.date()
        target_today_sp = datetime.combine(today_sp, target_time, tzinfo=SP_TZ)
        # Ja rodou hoje? proximo e amanha SP HH:MM.
        if last_started_at is not None:
            last_sp = last_started_at.astimezone(SP_TZ)
            if last_sp.date() >= today_sp:
                target_tomorrow_sp = target_today_sp + timedelta(days=1)
                return target_tomorrow_sp.astimezone(now.tzinfo or SP_TZ)
        # Nao rodou hoje. Se o horario ja passou, eh agora; senao, hoje SP HH:MM.
        if now_sp >= target_today_sp:
            return now
        return target_today_sp.astimezone(now.tzinfo or SP_TZ)

    return None


async def load_state_machine_next_attempts(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment,
    unidade_administrativa_id: UUID | None,
    endpoint_names: list[str],
) -> dict[str, datetime | None]:
    """MIN(next_attempt_at) por endpoint em `endpoint_date_state`, filtrado
    a TRABALHO PENDENTE REAL.

    Considera apenas datas em estados RETENTAVEIS (not_started, empty,
    partial, not_published) — i.e., quando o sistema realmente precisa
    sincronizar algo que ainda nao deu certo.

    NAO inclui:
    - `complete`: TTL de refresh-complete (re-fetch silencioso pra detectar
      republicacao). E proxima chamada a API, sim, mas a UI ficava confusa
      ("se deu certo, por que vai tentar de novo?"). UI cai no fallback
      do schedule (`compute_next_sync_legacy`) que mostra a proxima janela
      programada do daily_at, mais legivel.
    - `in_flight`: workers ja estao processando.
    - `abandoned`: terminal, sistema desistiu.

    Retorna dict {endpoint_name -> proxima_data}. Endpoints sem trabalho
    pendente ficam ausentes do dict — caller cai no schedule do TSEC.
    """
    if not endpoint_names:
        return {}
    stmt = (
        select(
            EndpointDateState.endpoint_name,
            func.min(EndpointDateState.next_attempt_at).label("next_attempt"),
        )
        .where(
            EndpointDateState.tenant_id == tenant_id,
            EndpointDateState.source_type == source_type,
            EndpointDateState.environment == environment,
            EndpointDateState.endpoint_name.in_(endpoint_names),
            EndpointDateState.next_attempt_at.is_not(None),
            EndpointDateState.state.in_(
                ("not_started", "empty", "partial", "not_published")
            ),
        )
        .group_by(EndpointDateState.endpoint_name)
    )
    if unidade_administrativa_id is None:
        stmt = stmt.where(EndpointDateState.unidade_administrativa_id.is_(None))
    else:
        stmt = stmt.where(
            EndpointDateState.unidade_administrativa_id == unidade_administrativa_id
        )
    rows = (await db.execute(stmt)).all()
    return {row[0]: row[1] for row in rows}


async def list_endpoint_configs_for_source(
    db: AsyncSession,
    *,
    tenant_id: Any,
    source_type: Any,
    environment: Environment = Environment.PRODUCTION,
    unidade_administrativa_id: Any = None,
) -> list[TenantSourceEndpointConfig]:
    """Lista todas as linhas TSEC de uma fonte para uma config de tenant
    (incluindo on_demand). Usado pela API GET /sources/{source}/endpoints.
    """
    stmt = select(TenantSourceEndpointConfig).where(
        TenantSourceEndpointConfig.tenant_id == tenant_id,
        TenantSourceEndpointConfig.source_type == source_type,
        TenantSourceEndpointConfig.environment == environment,
    )
    if unidade_administrativa_id is None:
        stmt = stmt.where(TenantSourceEndpointConfig.unidade_administrativa_id.is_(None))
    else:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id == unidade_administrativa_id
        )
    stmt = stmt.order_by(TenantSourceEndpointConfig.endpoint_name)
    result = await db.execute(stmt)
    return list(result.scalars().all())
