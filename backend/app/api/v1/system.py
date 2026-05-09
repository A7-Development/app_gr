"""System-level endpoints (cross-cutting, non-module).

Exposes pipeline health so the frontend can surface "is data flowing" e
"qual a proxima execucao prevista" independente de filtros de dashboard.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Environment, SourceType
from app.core.system_health_guard import require_system_health_token
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
)
from app.modules.integracoes.public import rule_name_for
from app.modules.integracoes.services.source_config import list_configs
from app.shared.audit_log.sync_health import last_sync_at, last_sync_attempt_at
from app.shared.catalog.source_catalog import SourceCatalog

router = APIRouter(prefix="/system", tags=["system"])


# Quando `now - last_sync_at` ultrapassa `freq * DELAY_FACTOR`, marcamos
# "delayed". 1.5 da uma janela de tolerancia (sync as vezes derrapa por
# segundos por concorrencia ou fila lenta) sem virar alarme falso.
_DELAY_FACTOR = 1.5


class SyncHealthStatus(StrEnum):
    """Estado da pipeline para uma fonte habilitada do tenant.

    - ok: ultimo sync OK aconteceu dentro da janela esperada (freq * 1.5).
    - delayed: passou da janela — scheduler parado, falhas em loop, ou
      upstream offline. UI pinta badge ambar.
    - stale: enabled + freq configurada mas nunca rodou (config recente
      sem ciclo ainda).
    - on_demand: enabled mas sem freq — fonte so roda manualmente
      (ex.: bureau Serasa via workflow do credito).
    - disabled: linha existe mas enabled=false (fonte parada).
    """

    OK = "ok"
    DELAYED = "delayed"
    STALE = "stale"
    ON_DEMAND = "on_demand"
    DISABLED = "disabled"


class SyncHealthEntry(BaseModel):
    """Snapshot de uma linha (tenant, source, ua) com saude calculada."""

    source_type: SourceType
    label: str
    enabled: bool
    sync_frequency_minutes: int | None = Field(
        default=None,
        description="null = sob demanda (sem agendamento).",
    )
    last_sync_at: datetime | None = Field(
        default=None,
        description="Ultimo SYNC OK (decision_log.explanation='OK').",
    )
    last_attempt_at: datetime | None = Field(
        default=None,
        description="Ultima tentativa SYNC (qualquer status — pra detectar retry em loop).",
    )
    expected_next_at: datetime | None = Field(
        default=None,
        description="Quando o dispatcher deve disparar o proximo ciclo. null pra on_demand.",
    )
    status: SyncHealthStatus
    unidade_administrativa_id: str | None = None


def _compute_status(
    *,
    enabled: bool,
    freq_minutes: int | None,
    last_ok: datetime | None,
    now: datetime,
) -> SyncHealthStatus:
    if not enabled:
        return SyncHealthStatus.DISABLED
    if freq_minutes is None:
        return SyncHealthStatus.ON_DEMAND
    if last_ok is None:
        return SyncHealthStatus.STALE
    threshold = timedelta(minutes=freq_minutes * _DELAY_FACTOR)
    if (now - last_ok) > threshold:
        return SyncHealthStatus.DELAYED
    return SyncHealthStatus.OK


@router.get("/sync-health", response_model=list[SyncHealthEntry])
async def sync_health(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    environment: Environment = Environment.PRODUCTION,
) -> list[SyncHealthEntry]:
    """Saude de cada fonte configurada para o tenant atual.

    Inclui apenas fontes que tem linha em `tenant_source_config` (configurada
    ou nao). Fontes do catalogo nunca cadastradas pelo tenant nao aparecem —
    use /integracoes/sources para descobrir o que existe.

    Public-fonte-FDW (CVM, Bacen) nao listada aqui — ingestao vive em repos
    separados sem decision_log.
    """
    now = datetime.now(UTC)
    out: list[SyncHealthEntry] = []

    catalog: dict[SourceType, SourceCatalog] = {}
    from sqlalchemy import select

    rows = (await db.execute(select(SourceCatalog))).scalars().all()
    for r in rows:
        catalog[r.source_type] = r

    for source_type, cat in catalog.items():
        rule = rule_name_for(source_type)
        if rule is None:
            continue
        configs = await list_configs(
            db, principal.tenant_id, source_type, environment
        )
        if not configs:
            continue

        last_ok = await last_sync_at(
            db, principal.tenant_id, rule_or_model=rule
        )
        last_attempt = await last_sync_attempt_at(
            db, principal.tenant_id, rule_or_model=rule
        )

        for cfg in configs:
            status = _compute_status(
                enabled=cfg.enabled,
                freq_minutes=cfg.sync_frequency_minutes,
                last_ok=last_ok,
                now=now,
            )
            expected_next = None
            if (
                cfg.enabled
                and cfg.sync_frequency_minutes is not None
                and last_attempt is not None
            ):
                expected_next = last_attempt + timedelta(
                    minutes=cfg.sync_frequency_minutes
                )

            out.append(
                SyncHealthEntry(
                    source_type=source_type,
                    label=cat.label,
                    enabled=cfg.enabled,
                    sync_frequency_minutes=cfg.sync_frequency_minutes,
                    last_sync_at=last_ok,
                    last_attempt_at=last_attempt,
                    expected_next_at=expected_next,
                    status=status,
                    unidade_administrativa_id=(
                        str(cfg.unidade_administrativa_id)
                        if cfg.unidade_administrativa_id
                        else None
                    ),
                )
            )

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint publico de monitoramento (auth por Bearer token de servico)
# ─────────────────────────────────────────────────────────────────────────────


class EndpointSyncStatusEntry(BaseModel):
    """Snapshot operacional de uma linha de TSEC.

    Cross-tenant — exposto para monitoramento externo (rotinas /schedule no
    Anthropic Cloud, uptime monitors). Sem JWT; auth via Bearer token de
    servico (SYSTEM_HEALTH_TOKEN). Read-only.
    """

    tenant_id: str
    source_type: SourceType
    environment: Environment
    unidade_administrativa_id: str | None
    endpoint_name: str
    enabled: bool
    schedule_kind: str = Field(description="interval | daily_at | on_demand")
    schedule_value: str | None
    last_sync_started_at: datetime | None
    last_sync_finished_at: datetime | None
    last_sync_status: str | None = Field(
        description="ok | erro | em_progresso | null (nunca rodou)"
    )
    last_sync_error: str | None


@router.get(
    "/endpoint-sync-status",
    response_model=list[EndpointSyncStatusEntry],
    summary="Snapshot operacional de tenant_source_endpoint_config (cross-tenant)",
)
async def endpoint_sync_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(require_system_health_token)],
) -> list[EndpointSyncStatusEntry]:
    """Cross-tenant snapshot da TSEC pra monitoramento externo.

    Auth: Bearer token via header `Authorization: Bearer <SYSTEM_HEALTH_TOKEN>`.
    Sem JWT. Sem escopo de tenant (excecao explicita ao multi-tenancy de
    CLAUDE.md §10 — endpoint operacional, nao de dominio).

    Use cases:
        - Rotinas /schedule cloud validando que daily_at endpoints disparam
          na janela natural (ex.: amanha 07-09h SP).
        - Uptime monitors externos (Pingdom, BetterStack) alertando quando
          last_sync_status='erro' ou last_sync_started_at envelhece.
        - Dashboard de saude operacional independente do app.

    Retorna **todas** as linhas de TSEC. Caller filtra/agrega como precisar.
    """
    from sqlalchemy import select

    stmt = select(TenantSourceEndpointConfig).order_by(
        TenantSourceEndpointConfig.source_type,
        TenantSourceEndpointConfig.endpoint_name,
        TenantSourceEndpointConfig.tenant_id,
    )
    rows = (await db.execute(stmt)).scalars().all()

    return [
        EndpointSyncStatusEntry(
            tenant_id=str(r.tenant_id),
            source_type=r.source_type,
            environment=r.environment,
            unidade_administrativa_id=(
                str(r.unidade_administrativa_id)
                if r.unidade_administrativa_id
                else None
            ),
            endpoint_name=r.endpoint_name,
            enabled=r.enabled,
            schedule_kind=r.schedule_kind,
            schedule_value=r.schedule_value,
            last_sync_started_at=r.last_sync_started_at,
            last_sync_finished_at=r.last_sync_finished_at,
            last_sync_status=r.last_sync_status,
            last_sync_error=r.last_sync_error,
        )
        for r in rows
    ]
