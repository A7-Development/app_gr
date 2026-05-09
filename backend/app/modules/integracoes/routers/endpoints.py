"""HTTP endpoints para configuracao de cadencia POR ENDPOINT (per-endpoint).

Granularidade fina (CLAUDE.md §13 + plano refactor 2026-05-05):

- `GET  /integracoes/sources/{source_type}/endpoints` — lista endpoints do
  catalogo + override do tenant (joined). Inclui os ON_DEMAND.
- `GET  /integracoes/sources/{source_type}/endpoints/{name}` — detalhe single.
- `PUT  /integracoes/sources/{source_type}/endpoints/{name}` — atualiza
  enabled / schedule_kind / schedule_value. Validacao Pydantic espelha
  CHECK constraint do banco.
- `POST /integracoes/sources/{source_type}/endpoints/{name}/sync` — dispara
  sync sob demanda. Usa `run_sync_endpoint`.

Todos exigem `require_module(Module.INTEGRACOES, Permission.ADMIN)`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Environment, Module, Permission, SourceType
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
)
from app.modules.integracoes.public import (
    endpoint_catalog,
    list_endpoint_configs_for_source,
    run_sync_endpoint,
)
from app.shared.endpoint_catalog import EndpointSpec

router = APIRouter(prefix="/sources", tags=["integracoes:endpoints"])

_Guard = Depends(require_module(Module.INTEGRACOES, Permission.ADMIN))


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

ScheduleKindStr = Literal["interval", "daily_at", "on_demand"]


class EndpointDetail(BaseModel):
    """Endpoint do catalogo + (opcional) override persistido do tenant."""

    # Catalogo (sempre presente)
    name: str
    label: str
    description: str
    canonical_table: str
    default_schedule_kind: ScheduleKindStr
    default_schedule_value: str | None

    # Override do tenant (None se nunca foi persistida linha em TSEC)
    enabled: bool | None = None
    schedule_kind: ScheduleKindStr | None = None
    schedule_value: str | None = None
    last_sync_started_at: datetime | None = None
    last_sync_finished_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    unidade_administrativa_id: UUID | None = None


class EndpointConfigPayload(BaseModel):
    """PUT body — atualiza enabled / schedule_kind / schedule_value.

    Validacao espelha o CHECK constraint do banco
    (`ck_tsec_schedule_value_format`):
        - interval: schedule_value e int 15..1440 como string.
        - daily_at: schedule_value e HH:MM (24h, zero-padded).
        - on_demand: schedule_value tem que ser None.
    """

    enabled: bool | None = None
    schedule_kind: ScheduleKindStr
    schedule_value: str | None = None
    environment: Environment = Environment.PRODUCTION
    unidade_administrativa_id: UUID | None = None

    @field_validator("schedule_value")
    @classmethod
    def _validate_value(cls, v: str | None, info: Any) -> str | None:
        kind = info.data.get("schedule_kind")
        if kind == "on_demand":
            if v is not None:
                raise ValueError("on_demand exige schedule_value=null")
            return None
        if kind == "interval":
            if v is None or not v.isdigit():
                raise ValueError("interval exige schedule_value como inteiro de minutos")
            n = int(v)
            if not (15 <= n <= 1440):
                raise ValueError("interval requer schedule_value entre 15 e 1440")
            return v
        if kind == "daily_at":
            if v is None or len(v) != 5 or v[2] != ":":
                raise ValueError("daily_at exige schedule_value HH:MM (ex.: '07:30')")
            try:
                hh = int(v[:2])
                mm = int(v[3:])
            except ValueError as e:
                raise ValueError("daily_at HH:MM invalido") from e
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError("daily_at HH:MM fora do range 00:00..23:59")
            return v
        return v


class EndpointSyncResult(BaseModel):
    """Retorno de POST /sync — summary do ciclo do endpoint."""

    ok: bool
    adapter_version: str | None = None
    endpoint_name: str
    started_at: str | None = None
    elapsed_seconds: float | None = None
    rows_ingested: int = 0
    steps: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _spec_to_detail(spec: EndpointSpec) -> EndpointDetail:
    return EndpointDetail(
        name=spec.name,
        label=spec.label,
        description=spec.description,
        canonical_table=spec.canonical_table,
        default_schedule_kind=spec.default_schedule_kind.value,  # type: ignore[arg-type]
        default_schedule_value=spec.default_schedule_value,
    )


def _merge_override(
    detail: EndpointDetail, row: TenantSourceEndpointConfig
) -> EndpointDetail:
    """Sobrepoe campos do TSEC no detail base do catalogo."""
    return detail.model_copy(
        update={
            "enabled": row.enabled,
            "schedule_kind": row.schedule_kind,  # type: ignore[arg-type]
            "schedule_value": row.schedule_value,
            "last_sync_started_at": row.last_sync_started_at,
            "last_sync_finished_at": row.last_sync_finished_at,
            "last_sync_status": row.last_sync_status,
            "last_sync_error": row.last_sync_error,
            "unidade_administrativa_id": row.unidade_administrativa_id,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{source_type}/endpoints",
    response_model=list[EndpointDetail],
)
async def list_endpoints(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    unidade_administrativa_id: Annotated[UUID | None, Query(alias="ua")] = None,
    _: None = _Guard,
) -> list[EndpointDetail]:
    """Lista endpoints do catalogo + override do tenant.

    Sempre retorna 1 entry por endpoint do catalogo. Se TSEC tem linha pra
    aquele (tenant, source, env, ua, endpoint), os campos override sao
    preenchidos; senao ficam None (caller sabe que e default do catalogo).
    """
    catalog = endpoint_catalog(source_type)
    if not catalog:
        return []

    overrides = await list_endpoint_configs_for_source(
        db,
        tenant_id=principal.tenant_id,
        source_type=source_type,
        environment=environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )
    overrides_by_name = {row.endpoint_name: row for row in overrides}

    out: list[EndpointDetail] = []
    for spec in catalog:
        detail = _spec_to_detail(spec)
        if spec.name in overrides_by_name:
            detail = _merge_override(detail, overrides_by_name[spec.name])
        out.append(detail)
    return out


@router.get(
    "/{source_type}/endpoints/{endpoint_name:path}",
    response_model=EndpointDetail,
)
async def get_endpoint(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    endpoint_name: Annotated[str, Path()],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    unidade_administrativa_id: Annotated[UUID | None, Query(alias="ua")] = None,
    _: None = _Guard,
) -> EndpointDetail:
    """Detalhe de um endpoint especifico (catalogo + override)."""
    catalog = endpoint_catalog(source_type)
    spec = next((ep for ep in catalog if ep.name == endpoint_name), None)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Endpoint '{endpoint_name}' nao existe no catalogo de "
                f"{source_type.value}."
            ),
        )
    detail = _spec_to_detail(spec)

    stmt = select(TenantSourceEndpointConfig).where(
        TenantSourceEndpointConfig.tenant_id == principal.tenant_id,
        TenantSourceEndpointConfig.source_type == source_type,
        TenantSourceEndpointConfig.environment == environment,
        TenantSourceEndpointConfig.endpoint_name == endpoint_name,
    )
    if unidade_administrativa_id is None:
        stmt = stmt.where(TenantSourceEndpointConfig.unidade_administrativa_id.is_(None))
    else:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id == unidade_administrativa_id
        )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is not None:
        detail = _merge_override(detail, row)
    return detail


@router.put(
    "/{source_type}/endpoints/{endpoint_name:path}",
    response_model=EndpointDetail,
)
async def update_endpoint(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    endpoint_name: Annotated[str, Path()],
    payload: EndpointConfigPayload,
    _: None = _Guard,
) -> EndpointDetail:
    """Atualiza schedule_kind / schedule_value / enabled de um endpoint.

    Upsert — cria linha em TSEC se nao existe, senao atualiza. Validacao
    Pydantic ja garantiu coerencia (kind, value) antes de bater no Postgres.
    """
    catalog = endpoint_catalog(source_type)
    spec = next((ep for ep in catalog if ep.name == endpoint_name), None)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Endpoint '{endpoint_name}' nao existe no catalogo de "
                f"{source_type.value}."
            ),
        )

    stmt = select(TenantSourceEndpointConfig).where(
        TenantSourceEndpointConfig.tenant_id == principal.tenant_id,
        TenantSourceEndpointConfig.source_type == source_type,
        TenantSourceEndpointConfig.environment == payload.environment,
        TenantSourceEndpointConfig.endpoint_name == endpoint_name,
    )
    if payload.unidade_administrativa_id is None:
        stmt = stmt.where(TenantSourceEndpointConfig.unidade_administrativa_id.is_(None))
    else:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id == payload.unidade_administrativa_id
        )
    row = (await db.execute(stmt)).scalar_one_or_none()

    if row is None:
        row = TenantSourceEndpointConfig(
            tenant_id=principal.tenant_id,
            source_type=source_type,
            environment=payload.environment,
            unidade_administrativa_id=payload.unidade_administrativa_id,
            endpoint_name=endpoint_name,
            enabled=True if payload.enabled is None else payload.enabled,
            schedule_kind=payload.schedule_kind,
            schedule_value=payload.schedule_value,
        )
        db.add(row)
    else:
        if payload.enabled is not None:
            row.enabled = payload.enabled
        row.schedule_kind = payload.schedule_kind
        row.schedule_value = payload.schedule_value
    await db.commit()
    await db.refresh(row)

    detail = _merge_override(_spec_to_detail(spec), row)
    return detail


@router.post(
    "/{source_type}/endpoints/{endpoint_name:path}/sync",
    response_model=EndpointSyncResult,
)
async def sync_endpoint(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    source_type: Annotated[SourceType, Path()],
    endpoint_name: Annotated[str, Path()],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    unidade_administrativa_id: Annotated[UUID | None, Query(alias="ua")] = None,
    _: None = _Guard,
) -> EndpointSyncResult:
    """Dispara sync sob demanda de UM endpoint. Sincronia (espera retorno).

    Levanta 404 se endpoint nao esta no catalogo. Levanta 422 se tenant nao
    tem TSC pra source (precisa configurar credenciais primeiro).
    """
    catalog = endpoint_catalog(source_type)
    if not any(ep.name == endpoint_name for ep in catalog):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Endpoint '{endpoint_name}' nao existe no catalogo de "
                f"{source_type.value}."
            ),
        )

    try:
        summary = await run_sync_endpoint(
            principal.tenant_id,
            source_type,
            endpoint_name,
            environment=environment,
            triggered_by=f"user:{principal.user_id}",
            unidade_administrativa_id=unidade_administrativa_id,
        )
    except ValueError as e:
        # run_sync_endpoint levanta ValueError quando TSC ausente.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    return EndpointSyncResult(
        ok=bool(summary.get("ok")),
        adapter_version=summary.get("adapter_version"),
        endpoint_name=endpoint_name,
        started_at=summary.get("started_at"),
        elapsed_seconds=summary.get("elapsed_seconds"),
        rows_ingested=int(summary.get("rows_ingested") or 0),
        steps=summary.get("steps") or [],
        errors=summary.get("errors") or [],
    )
