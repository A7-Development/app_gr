"""Endpoints REST sincronos pra familia /v2/fidc-custodia/report/*.

Auth: require_module(Module.INTEGRACOES, Permission.WRITE).

Endpoints:
    POST /integracoes/qitech/custodia/aquisicao-consolidada/sync
    POST /integracoes/qitech/custodia/liquidados-baixados/sync
    POST /integracoes/qitech/custodia/detalhes-operacoes/sync

Cada um aceita {cnpj_fundo, data_inicial, data_final} (ou data_importacao
no detalhes-operacoes), dispara a sync correspondente, retorna step com
metricas. Operador / agendador externo pode bater nesse endpoint pra
puxar dados manualmente — diferente do `/sources/admin:qitech/sync`
que roda o pipeline /netreport/* completo.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Environment, Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.integracoes.adapters.admin.qitech.custodia import (
    get_qitech_config_for_tenant,
    sync_aquisicao_consolidada,
    sync_detalhes_operacoes,
    sync_liquidados_baixados,
    sync_movimento_aberto,
)

router = APIRouter(
    prefix="/qitech/custodia", tags=["integracoes:qitech-custodia"]
)
_GuardWrite = Depends(require_module(Module.INTEGRACOES, Permission.WRITE))


# ---- Schemas --------------------------------------------------------------


class _PeriodoPayload(BaseModel):
    """Payload comum dos 2 endpoints de periodo."""

    cnpj_fundo: str = Field(min_length=14, max_length=18)
    data_inicial: date
    data_final: date
    environment: Environment = Environment.PRODUCTION


class _DataUnicaPayload(BaseModel):
    """Payload do detalhes-operacoes (data unica)."""

    cnpj_fundo: str = Field(min_length=14, max_length=18)
    data_importacao: date
    environment: Environment = Environment.PRODUCTION


class _SnapshotPayload(BaseModel):
    """Payload do movimento-aberto (snapshot, sem data no path).

    data_referencia opcional — default e hoje UTC. Permite override
    pra reprocessar snapshots historicos.
    """

    cnpj_fundo: str = Field(min_length=14, max_length=18)
    data_referencia: date | None = None
    environment: Environment = Environment.PRODUCTION


class SyncStep(BaseModel):
    name: str
    cnpj_fundo: str
    data_referencia: str
    ok: bool
    raw_http_status: int | None = None
    raw_persisted: bool = False
    canonical_rows_upserted: int = 0
    errors: list[str] = []
    elapsed_seconds: float = 0.0


# ---- Helpers --------------------------------------------------------------


async def _load_config_or_409(
    principal: RequestPrincipal, environment: Environment
):
    config = await get_qitech_config_for_tenant(
        tenant_id=principal.tenant_id, environment=environment
    )
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Sem config QiTech para {environment.value}. "
                f"Configure via PUT /integracoes/sources/admin:qitech/config."
            ),
        )
    if not config.has_credentials():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Config QiTech sem credenciais (client_id / client_secret).",
        )
    return config


# ---- Endpoints ------------------------------------------------------------


@router.post("/aquisicao-consolidada/sync", response_model=SyncStep)
async def sync_aquisicao_consolidada_endpoint(
    payload: _PeriodoPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> SyncStep:
    """Dispara sync sincrono de aquisicao-consolidada no periodo."""
    _ = db  # nao usamos a sessao aqui — sync abre a propria
    config = await _load_config_or_409(principal, payload.environment)
    step = await sync_aquisicao_consolidada(
        tenant_id=principal.tenant_id,
        environment=payload.environment,
        config=config,
        cnpj_fundo=payload.cnpj_fundo,
        data_inicial=payload.data_inicial,
        data_final=payload.data_final,
    )
    return SyncStep.model_validate(step)


@router.post("/liquidados-baixados/sync", response_model=SyncStep)
async def sync_liquidados_baixados_endpoint(
    payload: _PeriodoPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> SyncStep:
    """Dispara sync sincrono de liquidados-baixados/v2 no periodo."""
    _ = db
    config = await _load_config_or_409(principal, payload.environment)
    step = await sync_liquidados_baixados(
        tenant_id=principal.tenant_id,
        environment=payload.environment,
        config=config,
        cnpj_fundo=payload.cnpj_fundo,
        data_inicial=payload.data_inicial,
        data_final=payload.data_final,
    )
    return SyncStep.model_validate(step)


@router.post("/detalhes-operacoes/sync", response_model=SyncStep)
async def sync_detalhes_operacoes_endpoint(
    payload: _DataUnicaPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> SyncStep:
    """Dispara sync sincrono de detalhes-operacoes na data dada."""
    _ = db
    config = await _load_config_or_409(principal, payload.environment)
    step = await sync_detalhes_operacoes(
        tenant_id=principal.tenant_id,
        environment=payload.environment,
        config=config,
        cnpj_fundo=payload.cnpj_fundo,
        data_importacao=payload.data_importacao,
    )
    return SyncStep.model_validate(step)


@router.post("/movimento-aberto/sync", response_model=SyncStep)
async def sync_movimento_aberto_endpoint(
    payload: _SnapshotPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> SyncStep:
    """Dispara sync sincrono de movimento-aberto (snapshot atual)."""
    _ = db
    config = await _load_config_or_409(principal, payload.environment)
    step = await sync_movimento_aberto(
        tenant_id=principal.tenant_id,
        environment=payload.environment,
        config=config,
        cnpj_fundo=payload.cnpj_fundo,
        data_referencia=payload.data_referencia,
    )
    return SyncStep.model_validate(step)
