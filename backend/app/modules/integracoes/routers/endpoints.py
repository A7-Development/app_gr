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

from datetime import UTC, date, datetime
from decimal import Decimal
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
from app.modules.integracoes.services.backfill_service import (
    cancel_backfill_job,
    create_backfill_job,
    get_backfill_job,
    list_active_backfill_jobs,
    resolve_backfill_ua,
)
from app.modules.integracoes.services.coverage import (
    CoverageStatus,
    PublicationState,
    get_source_coverage,
)
from app.modules.integracoes.services.endpoint_routing import (
    is_state_machine_enabled,
)
from app.modules.integracoes.services.endpoint_scheduling import (
    compute_next_sync_legacy,
    load_state_machine_next_attempts,
)
from app.modules.integracoes.services.source_config import list_configs
from app.modules.integracoes.services.tolerance import resolve_tolerance_window
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

    # Identidade cross-admin / cross-tenant (Fase 1 do refactor de proveniencia
    # transversal, 2026-05-18). admin_code e global_id sao derivados do
    # EndpointSpec; tenant_endpoint_handle e derivado no handler (precisa do
    # tenant.slug). Ver CLAUDE.md §14.
    admin_code: str
    global_id: str
    tenant_endpoint_handle: str
    # Doc do shape do payload (Fase 2, 2026-05-18). Path relativo a raiz do
    # repo. None = adapter ainda nao publicou catalogo de shapes. UI admin
    # consome pra abrir doc in-line.
    payload_shape_doc_relpath: str | None = None

    # Tolerancia de publicacao — defaults sempre presentes do catalogo.
    default_expected_lag_business_days: int
    default_tolerance_business_days: int
    default_give_up_business_days: int

    # Override do tenant (None se nunca foi persistida linha em TSEC)
    enabled: bool | None = None
    schedule_kind: ScheduleKindStr | None = None
    schedule_value: str | None = None
    last_sync_started_at: datetime | None = None
    last_sync_finished_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    unidade_administrativa_id: UUID | None = None

    # Tolerancia — overrides (NULL = "segue default").
    expected_lag_business_days_override: int | None = None
    tolerance_business_days_override: int | None = None
    give_up_business_days_override: int | None = None

    # Valores efetivos = override OR default — facilita renderizacao na UI
    # (sem ter que recombinar no cliente). Sempre preenchidos.
    effective_expected_lag_business_days: int
    effective_tolerance_business_days: int
    effective_give_up_business_days: int

    # Proximo sync agendado (UTC). Fonte da informacao:
    # - Endpoints `state_machine_enabled=True`: MIN(next_attempt_at) de
    #   endpoint_date_state — cobre proxima retentativa adaptativa + TTL
    #   de refresh-complete.
    # - Endpoints legados: derivado de schedule_kind/value + last_sync_started_at
    #   (proximo HH:MM do daily_at ou last + intervalo do interval).
    # - on_demand ou nunca configurado: None.
    next_sync_at: datetime | None = None
    next_sync_source: Literal["state_machine", "schedule", "manual_only"] | None = (
        None
    )


class EndpointConfigPayload(BaseModel):
    """PUT body — atualiza enabled / schedule_kind / schedule_value + tolerancia.

    Validacao espelha o CHECK constraint do banco
    (`ck_tsec_schedule_value_format`):
        - interval: schedule_value e int 15..1440 como string.
        - daily_at: schedule_value e HH:MM (24h, zero-padded).
        - on_demand: schedule_value tem que ser None.

    Para tolerance:
        - Cada campo pode vir como int >= 0 (override) ou null (segue default).
        - Coerencia (expected <= tolerance <= give_up) e validada apos a
          composicao com defaults do catalogo no handler (nao aqui — o
          payload nao conhece os defaults).
    """

    enabled: bool | None = None
    schedule_kind: ScheduleKindStr
    schedule_value: str | None = None
    environment: Environment = Environment.PRODUCTION
    unidade_administrativa_id: UUID | None = None

    # Tolerancia — null = "limpar override e voltar a herdar do catalogo".
    expected_lag_business_days_override: int | None = Field(
        default=None, ge=0, le=30
    )
    tolerance_business_days_override: int | None = Field(
        default=None, ge=0, le=60
    )
    give_up_business_days_override: int | None = Field(
        default=None, ge=0, le=120
    )

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


