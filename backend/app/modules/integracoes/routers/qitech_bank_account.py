"""Endpoints REST sincronos para a familia /v2/bank-account/* da QiTech.

Auth: require_module(Module.INTEGRACOES, Permission.WRITE).

Endpoints:
    POST /integracoes/qitech/bank-account/saldo/sync       (1 conta)
    POST /integracoes/qitech/bank-account/saldo/sync-all   (todas habilitadas)
    POST /integracoes/qitech/bank-account/extrato/sync     (1 conta)
    POST /integracoes/qitech/bank-account/extrato/sync-all (todas habilitadas)

Diferente da familia /custodia/* (que resolve UA por CNPJ), aqui o cliente
manda `unidade_administrativa_id` direto -- a UI ja sabe qual UA esta
selecionada (?ua=<id>) e a config QiTech daquela UA contem a lista
`bank_accounts`.

CNPJ nao viaja no payload nem no path -- e implicito da UA dona da config.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Environment, Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.integracoes.adapters.admin.qitech.bank_account_sync import (
    sync_balance,
    sync_balance_all_accounts,
    sync_statement,
    sync_statement_all_accounts,
)
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.custodia import (
    get_qitech_config_for_tenant,
)

router = APIRouter(
    prefix="/qitech/bank-account",
    tags=["integracoes:qitech-bank-account"],
)
_GuardWrite = Depends(require_module(Module.INTEGRACOES, Permission.WRITE))


# ─── Schemas ────────────────────────────────────────────────────────────────


class _SaldoUmaContaPayload(BaseModel):
    """Saldo de UMA conta na data."""

    unidade_administrativa_id: UUID
    agencia: str = Field(min_length=1, max_length=20)
    conta: str = Field(min_length=1, max_length=40)
    data: date
    environment: Environment = Environment.PRODUCTION


class _SaldoTodasPayload(BaseModel):
    """Saldo de todas as contas habilitadas da UA na data."""

    unidade_administrativa_id: UUID
    data: date
    environment: Environment = Environment.PRODUCTION


class _ExtratoUmaContaPayload(BaseModel):
    """Extrato de UMA conta no periodo."""

    unidade_administrativa_id: UUID
    agencia: str = Field(min_length=1, max_length=20)
    conta: str = Field(min_length=1, max_length=40)
    data_inicial: date
    data_final: date
    environment: Environment = Environment.PRODUCTION


class _ExtratoTodasPayload(BaseModel):
    """Extrato de todas as contas habilitadas da UA no periodo."""

    unidade_administrativa_id: UUID
    data_inicial: date
    data_final: date
    environment: Environment = Environment.PRODUCTION


class BankAccountSyncStep(BaseModel):
    """Resultado de uma chamada (1 conta, 1 endpoint)."""

    name: str
    agencia: str
    conta: str
    # Saldo carrega `data`; extrato carrega `periodo_inicio` + `periodo_fim`.
    data: str | None = None
    periodo_inicio: str | None = None
    periodo_fim: str | None = None
    ok: bool
    raw_http_status: int | None = None
    raw_persisted: bool = False
    canonical_rows_upserted: int = 0
    errors: list[str] = []
    elapsed_seconds: float = 0.0


class BankAccountSyncBatch(BaseModel):
    """Resultado consolidado quando processa N contas (sync-all)."""

    total_contas: int
    total_ok: int
    total_com_erro: int
    total_canonical_rows_upserted: int
    steps: list[BankAccountSyncStep]


# ─── Helpers ────────────────────────────────────────────────────────────────


async def _load_config_or_409(
    principal: RequestPrincipal,
    environment: Environment,
    *,
    unidade_administrativa_id: UUID,
) -> QiTechConfig:
    """Carrega config QiTech da UA. 409 sem config / sem credenciais."""
    config = await get_qitech_config_for_tenant(
        tenant_id=principal.tenant_id,
        environment=environment,
        unidade_administrativa_id=unidade_administrativa_id,
    )
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Sem config QiTech para UA {unidade_administrativa_id} em "
                f"{environment.value}. Configure via PUT "
                f"/integracoes/sources/admin:qitech/config."
            ),
        )
    if not config.has_credentials():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Config QiTech sem credenciais (client_id / client_secret).",
        )
    return config


def _ensure_account_in_config(
    config: QiTechConfig, agencia: str, conta: str
) -> None:
    """Erra 409 se (agencia, conta) nao estiver em config.bank_accounts.

    Razao: nao queremos chamada arbitraria a Singulare com par (ag, conta) que
    o admin do tenant nao cadastrou. O cadastro e o `consentimento explicito`
    do tenant pra essa conta ser tocada via API.
    """
    if not any(
        a.agencia == agencia and a.conta == conta for a in config.bank_accounts
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Conta {agencia}/{conta} nao esta cadastrada na config QiTech "
                f"desta UA. Cadastre via UI ou PUT "
                f"/integracoes/sources/admin:qitech/config."
            ),
        )


def _aggregate_steps(steps: list[dict]) -> BankAccountSyncBatch:
    """Consolida lista de steps num batch summary."""
    return BankAccountSyncBatch(
        total_contas=len(steps),
        total_ok=sum(1 for s in steps if s.get("ok")),
        total_com_erro=sum(1 for s in steps if not s.get("ok")),
        total_canonical_rows_upserted=sum(
            int(s.get("canonical_rows_upserted") or 0) for s in steps
        ),
        steps=[BankAccountSyncStep.model_validate(s) for s in steps],
    )


# ─── Endpoints: SALDO ───────────────────────────────────────────────────────


@router.post("/saldo/sync", response_model=BankAccountSyncStep)
async def sync_saldo_endpoint(
    payload: _SaldoUmaContaPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> BankAccountSyncStep:
    """Sincroniza saldo de UMA conta na data."""
    _ = db
    config = await _load_config_or_409(
        principal,
        payload.environment,
        unidade_administrativa_id=payload.unidade_administrativa_id,
    )
    _ensure_account_in_config(config, payload.agencia, payload.conta)
    step = await sync_balance(
        tenant_id=principal.tenant_id,
        unidade_administrativa_id=payload.unidade_administrativa_id,
        environment=payload.environment,
        config=config,
        agencia=payload.agencia,
        conta=payload.conta,
        data=payload.data,
    )
    return BankAccountSyncStep.model_validate(step)


@router.post("/saldo/sync-all", response_model=BankAccountSyncBatch)
async def sync_saldo_all_endpoint(
    payload: _SaldoTodasPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> BankAccountSyncBatch:
    """Sincroniza saldo de todas as contas habilitadas da UA na data."""
    _ = db
    config = await _load_config_or_409(
        principal,
        payload.environment,
        unidade_administrativa_id=payload.unidade_administrativa_id,
    )
    if not config.enabled_bank_accounts():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Nenhuma conta bancaria habilitada nesta UA. Cadastre contas "
                "na aba 'Contas bancarias' antes de sincronizar."
            ),
        )
    steps = await sync_balance_all_accounts(
        tenant_id=principal.tenant_id,
        unidade_administrativa_id=payload.unidade_administrativa_id,
        environment=payload.environment,
        config=config,
        data=payload.data,
    )
    return _aggregate_steps(steps)


# ─── Endpoints: EXTRATO ─────────────────────────────────────────────────────


@router.post("/extrato/sync", response_model=BankAccountSyncStep)
async def sync_extrato_endpoint(
    payload: _ExtratoUmaContaPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> BankAccountSyncStep:
    """Sincroniza extrato de UMA conta no periodo."""
    _ = db
    if payload.data_final < payload.data_inicial:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="data_final nao pode ser anterior a data_inicial.",
        )
    config = await _load_config_or_409(
        principal,
        payload.environment,
        unidade_administrativa_id=payload.unidade_administrativa_id,
    )
    _ensure_account_in_config(config, payload.agencia, payload.conta)
    step = await sync_statement(
        tenant_id=principal.tenant_id,
        unidade_administrativa_id=payload.unidade_administrativa_id,
        environment=payload.environment,
        config=config,
        agencia=payload.agencia,
        conta=payload.conta,
        inicio=payload.data_inicial,
        fim=payload.data_final,
    )
    return BankAccountSyncStep.model_validate(step)


@router.post("/extrato/sync-all", response_model=BankAccountSyncBatch)
async def sync_extrato_all_endpoint(
    payload: _ExtratoTodasPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> BankAccountSyncBatch:
    """Sincroniza extrato de todas as contas habilitadas da UA no periodo."""
    _ = db
    if payload.data_final < payload.data_inicial:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="data_final nao pode ser anterior a data_inicial.",
        )
    config = await _load_config_or_409(
        principal,
        payload.environment,
        unidade_administrativa_id=payload.unidade_administrativa_id,
    )
    if not config.enabled_bank_accounts():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Nenhuma conta bancaria habilitada nesta UA. Cadastre contas "
                "na aba 'Contas bancarias' antes de sincronizar."
            ),
        )
    steps = await sync_statement_all_accounts(
        tenant_id=principal.tenant_id,
        unidade_administrativa_id=payload.unidade_administrativa_id,
        environment=payload.environment,
        config=config,
        inicio=payload.data_inicial,
        fim=payload.data_final,
    )
    return _aggregate_steps(steps)
