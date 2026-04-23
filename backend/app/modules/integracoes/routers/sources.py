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

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Environment, Module, Permission, SourceType
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.integracoes.public import run_ping, run_sync_one
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
    merge_config,
    set_enabled,
)
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.shared.catalog.source_catalog import SourceCatalog

router = APIRouter(prefix="/sources", tags=["integracoes:sources"])

_Guard = Depends(require_module(Module.INTEGRACOES, Permission.ADMIN))


# --- Metadata por source_type --------------------------------------------------
# Secrets: campos que nunca vazam na resposta (mascarados como "***SET***").
# rule_or_model: valor usado pelo adapter ao gravar no decision_log.
_SOURCE_SECRET_FIELDS: dict[SourceType, frozenset[str]] = {
    SourceType.ERP_BITFIN: frozenset({"password"}),
    SourceType.ADMIN_QITECH: frozenset(
        {"api_key", "client_private_key_pem", "qi_public_key_pem"}
    ),
}

_SOURCE_RULE_NAME: dict[SourceType, str] = {
    SourceType.ERP_BITFIN: "bitfin_adapter",
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
    """Linha do catalogo com status para o tenant atual."""

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


class ConfigUpdate(BaseModel):
    """PUT body: merge parcial do config + flags opcionais."""

    config: dict[str, Any] = Field(default_factory=dict)
    environment: Environment = Environment.PRODUCTION
    enabled: bool | None = None
    sync_frequency_minutes: int | None = None


class EnableUpdate(BaseModel):
    """POST body para enable/disable."""

    enabled: bool
    environment: Environment = Environment.PRODUCTION


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
    rule = _SOURCE_RULE_NAME.get(source_type)
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
) -> SourceDetail:
    """Monta o SourceDetail sem passar pela dependency do guard (reuso interno)."""
    cat = await _catalog_row(db, source_type)
    row = await get_config(db, tenant_id, source_type, environment)
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
    )


# --- Endpoints -----------------------------------------------------------------


@router.get("", response_model=list[SourceListItem])
async def list_sources(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    _: None = _Guard,
) -> list[SourceListItem]:
    """Lista catalogo + status de cada fonte para o tenant atual no ambiente pedido."""
    catalog = await _load_catalog(db)
    out: list[SourceListItem] = []
    for c in catalog:
        row = await get_config(db, principal.tenant_id, c.source_type, environment)
        last_sync = await _last_sync_at(db, principal.tenant_id, c.source_type)
        out.append(
            SourceListItem(
                source_type=c.source_type,
                label=c.label,
                category=c.category,
                owner_org=c.owner_org,
                description=c.description,
                configured=row is not None,
                enabled=bool(row and row.enabled),
                environment=row.environment if row else None,
                last_sync_at=last_sync,
            )
        )
    return out


@router.get("/{source_type}", response_model=SourceDetail)
async def get_source(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    _: None = _Guard,
) -> SourceDetail:
    """Detalhe do source para o tenant. Secrets nunca saem em claro."""
    return await _build_source_detail(
        db, principal.tenant_id, source_type, environment
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
    passe-o com valor `null`.
    """
    await _catalog_row(db, source_type)
    await merge_config(
        db,
        principal.tenant_id,
        source_type,
        payload.config,
        environment=payload.environment,
        enabled=payload.enabled,
        sync_frequency_minutes=payload.sync_frequency_minutes,
    )
    return await _build_source_detail(
        db, principal.tenant_id, source_type, payload.environment
    )


@router.post("/{source_type}/enable", response_model=SourceDetail)
async def enable_source(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    payload: EnableUpdate,
    _: None = _Guard,
) -> SourceDetail:
    """Liga ou desliga a fonte para (tenant, environment). Exige config ja persistida."""
    await _catalog_row(db, source_type)
    ok = await set_enabled(
        db,
        principal.tenant_id,
        source_type,
        payload.enabled,
        environment=payload.environment,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Nao existe config persistida para {source_type.value}/"
                f"{payload.environment.value}. Envie PUT /config primeiro."
            ),
        )
    return await _build_source_detail(
        db, principal.tenant_id, source_type, payload.environment
    )


@router.post("/{source_type}/test", response_model=TestResult)
async def test_source(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    source_type: Annotated[SourceType, Path()],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    _: None = _Guard,
) -> TestResult:
    """Dispara `adapter.ping` contra a config persistida. Nunca levanta — erro vira `ok=False`."""
    result = await run_ping(
        principal.tenant_id, source_type, environment=environment
    )
    return TestResult(**result)


@router.post("/{source_type}/sync", response_model=SyncResult)
async def sync_source(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    source_type: Annotated[SourceType, Path()],
    environment: Annotated[Environment, Query()] = Environment.PRODUCTION,
    _: None = _Guard,
) -> SyncResult:
    """Dispara sync manual sincronico (nao verifica `enabled`).

    Propaga erros para o operador ver falha imediatamente — diferente do ciclo
    automatico, que isola por tenant.
    """
    try:
        summary = await run_sync_one(
            principal.tenant_id,
            source_type,
            environment=environment,
            triggered_by=f"user:{principal.user_id}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        ) from e
    return SyncResult(**summary)


@router.get("/{source_type}/runs", response_model=list[RunEntry])
async def list_runs(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_type: Annotated[SourceType, Path()],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    _: None = _Guard,
) -> list[RunEntry]:
    """Historico das ultimas execucoes (decision_log filtrado pelo adapter)."""
    rule = _SOURCE_RULE_NAME.get(source_type)
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