async def _resolve_tenant_slug(db: AsyncSession, tenant_id: UUID) -> str:
    """Carrega tenant.slug 1x por request pra montar tenant_endpoint_handle.

    Slug e curto (max 100 chars), indexed, e nao muda durante a vida do
    tenant — uma query simples e suficiente. NAO cacheia em modulo: tenants
    podem ser renomeados administrativamente e cache ficaria stale.
    """
    from app.shared.identity.tenant import Tenant

    row = await db.execute(select(Tenant.slug).where(Tenant.id == tenant_id))
    slug = row.scalar_one_or_none()
    if slug is None:
        # Defesa: nao deveria acontecer (principal vem do JWT validado), mas
        # se rolar, melhor 422 explicito que stack trace silencioso.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tenant {tenant_id} nao encontrado.",
        )
    return slug


def _spec_to_detail(spec: EndpointSpec, tenant_slug: str) -> EndpointDetail:
    # Sem override: effective_* = default_*.
    return EndpointDetail(
        name=spec.name,
        label=spec.label,
        description=spec.description,
        canonical_table=spec.canonical_table,
        default_schedule_kind=spec.default_schedule_kind.value,  # type: ignore[arg-type]
        default_schedule_value=spec.default_schedule_value,
        admin_code=spec.admin_code,
        global_id=spec.global_id,
        tenant_endpoint_handle=spec.tenant_endpoint_handle(tenant_slug),
        payload_shape_doc_relpath=spec.payload_shape_doc_relpath,
        default_expected_lag_business_days=spec.default_expected_lag_business_days,
        default_tolerance_business_days=spec.default_tolerance_business_days,
        default_give_up_business_days=spec.default_give_up_business_days,
        effective_expected_lag_business_days=spec.default_expected_lag_business_days,
        effective_tolerance_business_days=spec.default_tolerance_business_days,
        effective_give_up_business_days=spec.default_give_up_business_days,
    )


def _merge_override(
    detail: EndpointDetail, row: TenantSourceEndpointConfig
) -> EndpointDetail:
    """Sobrepoe campos do TSEC no detail base do catalogo.

    Resolve `effective_*` = override OR default. Se override viola
    monotonicidade contra defaults (combinacao mista invalida), mantem
    effective_* = override em cada campo individualmente. UI mostra warning
    e operador corrige.
    """
    effective_expected = (
        row.expected_lag_business_days_override
        if row.expected_lag_business_days_override is not None
        else detail.default_expected_lag_business_days
    )
    effective_tolerance = (
        row.tolerance_business_days_override
        if row.tolerance_business_days_override is not None
        else detail.default_tolerance_business_days
    )
    effective_give_up = (
        row.give_up_business_days_override
        if row.give_up_business_days_override is not None
        else detail.default_give_up_business_days
    )
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
            "expected_lag_business_days_override": (
                row.expected_lag_business_days_override
            ),
            "tolerance_business_days_override": (
                row.tolerance_business_days_override
            ),
            "give_up_business_days_override": (
                row.give_up_business_days_override
            ),
            "effective_expected_lag_business_days": effective_expected,
            "effective_tolerance_business_days": effective_tolerance,
            "effective_give_up_business_days": effective_give_up,
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

    tenant_slug = await _resolve_tenant_slug(db, principal.tenant_id)
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
        detail = _spec_to_detail(spec, tenant_slug)
        if spec.name in overrides_by_name:
            detail = _merge_override(detail, overrides_by_name[spec.name])
        out.append(detail)

    # Injeta next_sync_at agora que ja temos overrides resolvidos. Batch:
    # 1 query SQL pro state machine cobrindo todos endpoints state-machine-enabled,
    # 0 SQL pros legados (calculo puro a partir do schedule + last_sync_started_at).
    await _populate_next_sync(
        out,
        db=db,
        tenant_id=principal.tenant_id,
        source_type=source_type,
        environment=environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )

    return out


