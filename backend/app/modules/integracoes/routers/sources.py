"""HTTP endpoints para configuracao de fontes externas (integracoes).

Fluxo esperado pelo operador:
1. `GET /integracoes/sources` — lista catalogo + status por tenant.
2. `GET /integracoes/sources/{source_type}` — detalhe (secrets mascarados).
3. `PUT /integracoes/sources/{source_type}/config` — merge parcial.
4. `POST /integracoes/sources/{source_type}/enable` — liga/desliga.
5. `POST /integracoes/sources/{source_type}/test` — ping via adapter.
6. `POST /integracoes/sources/{source_type}/sync` — dispara sync manual.
7. `GET /integracoes/sources/{source_type}/runs` — historico do decision_log.

Todos exigem `require_module(Module.INTEGRACOES, Permission.ADMIN)`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.enums import Environment, Module, Permission, SourceType
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.integracoes.public import run_ping, run_sync_one
from app.modules.integracoes.services.backfill_service import (
    create_backfill_job,
    list_active_backfill_jobs,
)
from app.modules.integracoes.services.coverage import (
    CoverageStatus,
    get_source_coverage,
)
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
    merge_config,
    set_enabled,
)
from app.modules.integracoes.services.sync_runner import rule_name_for
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.shared.catalog.source_catalog import SourceCatalog

router = APIRouter(prefix="/sources", tags=["integracoes:sources"])

_Guard = Depends(require_module(Module.INTEGRACOES, Permission.ADMIN))


# --- Metadata por source_type --------------------------------------------------
# Secrets: campos que nunca vazam na resposta (mascarados como "***SET***").
# rule_or_model: valor usado pelo adapter ao gravar no decision_log.
_SOURCE_SECRET_FIELDS: dict[SourceType, frozenset[str]] = {
    SourceType.ERP_BITFIN: frozenset({"password"}),
    # QiTech/Singulare autentica via Basic Auth com par client_id+client_secret
    # emitido ao tenant. Ambos sao tratados como sensiveis e mascarados no GET
    # para evitar vazamento de credencial pela API, mesmo que client_id seja
    # tecnicamente "publico" em OAuth2 puro — no contexto do GR sao duas
    # metades da credencial do tenant.
    SourceType.ADMIN_QITECH: frozenset({"client_id", "client_secret"}),
    # Serasa PJ: client_id+client_secret sao a credencial de distribuidor.
    # `retailer_document_id` (CNPJ do consultante) NAO e segredo — operador
    # precisa ver pra confirmar config; revelar nao da acesso a nada.
    SourceType.BUREAU_SERASA_PJ: frozenset({"client_id", "client_secret"}),
}

def _mask_secrets(source_type: SourceType, config: dict) -> dict:
    """Retorna copia de `config` com valores de campos sensiveis trocados por `***SET***`."""
    secret_keys = _SOURCE_SECRET_FIELDS.get(source_type, frozenset())
    return {
        k: ("***SET***" if k in secret_keys and v not in (None, "") else v)
        for k, v in config.items()
    }


# --- Schemas -------------------------------------------------------------------


class SourceListItem(BaseModel):
    """Linha do catalogo com status para o tenant atual.

    Multi-UA: para fontes admin que tem credencial por UA (QiTech), pode
    haver N entradas — uma por UA. `unidade_administrativa_id` distingue.
    """

    source_type: SourceType
    label: str
    category: str
    owner_org: str | None
    description: str | None
    # Status por tenant (ambiente padrao: production)
    configured: bool
    enabled: bool
    environment: Environment | None
    last_sync_at: datetime | None
    # null = sob demanda; numero = cadencia ativa do scheduler
    sync_frequency_minutes: int | None = None
    unidade_administrativa_id: UUID | None = None


class SourceDetail(BaseModel):
    """Detalhe da configuracao (secrets mascarados)."""

    source_type: SourceType
    label: str
    category: str
    owner_org: str | None
    description: str | None
    environment: Environment
    configured: bool
    enabled: bool
    config: dict[str, Any]  # secrets mascarados
    sync_frequency_minutes: int | None
    updated_at: datetime | None
    unidade_administrativa_id: UUID | None = None


class ConfigUpdate(BaseModel):
    """PUT body: merge parcial do config + flags opcionais."""

    config: dict[str, Any] = Field(default_factory=dict)
    environment: Environment = Environment.PRODUCTION
    enabled: bool | None = None
    # null = sob demanda (sem agendamento). Range 15..1440 espelha a CHECK
    # do banco (alembic 0011_sync_frequency_check) — falha em UI antes de
    # bater no Postgres.
    sync_frequency_minutes: int | None = Field(default=None, ge=15, le=1440)
    unidade_administrativa_id: UUID | None = None


class EnableUpdate(BaseModel):
    """POST body para enable/disable."""

    enabled: bool
    environment: Environment = Environment.PRODUCTION
    unidade_administrativa_id: UUID | None = None


class TestResult(BaseModel):
    """Retorno de POST /test (proxy do adapter.ping)."""

    ok: bool
    latency_ms: float | None = None
    detail: Any = None
    adapter_version: str | None = None


class SyncResult(BaseModel):
    """Retorno de POST /sync — summary do ciclo."""

    adapter_version: str | None = None
    started_at: str | None = None
    elapsed_seconds: float | None = None
    since: str | None = None
    tables: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class RunEntry(BaseModel):
    """Entrada do decision_log (filtrada por sync do adapter)."""

    id: UUID
    occurred_at: datetime
    rule_or_model: str | None
    rule_or_model_version: str | None
    triggered_by: str
    explanation: str | None
    output: dict[str, Any] | None


class RefreshEmptyEndpointResult(BaseModel):
    """Resultado por endpoint da varredura refresh-empty."""

    endpoint_name: str
    label: str
    # Datas detectadas com state nos `states` pedidos no range.
    detected_dates_count: int
    # Datas que ja estavam em jobs ativos (pending/running) — nao re-enfileiradas.
    skipped_in_active_jobs_count: int
    # Datas efetivamente enfileiradas neste call.
    enqueued_dates_count: int
    job_id: UUID | None = None


class RefreshEmptyResult(BaseModel):
    """Retorno consolidado de POST /refresh-empty."""

    since: date
    until: date
    states_scanned: list[CoverageStatus]
    endpoints_scanned: int
    endpoints_with_matches: int
    endpoints_enqueued: int
    total_dates_detected: int
    total_dates_enqueued: int
    per_endpoint: list[RefreshEmptyEndpointResult]


# --- Helpers -------------------------------------------------------------------


async def _load_catalog(db: AsyncSession) -> list[SourceCatalog]:
    stmt = select(SourceCatalog).order_by(SourceCatalog.category, SourceCatalog.label)
    return list((await db.execute(stmt)).scalars().all())


async def _catalog_row(db: AsyncSession, source_type: SourceType) -> SourceCatalog:
    row = await db.get(SourceCatalog, source_type)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"source_type '{source_type.value}' nao existe em source_catalog",
        )
    return row


async def _last_sync_at(
    db: AsyncSession, tenant_id: UUID, source_type: SourceType
) -> datetime | None:
    """Ultimo occurred_at no decision_log para o adapter daquele source_type."""
    rule = rule_name_for(source_type)
    if rule is None:
        return None
    stmt = (
        select(DecisionLog.occurred_at)
        .where(
            DecisionLog.tenant_id == tenant_id,
            DecisionLog.decision_type == DecisionType.SYNC,
            DecisionLog.rule_or_model == rule,
        )
        .order_by(desc(DecisionLog.occurred_at))
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _build_source_detail(
    db: AsyncSession,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment,
    *,
    unidade_administrativa_id: UUID | None = None,
) -> SourceDetail:
    """Monta o SourceDetail sem passar pela dependency do guard (reuso interno)."""
    cat = await _catalog_row(db, source_type)
    row = await get_config(
        db,
        tenant_id,
        source_type,
        environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )
    config_plain: dict[str, Any] = {}
    if row is not None:
        config_plain = decrypt_config(row.config)
    return SourceDetail(
        source_type=cat.source_type,
        label=cat.label,
        category=cat.category,
        owner_org=cat.owner_org,
        description=cat.description,
        environment=row.environment if row else environment,
        configured=row is not None,
        enabled=bool(row and row.enabled),
        config=_mask_secrets(source_type, config_plain),
        sync_frequency_minutes=row.sync_frequency_minutes if row else None,
        updated_at=row.updated_at if row else None,
        unidade_administrativa_id=row.unidade_administrativa_id if row else None,
    )


# --- Endpoints -----------------------------------------------------------------


@router.get("", response_model=list[SourceListItem])
async def list_sources(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    _: None = _Guard,
) -> list[SourceListItem]:
    """Lista catalogo + status de cada fonte para o tenant atual no ambiente pedido.

    Pos-multi-UA: pra fontes com credencial por UA (QiTech), retorna 1 linha
    por UA configurada (alem da entrada base do catalogo). Bitfin continua
    com 1 linha so.
    """
    from app.modules.integracoes.services.source_config import list_configs

    catalog = await _load_catalog(db)
    out: list[SourceListItem] = []
    for c in catalog:
        configs = await list_configs(
            db, principal.tenant_id, c.source_type, environment
        )
        last_sync = await _last_sync_at(db, principal.tenant_id, c.source_type)
        if not configs:
            out.append(
                SourceListItem(
                    source_type=c.source_type,
                    label=c.label,
                    category=c.category,
                    owner_org=c.owner_org,
                    description=c.description,
                    configured=False,
                    enabled=False,
                    environment=None,
                    last_sync_at=last_sync,
                    sync_frequency_minutes=None,
                    unidade_administrativa_id=None,
                )
            )
            continue
        for row in configs:
            out.append(
                SourceListItem(
                    source_type=c.source_type,
                    label=c.label,
                    category=c.category,
                    owner_org=c.owner_org,
                    description=c.description,
                    configured=True,
                    enabled=row.enabled,
                    environment=row.environment,
                    last_sync_at=last_sync,
                    sync_frequency_minutes=row.sync_frequency_minutes,
                    unidade_administrativa_id=row.unidade_administrativa_id,
                )
            )
    return out


@router.get("/{source_type}", response_model=SourceDetail)
async def get_source(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    unidade_administrativa_id: Annotated[UUID | None, Query()] = None,
    _: None = _Guard,
) -> SourceDetail:
    """Detalhe do source para o tenant. Secrets nunca saem em claro.

    `unidade_administrativa_id` (multi-UA): quando informado, retorna a config
    da UA especifica. Sem o param, casa a linha legacy (UA=NULL).
    """
    return await _build_source_detail(
        db,
        principal.tenant_id,
        source_type,
        environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )


@router.put("/{source_type}/config", response_model=SourceDetail)
async def update_source_config(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    payload: ConfigUpdate,
    _: None = _Guard,
) -> SourceDetail:
    """Merge parcial: campos ausentes em `payload.config` preservam valor persistido.

    Permite rotacionar um secret sem re-enviar os demais. Para remover um campo,
    passe-o com valor `null`. `unidade_administrativa_id` (multi-UA) escopa
    a linha — admin pode ter N credenciais por (tenant, source, env), uma
    por UA.

    Cadencia (sync_frequency_minutes): quando o agendamento por endpoint esta
    ligado (`INTEGRACOES_USE_ENDPOINT_SCHEDULING=True`), o campo legado fica
    deprecated. Se o caller ainda enviar valor != None, retornamos 400
    redirecionando para a UI de endpoints. Modo legado continua aceitando.
    """
    if (
        get_settings().INTEGRACOES_USE_ENDPOINT_SCHEDULING
        and payload.sync_frequency_minutes is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cadencia agora e configurada por endpoint — use "
                "PUT /integracoes/sources/{source_type}/endpoints/{endpoint_name}. "
                "O campo `sync_frequency_minutes` em /config esta deprecated e "
                "sera removido num release futuro."
            ),
        )

    await _catalog_row(db, source_type)
    await merge_config(
        db,
        principal.tenant_id,
        source_type,
        payload.config,
        environment=payload.environment,
        enabled=payload.enabled,
        sync_frequency_minutes=payload.sync_frequency_minutes,
        unidade_administrativa_id=payload.unidade_administrativa_id,
    )
    return await _build_source_detail(
        db,
        principal.tenant_id,
        source_type,
        payload.environment,
        unidade_administrativa_id=payload.unidade_administrativa_id,
    )


@router.post("/{source_type}/enable", response_model=SourceDetail)
async def enable_source(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    payload: EnableUpdate,
    _: None = _Guard,
) -> SourceDetail:
    """Liga ou desliga a fonte para (tenant, environment, UA). Exige config persistida."""
    await _catalog_row(db, source_type)
    ok = await set_enabled(
        db,
        principal.tenant_id,
        source_type,
        payload.enabled,
        environment=payload.environment,
        unidade_administrativa_id=payload.unidade_administrativa_id,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Nao existe config persistida para {source_type.value}/"
                f"{payload.environment.value}/ua={payload.unidade_administrativa_id}. "
                f"Envie PUT /config primeiro."
            ),
        )
    return await _build_source_detail(
        db,
        principal.tenant_id,
        source_type,
        payload.environment,
        unidade_administrativa_id=payload.unidade_administrativa_id,
    )


@router.post("/{source_type}/test", response_model=TestResult)
async def test_source(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    source_type: Annotated[SourceType, Path()],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    unidade_administrativa_id: Annotated[UUID | None, Query()] = None,
    _: None = _Guard,
) -> TestResult:
    """Dispara `adapter.ping` contra a config persistida. Nunca levanta — erro vira `ok=False`."""
    result = await run_ping(
        principal.tenant_id,
        source_type,
        environment=environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )
    return TestResult(**result)


@router.post("/{source_type}/sync", response_model=SyncResult)
async def sync_source(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    source_type: Annotated[SourceType, Path()],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    unidade_administrativa_id: Annotated[UUID | None, Query()] = None,
    _: None = _Guard,
) -> SyncResult:
    """Dispara sync manual sincronico (nao verifica `enabled`).

    Propaga erros para o operador ver falha imediatamente — diferente do ciclo
    automatico, que isola por linha.
    """
    try:
        summary = await run_sync_one(
            principal.tenant_id,
            source_type,
            environment=environment,
            triggered_by=f"user:{principal.user_id}",
            unidade_administrativa_id=unidade_administrativa_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        ) from e
    return SyncResult(**summary)


# Estados default que disparam re-enfileiramento. Cobre os 3 casos onde a
# publicacao do vendor pode ainda evoluir e justifica retentar:
# - NOT_PUBLISHED: linha raw existe com http != 200 (ex.: 400/404 padrao
#   MEC e dos endpoints market quando vendor ainda nao publicou). Caso real
#   dos 5 endpoints presos do REALINVEST em 2026-05-15.
# - PARTIAL: http=200 mas completeness in ("partial", "empty") — payload
#   incompleto que pode ser republicado pelo vendor.
# - GAP: dia util sem nenhuma linha raw (ETL nunca tentou ou erro de rede
#   antes de gravar raw).
#
# Operador pode override via `?states=...&states=...` se quiser, por ex.,
# excluir PARTIAL e so retentar NOT_PUBLISHED.
_REFRESH_EMPTY_DEFAULT_STATES: tuple[CoverageStatus, ...] = (
    CoverageStatus.NOT_PUBLISHED,
    CoverageStatus.PARTIAL,
    CoverageStatus.GAP,
)


@router.post(
    "/{source_type}/refresh-empty",
    response_model=RefreshEmptyResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def refresh_empty_dates(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    since: Annotated[date, Query(description="Limite inferior do range, inclusivo (YYYY-MM-DD).")],
    until: Annotated[
        date | None,
        Query(description="Limite superior, inclusivo. Default = hoje."),
    ] = None,
    states: Annotated[
        list[CoverageStatus] | None,
        Query(description="Estados que disparam backfill. Default: not_published, partial, gap."),
    ] = None,
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    unidade_administrativa_id: Annotated[UUID | None, Query()] = None,
    _: None = _Guard,
) -> RefreshEmptyResult:
    """Varre cobertura no range e enfileira BackfillJob pros dias presos.

    Caso de uso: depois que reconciler/cap absoluto esgota tentativas e
    deixa endpoint preso em empty/not_published, esta rota destrava em
    massa — varre todos os endpoints da source, encontra dias com state
    nos `states` pedidos, e cria 1 BackfillJob por endpoint.

    Idempotencia: dias que ja estao em job ativo (pending/running) sao
    ignorados — evita duplicacao quando operador clica de novo.
    """
    today = datetime.now(UTC).date()
    end = until or today
    if since > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"since ({since}) nao pode ser posterior a until/today ({end}).",
        )

    range_days = (end - since).days + 1
    selected_states = tuple(states) if states else _REFRESH_EMPTY_DEFAULT_STATES

    coverage = await get_source_coverage(
        db,
        source_type=source_type,
        tenant_id=principal.tenant_id,
        unidade_administrativa_id=unidade_administrativa_id,
        range_days=range_days,
    )

    # get_source_coverage usa today como end e clampa start em today-range_days+1
    # — pode divergir do `since` informado quando until != today. Filtramos pelo
    # range pedido pra resposta refletir exatamente o intervalo solicitado.
    per_endpoint: list[RefreshEmptyEndpointResult] = []
    total_detected = 0
    total_enqueued = 0
    endpoints_with_matches = 0
    endpoints_enqueued = 0

    for ep_cov in coverage.endpoints:
        if not ep_cov.supported:
            continue

        detected = [
            d.data
            for d in ep_cov.days
            if since <= d.data <= end and d.status in selected_states
        ]
        if not detected:
            per_endpoint.append(
                RefreshEmptyEndpointResult(
                    endpoint_name=ep_cov.name,
                    label=ep_cov.label,
                    detected_dates_count=0,
                    skipped_in_active_jobs_count=0,
                    enqueued_dates_count=0,
                )
            )
            continue

        endpoints_with_matches += 1
        total_detected += len(detected)

        # Idempotencia: dedup contra jobs ativos do MESMO endpoint.
        active_jobs = await list_active_backfill_jobs(
            db,
            tenant_id=principal.tenant_id,
            source_type=source_type,
            endpoint_name=ep_cov.name,
        )
        dates_in_active: set[date] = set()
        for job in active_jobs:
            dates_in_active.update(job.dates_pending or [])

        to_enqueue = [d for d in detected if d not in dates_in_active]
        skipped = len(detected) - len(to_enqueue)

        job_id: UUID | None = None
        if to_enqueue:
            job = await create_backfill_job(
                db,
                tenant_id=principal.tenant_id,
                source_type=source_type,
                environment=environment,
                unidade_administrativa_id=unidade_administrativa_id,
                endpoint_name=ep_cov.name,
                dates=to_enqueue,
                created_by=f"refresh-empty:{principal.user_id}",
            )
            job_id = job.id
            endpoints_enqueued += 1
            total_enqueued += len(to_enqueue)

        per_endpoint.append(
            RefreshEmptyEndpointResult(
                endpoint_name=ep_cov.name,
                label=ep_cov.label,
                detected_dates_count=len(detected),
                skipped_in_active_jobs_count=skipped,
                enqueued_dates_count=len(to_enqueue),
                job_id=job_id,
            )
        )

    return RefreshEmptyResult(
        since=since,
        until=end,
        states_scanned=list(selected_states),
        endpoints_scanned=sum(1 for e in coverage.endpoints if e.supported),
        endpoints_with_matches=endpoints_with_matches,
        endpoints_enqueued=endpoints_enqueued,
        total_dates_detected=total_detected,
        total_dates_enqueued=total_enqueued,
        per_endpoint=per_endpoint,
    )


@router.get("/{source_type}/runs", response_model=list[RunEntry])
async def list_runs(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    _: None = _Guard,
) -> list[RunEntry]:
    """Historico das ultimas execucoes (decision_log filtrado pelo adapter)."""
    rule = rule_name_for(source_type)
    if rule is None:
        return []
    stmt = (
        select(DecisionLog)
        .where(
            DecisionLog.tenant_id == principal.tenant_id,
            DecisionLog.decision_type == DecisionType.SYNC,
            DecisionLog.rule_or_model == rule,
        )
        .order_by(desc(DecisionLog.occurred_at))
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return [
        RunEntry(
            id=r.id,
            occurred_at=r.occurred_at,
            rule_or_model=r.rule_or_model,
            rule_or_model_version=r.rule_or_model_version,
            triggered_by=r.triggered_by,
            explanation=r.explanation,
            output=r.output,
        )
        for r in rows
    ]
