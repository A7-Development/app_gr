"""Coverage service — qual a saude historica de cada endpoint de uma fonte.

Pra cada endpoint daily/diario de uma source, retorna pros ultimos N dias:
- `ok`: linha raw com http_status=200 existe na data
- `not_published`: linha raw com http_status != 200 (4xx-as-row pattern do MEC)
- `weekend`/`holiday`: data sem expectativa (calendario ANBIMA)
- `gap`: dia util sem nenhuma linha raw — FURO REAL
- `pending`: data >= hoje (publicacao esperada mais tarde)
- `before_first_sync`: data anterior ao primeiro fetched_at do endpoint
  (sem expectativa — sync nao tinha sido configurado ainda)
- `unsupported`: endpoint nao tem layout 1-row-per-day (INTERVAL, ON_DEMAND)

A query usa `wh_dim_dia_util` (calendario ANBIMA) como referencia.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SourceType
from app.modules.integracoes.adapters.admin.qitech.coverage import (
    CoverageRow,
    fetch_qitech_coverage,
    fetch_qitech_first_data_date,
    qitech_endpoint_supports_coverage,
)
from app.modules.integracoes.public import endpoint_catalog
from app.shared.endpoint_catalog import EndpointSpec, ScheduleKind
from app.warehouse.dim_dia_util import DimDiaUtil


class CoverageStatus(StrEnum):
    OK = "ok"
    NOT_PUBLISHED = "not_published"
    GAP = "gap"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"
    PENDING = "pending"
    BEFORE_FIRST_SYNC = "before_first_sync"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class CoverageDay:
    data: date
    status: CoverageStatus
    http_status: int | None = None


@dataclass(frozen=True)
class EndpointCoverage:
    name: str
    label: str
    schedule_kind: str
    supported: bool
    days: list[CoverageDay]
    # Resumo agregado pra UI
    count_ok: int
    count_not_published: int
    count_gap: int


@dataclass(frozen=True)
class CoverageResponse:
    start_date: date
    end_date: date
    endpoints: list[EndpointCoverage]


async def _load_calendar(
    db: AsyncSession, tenant_id: UUID, start: date, end: date
) -> dict[date, tuple[bool, bool, bool]]:
    """Carrega o calendario ANBIMA para o range — 1 select, indexado em RAM.

    Retorna dict {data: (eh_dia_util, eh_fim_de_semana, eh_feriado)}.
    """
    stmt = select(
        DimDiaUtil.data,
        DimDiaUtil.eh_dia_util,
        DimDiaUtil.eh_fim_de_semana,
        DimDiaUtil.eh_feriado_nacional,
    ).where(
        DimDiaUtil.tenant_id == tenant_id,
        DimDiaUtil.data.between(start, end),
    )
    rows = (await db.execute(stmt)).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def _classify_day(
    day: date,
    today: date,
    raw_status: int | None,
    calendar_entry: tuple[bool, bool, bool] | None,
    first_data_in_endpoint: date | None,
) -> CoverageStatus:
    """Decide qual status atribuir a um dia, dadas as evidencias."""
    # 1. Data futura ou hoje — pendente (publicacao esperada mais tarde).
    if day >= today:
        return CoverageStatus.PENDING

    # 2. Tem linha raw — distingue ok vs not_published.
    if raw_status is not None:
        if 200 <= raw_status < 300:
            return CoverageStatus.OK
        return CoverageStatus.NOT_PUBLISHED

    # 3. Sem linha raw, anterior ao primeiro sync configurado — esperado vazio.
    if first_data_in_endpoint is not None and day < first_data_in_endpoint:
        return CoverageStatus.BEFORE_FIRST_SYNC

    # 4. Sem expectativa — fim de semana, feriado.
    if calendar_entry is not None:
        eh_dia_util, eh_fds, eh_feriado = calendar_entry
        if eh_feriado:
            return CoverageStatus.HOLIDAY
        if eh_fds:
            return CoverageStatus.WEEKEND
        if not eh_dia_util:
            # Bate-prevencao: calendario diz nao-util por outro motivo.
            return CoverageStatus.HOLIDAY

    # 5. Dia util sem linha — furo real.
    return CoverageStatus.GAP


async def _fetch_endpoint_rows(
    db: AsyncSession,
    *,
    source_type: SourceType,
    endpoint_name: str,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    start: date,
    end: date,
) -> list[CoverageRow]:
    """Dispatcher para o resolver do source — hoje so QiTech tem coverage."""
    if source_type == SourceType.ADMIN_QITECH:
        return await fetch_qitech_coverage(
            db,
            endpoint_name=endpoint_name,
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
            start_date=start,
            end_date=end,
        )
    return []


def _endpoint_supports_coverage(
    source_type: SourceType, spec: EndpointSpec
) -> bool:
    if source_type == SourceType.ADMIN_QITECH:
        return qitech_endpoint_supports_coverage(spec.name)
    return False


# Cap absoluto: mesmo "todo o periodo" nao mostra mais que isso, pra
# evitar DOM gigante no frontend (730 dias x 12 endpoints = ~8.7k celulas).
MAX_RANGE_DAYS = 730


async def _resolve_full_range_start(
    db: AsyncSession,
    *,
    source_type: SourceType,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    today: date,
) -> date:
    """Quando o caller pede 'todo o periodo', busca MIN(data) cross-endpoint
    e clampa em MAX_RANGE_DAYS. Fallback: 90 dias se nada existe."""
    first: date | None = None
    if source_type == SourceType.ADMIN_QITECH:
        first = await fetch_qitech_first_data_date(
            db,
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
        )
    if first is None:
        return today - timedelta(days=89)
    earliest_allowed = today - timedelta(days=MAX_RANGE_DAYS - 1)
    return max(first, earliest_allowed)


async def get_source_coverage(
    db: AsyncSession,
    *,
    source_type: SourceType,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    range_days: int | None,
) -> CoverageResponse:
    """Monta a cobertura cross-endpoint pra exibir no heatmap.

    `range_days=None` (ou 0) significa "todo o periodo desde o primeiro
    dado coletado" — cap em MAX_RANGE_DAYS.
    """
    today = datetime.now(UTC).date()
    end = today
    if range_days is None or range_days <= 0:
        start = await _resolve_full_range_start(
            db,
            source_type=source_type,
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
            today=today,
        )
    else:
        clamped = min(range_days, MAX_RANGE_DAYS)
        start = today - timedelta(days=clamped - 1)

    catalog = endpoint_catalog(source_type)
    calendar_map = await _load_calendar(db, tenant_id, start, end)

    endpoints_out: list[EndpointCoverage] = []
    for spec in catalog:
        if not _endpoint_supports_coverage(source_type, spec):
            endpoints_out.append(
                EndpointCoverage(
                    name=spec.name,
                    label=spec.label,
                    schedule_kind=spec.default_schedule_kind.value,
                    supported=False,
                    days=[],
                    count_ok=0,
                    count_not_published=0,
                    count_gap=0,
                )
            )
            continue

        raw_rows = await _fetch_endpoint_rows(
            db,
            source_type=source_type,
            endpoint_name=spec.name,
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
            start=start,
            end=end,
        )
        # Indexa por data
        raw_by_date: dict[date, int | None] = {r.data_posicao: r.http_status for r in raw_rows}
        first_data = min(raw_by_date.keys()) if raw_by_date else None

        days: list[CoverageDay] = []
        count_ok = count_not_pub = count_gap = 0
        cursor = start
        while cursor <= end:
            status = _classify_day(
                day=cursor,
                today=today,
                raw_status=raw_by_date.get(cursor),
                calendar_entry=calendar_map.get(cursor),
                first_data_in_endpoint=first_data,
            )
            days.append(
                CoverageDay(
                    data=cursor,
                    status=status,
                    http_status=raw_by_date.get(cursor),
                )
            )
            if status == CoverageStatus.OK:
                count_ok += 1
            elif status == CoverageStatus.NOT_PUBLISHED:
                count_not_pub += 1
            elif status == CoverageStatus.GAP:
                count_gap += 1
            cursor = cursor + timedelta(days=1)

        endpoints_out.append(
            EndpointCoverage(
                name=spec.name,
                label=spec.label,
                schedule_kind=spec.default_schedule_kind.value,
                supported=True,
                days=days,
                count_ok=count_ok,
                count_not_published=count_not_pub,
                count_gap=count_gap,
            )
        )

    return CoverageResponse(
        start_date=start,
        end_date=end,
        endpoints=endpoints_out,
    )


# Suprime warning de unused import (ScheduleKind eh re-exportado).
__all__ = [
    "CoverageDay",
    "CoverageResponse",
    "CoverageStatus",
    "EndpointCoverage",
    "ScheduleKind",
    "get_source_coverage",
]