async def _populate_next_sync(
    details: list[EndpointDetail],
    *,
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment,
    unidade_administrativa_id: UUID | None,
) -> None:
    """Preenche `next_sync_at` + `next_sync_source` in-place em cada detail.

    Para endpoints state-machine-enabled: usa MIN(next_attempt_at) de
    endpoint_date_state. Para legados: deriva de schedule + last_sync_started_at.
    on_demand fica com None + source="manual_only".
    """
    sm_endpoints = [
        d.name for d in details
        if is_state_machine_enabled(source_type, d.name)
    ]
    sm_next = await load_state_machine_next_attempts(
        db,
        tenant_id=tenant_id,
        source_type=source_type,
        environment=environment,
        unidade_administrativa_id=unidade_administrativa_id,
        endpoint_names=sm_endpoints,
    )
    now = datetime.now(UTC)
    for d in details:
        # Schedule do tenant (override OR default) — usado tanto como
        # fallback quando state machine nao tem trabalho pendente, quanto
        # como caminho principal pros endpoints legados.
        kind = d.schedule_kind or d.default_schedule_kind
        value = (
            d.schedule_value if d.schedule_kind is not None
            else d.default_schedule_value
        )

        if is_state_machine_enabled(source_type, d.name):
            # State machine pendente = ha data retentavel (not_started, empty,
            # partial, not_published). TTL de refresh-complete (state=complete)
            # NAO entra aqui pra nao confundir UI com "Próximo sync em X" pra
            # dia ja saudavel.
            pending_at = sm_next.get(d.name)
            if pending_at is not None:
                d.next_sync_at = pending_at
                d.next_sync_source = "state_machine"
                continue
            # Sem trabalho pendente — proximo sync e a proxima janela
            # programada do schedule (ex.: amanha SP 09:45 pro daily_at).
            # Semantica: "tudo em dia, proximo ciclo normal sai em X".
            if kind == "on_demand":
                d.next_sync_at = None
                d.next_sync_source = "manual_only"
                continue
            d.next_sync_at = compute_next_sync_legacy(
                schedule_kind=kind,
                schedule_value=value,
                last_started_at=d.last_sync_started_at,
                now=now,
            )
            d.next_sync_source = "schedule" if d.next_sync_at else "manual_only"
            continue

        # Legado: deriva do schedule. Se TSEC nao existe (schedule_kind None),
        # cai no default do catalogo (nao deveria acontecer pra QiTech pq a
        # migration ja seedou, mas defensivo).
        if kind == "on_demand":
            d.next_sync_at = None
            d.next_sync_source = "manual_only"
            continue
        d.next_sync_at = compute_next_sync_legacy(
            schedule_kind=kind,
            schedule_value=value,
            last_started_at=d.last_sync_started_at,
            now=now,
        )
        d.next_sync_source = "schedule" if d.next_sync_at else "manual_only"


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
    tenant_slug = await _resolve_tenant_slug(db, principal.tenant_id)
    detail = _spec_to_detail(spec, tenant_slug)

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
    await _populate_next_sync(
        [detail],
        db=db,
        tenant_id=principal.tenant_id,
        source_type=source_type,
        environment=environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )
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

    # Valida monotonicidade da JANELA EFETIVA (override + catalog) antes de
    # persistir — caller pode mandar override parcial que viola contra os
    # defaults do catalogo (ex.: tolerance=15 com default give_up=10).
    try:
        resolve_tolerance_window(
            expected_lag_override=payload.expected_lag_business_days_override,
            tolerance_override=payload.tolerance_business_days_override,
            give_up_override=payload.give_up_business_days_override,
            default_expected_lag=spec.default_expected_lag_business_days,
            default_tolerance=spec.default_tolerance_business_days,
            default_give_up=spec.default_give_up_business_days,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Combinacao de tolerancia invalida (override + defaults do "
                f"catalogo): {e}. Ajuste expected/tolerance/give_up para "
                f"satisfazer expected <= tolerance <= give_up."
            ),
        ) from e

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
            expected_lag_business_days_override=(
                payload.expected_lag_business_days_override
            ),
            tolerance_business_days_override=(
                payload.tolerance_business_days_override
            ),
            give_up_business_days_override=(
                payload.give_up_business_days_override
            ),
        )
        db.add(row)
    else:
        if payload.enabled is not None:
            row.enabled = payload.enabled
        row.schedule_kind = payload.schedule_kind
        row.schedule_value = payload.schedule_value
        # Tolerance: respeita semantica "null explicito = limpa, omitido =
        # preserva". `model_fields_set` lista os campos que vieram no body,
        # incluindo aqueles com valor null. Frontend antigo (sem os 3
        # campos novos) NAO aparece em fields_set -> mantemos override
        # existente intacto.
        fs = payload.model_fields_set
        if "expected_lag_business_days_override" in fs:
            row.expected_lag_business_days_override = (
                payload.expected_lag_business_days_override
            )
        if "tolerance_business_days_override" in fs:
            row.tolerance_business_days_override = (
                payload.tolerance_business_days_override
            )
        if "give_up_business_days_override" in fs:
            row.give_up_business_days_override = (
                payload.give_up_business_days_override
            )
    await db.commit()
    await db.refresh(row)

    tenant_slug = await _resolve_tenant_slug(db, principal.tenant_id)
    detail = _merge_override(_spec_to_detail(spec, tenant_slug), row)
    await _populate_next_sync(
        [detail],
        db=db,
        tenant_id=principal.tenant_id,
        source_type=source_type,
        environment=payload.environment,
        unidade_administrativa_id=payload.unidade_administrativa_id,
    )
    return detail


@router.post(
    "/{source_type}/endpoints/{endpoint_name:path}/sync",
    response_model=EndpointSyncResult,
)
async def sync_endpoint(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    endpoint_name: Annotated[str, Path()],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    unidade_administrativa_id: Annotated[UUID | None, Query(alias="ua")] = None,
    date_param: Annotated[date | None, Query(alias="date")] = None,
    _: None = _Guard,
) -> EndpointSyncResult:
    """Dispara sync sob demanda de UM endpoint. Sincronia (espera retorno).

    `?date=YYYY-MM-DD` opcional — quando passado, o adapter pede a data
    especifica em vez do default (D-1 para market reports). Usado pelo
    backfill manual e backfill_worker. Sem ?date, comportamento legado.

    Levanta 404 se endpoint nao esta no catalogo. Levanta 422 se tenant nao
    tem TSC pra source (precisa configurar credenciais primeiro).

    Resolucao de UA quando `?ua` nao e passado (pos 2026-05-10):
    1. Se ha exatamente UMA TSC para (tenant, source, env) -> usa essa UA
       (pode ser ua=NULL legacy ou ua=<UUID>). Cobre o caso comum de tenant
       single-UA chamado pela UI sem seletor de UA.
    2. Se ha 0 ou 2+ TSCs -> mantem comportamento original (procura ua=NULL,
       422 se nao achar). Para multi-UA o caller PRECISA passar `?ua=<UUID>`.
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

    # Auto-resolve UA quando o caller nao passou explicitamente. Buscar TODAS
    # as TSCs do (tenant, source, env) e desambiguar:
    if unidade_administrativa_id is None:
        configs = await list_configs(db, principal.tenant_id, source_type, environment)
        if len(configs) == 1:
            unidade_administrativa_id = configs[0].unidade_administrativa_id
        elif len(configs) > 1:
            uas_disponiveis = ", ".join(
                str(c.unidade_administrativa_id) for c in configs
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Tenant {principal.tenant_id} tem {len(configs)} TSCs "
                    f"para {source_type.value}/{environment.value}. Passe "
                    f"`?ua=<UUID>` para escolher. Disponiveis: {uas_disponiveis}"
                ),
            )
        # len == 0: cai pro caminho original (run_sync_endpoint vai retornar
        # 422 com a mensagem ja existente).

    try:
        summary = await run_sync_endpoint(
            principal.tenant_id,
            source_type,
            endpoint_name,
            environment=environment,
            since=date_param,
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


# ─────────────────────────────────────────────────────────────────────────────
# Backfill (assincrono) — Sub-fase 2A da freshness story (2026-05-12)
# ─────────────────────────────────────────────────────────────────────────────


class BackfillCreatePayload(BaseModel):
    """Body do POST /backfill — lista de datas pra enfileirar."""

    dates: list[date] = Field(min_length=1, max_length=2000)
    environment: Environment = Environment.PRODUCTION
    unidade_administrativa_id: UUID | None = None


class BackfillJobOut(BaseModel):
    """Snapshot do estado do job. Polled pelo frontend a cada 2s."""

    id: UUID
    source_type: SourceType
    environment: Environment
    unidade_administrativa_id: UUID | None
    endpoint_name: str
    status: str
    dates_pending: list[date]
    dates_done: list[date]
    dates_failed: list[dict[str, Any]]
    created_by: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


def _job_to_out(job: Any) -> BackfillJobOut:
    return BackfillJobOut(
        id=job.id,
        source_type=SourceType(job.source_type),
        environment=Environment(job.environment),
        unidade_administrativa_id=job.unidade_administrativa_id,
        endpoint_name=job.endpoint_name,
        status=job.status,
        dates_pending=list(job.dates_pending),
        dates_done=list(job.dates_done),
        dates_failed=list(job.dates_failed),
        created_by=job.created_by,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.post(
    "/{source_type}/endpoints/{endpoint_name:path}/backfill",
    response_model=BackfillJobOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint_backfill(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    endpoint_name: Annotated[str, Path()],
    payload: BackfillCreatePayload,
    _: None = _Guard,
) -> BackfillJobOut:
    """Cria backfill assincrono de N datas pra UM endpoint.

    Retorna `job_id` em 100ms. O worker (APScheduler tick 5s) pega o job e
    processa serialmente, atualizando `dates_done` / `dates_failed`.
    Frontend polla `GET /backfill/{job_id}` a cada 2s pra animar o heatmap.
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

    # Quando a UI nao manda UA (nenhuma selecionada), resolve a config
    # habilitada — evita o job com ua=None que falhava 100% silenciosamente
    # (bug 2026-05-27). UA ambigua (>1) ou ausente vira 409 claro.
    ua_id = payload.unidade_administrativa_id
    if ua_id is None:
        try:
            ua_id = await resolve_backfill_ua(
                db,
                tenant_id=principal.tenant_id,
                source_type=source_type,
                environment=payload.environment,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(e)
            ) from e

    job = await create_backfill_job(
        db,
        tenant_id=principal.tenant_id,
        source_type=source_type,
        environment=payload.environment,
        unidade_administrativa_id=ua_id,
        endpoint_name=endpoint_name,
        dates=payload.dates,
        created_by=f"user:{principal.user_id}",
    )
    return _job_to_out(job)


@router.get(
    "/backfill/{job_id}",
    response_model=BackfillJobOut,
)
async def get_backfill_job_status(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    job_id: Annotated[UUID, Path()],
    _: None = _Guard,
) -> BackfillJobOut:
    job = await get_backfill_job(
        db, tenant_id=principal.tenant_id, job_id=job_id
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job nao encontrado.")
    return _job_to_out(job)


@router.delete(
    "/backfill/{job_id}",
    response_model=BackfillJobOut,
)
async def cancel_backfill_job_endpoint(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    job_id: Annotated[UUID, Path()],
    _: None = _Guard,
) -> BackfillJobOut:
    """Marca job como cancelled. Worker para no proximo loop de data."""
    job = await cancel_backfill_job(
        db, tenant_id=principal.tenant_id, job_id=job_id
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job nao encontrado.")
    return _job_to_out(job)


@router.get(
    "/{source_type}/backfill/active",
    response_model=list[BackfillJobOut],
)
async def list_active_backfills(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    endpoint_name: Annotated[str | None, Query()] = None,
    _: None = _Guard,
) -> list[BackfillJobOut]:
    """Lista jobs `pending` ou `running` pra (tenant, source [, endpoint]).
    Frontend chama no mount da aba Cobertura pra recuperar polls em
    progresso quando voce recarrega a pagina."""
    jobs = await list_active_backfill_jobs(
        db,
        tenant_id=principal.tenant_id,
        source_type=source_type,
        endpoint_name=endpoint_name,
    )
    return [_job_to_out(j) for j in jobs]


# ─────────────────────────────────────────────────────────────────────────────
# Coverage (Fase 1 - aba "Cobertura" da UI)
# ─────────────────────────────────────────────────────────────────────────────


class ItemSummaryOut(BaseModel):
    """Linha do sumario do payload (carteira, papel, conta, movimento).

    `value` e `delta_pct` sao opcionais — Decimal serializado como string
    para preservar precisao (frontend usa Number() quando precisa formatar).
    Para tipos sem semantica de valor (ex.: job_id de CSV), `value=None` e
    o frontend exibe so o `name`.
    """

    name: str
    value: Decimal | None = None
    delta_pct: Decimal | None = None
    suspicious: bool = False
    suspicious_reason: str | None = None


class PayloadSummaryOut(BaseModel):
    """Sumario do payload bruto, populado em endpoints com payload JSONB
    em `wh_qitech_raw_relatorio`. Outros endpoints (bank_account.*) devolvem
    `None` no field do dia."""

    total_items: int
    expected_items: int | None = None
    suspicious_count: int = 0
    items: list[ItemSummaryOut] = Field(default_factory=list)


class CoverageDayOut(BaseModel):
    data: date
    status: str = Field(description=", ".join(s.value for s in CoverageStatus))
    http_status: int | None = None
    # 'complete' | 'partial' | 'empty' | None — detalha o status quando
    # http=200 mas a 200 nao implica payload integro (Opcao A, 2026-05-13).
    completeness: str | None = None
    # 'esperado' | 'atrasado' | 'suspeito' | 'furo_definitivo' | None.
    # Aplica apenas quando o dia ainda nao publicou (GAP/NOT_PUBLISHED/
    # PENDING). UI usa pra pintar badge color e mostrar tooltip de tempo.
    tolerance_state: str | None = Field(
        default=None,
        description=", ".join(s.value for s in PublicationState),
    )
    # Sinais de qualidade (2026-05-20) — visiveis no tooltip do
    # `QiTechCoverageStrip`. So populados em endpoints com payload JSONB
    # (`wh_qitech_raw_relatorio`); demais devolvem None.
    fetched_at: datetime | None = None
    fetched_by_version: str | None = None
    payload_sha256_short: str | None = None
    summary: PayloadSummaryOut | None = None


class EndpointCoverageOut(BaseModel):
    name: str
    label: str
    schedule_kind: ScheduleKindStr
    supported: bool
    days: list[CoverageDayOut]
    count_ok: int
    count_partial: int
    count_not_published: int
    count_gap: int
    # Janela efetiva (override OR catalogo). None quando endpoint nao suporta
    # coverage. Frontend renderiza "Esperado em D+X · Suspeito a partir D+Y"
    # como subtitulo da linha do endpoint.
    expected_lag_business_days: int | None = None
    tolerance_business_days: int | None = None
    give_up_business_days: int | None = None
    # Agregados por estado de tolerancia — contagem dentro do range pedido.
    count_esperado: int = 0
    count_atrasado: int = 0
    count_suspeito: int = 0
    count_furo_definitivo: int = 0


class CoverageResponseOut(BaseModel):
    start_date: date
    end_date: date
    endpoints: list[EndpointCoverageOut]


@router.get(
    "/{source_type}/coverage",
    response_model=CoverageResponseOut,
)
async def source_coverage(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    range_days: Annotated[int, Query(ge=0, le=2000)] = 180,
    unidade_administrativa_id: Annotated[UUID | None, Query(alias="ua")] = None,
    _: None = _Guard,
) -> CoverageResponseOut:
    """Cobertura historica por endpoint nos ultimos `range_days` dias.

    `range_days=0` significa "todo o periodo desde o primeiro dado
    coletado" — cap absoluto em `MAX_RANGE_DAYS` (2000d, ~5.5 anos)
    pra nao estourar o DOM.

    Cruza raw tables com calendario ANBIMA (`wh_dim_dia_util`) pra
    distinguir furo real de feriado. Endpoints ON_DEMAND/INTERVAL tambem
    sao cobertos: o conceito de "dia coletado" muda mas a pergunta e a
    mesma.
    """
    cov = await get_source_coverage(
        db,
        source_type=source_type,
        tenant_id=principal.tenant_id,
        unidade_administrativa_id=unidade_administrativa_id,
        range_days=range_days if range_days > 0 else None,
    )
    return CoverageResponseOut(
        start_date=cov.start_date,
        end_date=cov.end_date,
        endpoints=[
            EndpointCoverageOut(
                name=ep.name,
                label=ep.label,
                schedule_kind=ep.schedule_kind,  # type: ignore[arg-type]
                supported=ep.supported,
                days=[
                    CoverageDayOut(
                        data=d.data,
                        status=d.status.value,
                        http_status=d.http_status,
                        completeness=d.completeness,
                        tolerance_state=(
                            d.tolerance_state.value
                            if d.tolerance_state is not None
                            else None
                        ),
                        fetched_at=d.fetched_at,
                        fetched_by_version=d.fetched_by_version,
                        payload_sha256_short=d.payload_sha256_short,
                        summary=(
                            PayloadSummaryOut(
                                total_items=d.summary.total_items,
                                expected_items=d.summary.expected_items,
                                suspicious_count=d.summary.suspicious_count,
                                items=[
                                    ItemSummaryOut(
                                        name=it.name,
                                        value=it.value,
                                        delta_pct=it.delta_pct,
                                        suspicious=it.suspicious,
                                        suspicious_reason=it.suspicious_reason,
                                    )
                                    for it in d.summary.items
                                ],
                            )
                            if d.summary is not None
                            else None
                        ),
                    )
                    for d in ep.days
                ],
                count_ok=ep.count_ok,
                count_partial=ep.count_partial,
                count_not_published=ep.count_not_published,
                count_gap=ep.count_gap,
                expected_lag_business_days=ep.expected_lag_business_days,
                tolerance_business_days=ep.tolerance_business_days,
                give_up_business_days=ep.give_up_business_days,
                count_esperado=ep.count_esperado,
                count_atrasado=ep.count_atrasado,
                count_suspeito=ep.count_suspeito,
                count_furo_definitivo=ep.count_furo_definitivo,
            )
            for ep in cov.endpoints
        ],
    )
