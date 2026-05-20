"""ETL orchestrators para a familia QiTech /v2/bank-account/*.

Pipeline por chamada:
    1. Fetch (bank_account.fetch_balance / fetch_statement)
    2. Persist raw (wh_qitech_raw_bank_account_balance / _statement)
    3. Map (mappers.bank_account_balance / .bank_account_statement)
    4. Upsert canonico (wh_saldo_bancario_diario / wh_extrato_bancario)

Sao pacotes 1-conta-por-vez. O caller (REST endpoint ou scheduled task)
itera sobre `config.enabled_bank_accounts()` e dispara N chamadas em sequencia
(ou paralelas com semaphore se a Singulare suportar).

Cada `sync_*` devolve um `dict` com metricas detalhadas (mesmo padrao do
custodia.py). O caller agrega esses steps numa estrutura que vai pra
decision_log.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.bank_account import (
    fetch_balance,
    fetch_statement,
)
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechHttpError
from app.modules.integracoes.adapters.admin.qitech.critical_fields import (
    get_critical_fields,
)
from app.modules.integracoes.adapters.admin.qitech.etl import (
    _replace_canonical_partition,
)
from app.modules.integracoes.adapters.admin.qitech.hashing import sha256_of_row
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_bank_account_balance,
    map_bank_account_statement,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION
from app.warehouse.extrato_bancario import ExtratoBancario
from app.warehouse.qitech_raw_bank_account_balance import (
    QiTechRawBankAccountBalance,
)
from app.warehouse.qitech_raw_bank_account_statement import (
    QiTechRawBankAccountStatement,
)
from app.warehouse.saldo_bancario_diario import SaldoBancarioDiario

logger = logging.getLogger(__name__)


def _wrap_payload(payload: Any) -> dict[str, Any]:
    """Embrulha payload nao-dict (lista, scalar) num dict pra caber em JSONB."""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"items": payload}
    return {"value": payload}


# ─── Raw upserts (idempotentes por UQ) ──────────────────────────────────────


async def _upsert_raw_balance(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID,
    agencia: str,
    conta: str,
    data_posicao: date,
    payload: Any,
    http_status: int,
) -> UUID:
    """Retorna o `raw_id` (UUID) da row raw. Mesmo id em re-upsert porque
    a UQ bate. Consumido pelo `_replace_canonical_partition` (Fase 1.3)
    como partition key do DELETE+INSERT no silver wh_saldo_bancario_diario.

    Sem coluna `completeness` aqui — endpoints bank_account nao tem perfil
    de completeness implementado em `completeness.py`. O caller assume
    'complete' por default (HTTP 200 = payload completo neste endpoint).
    """
    payload_json = _wrap_payload(payload)
    row = {
        "tenant_id": tenant_id,
        "unidade_administrativa_id": unidade_administrativa_id,
        "agencia": agencia,
        "conta": conta,
        "data_posicao": data_posicao,
        "payload": payload_json,
        "http_status": http_status,
        "payload_sha256": sha256_of_row(payload_json),
        "fetched_at": datetime.now(UTC),
        "fetched_by_version": ADAPTER_VERSION,
    }
    stmt = pg_insert(QiTechRawBankAccountBalance.__table__).values(row)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_wh_qitech_raw_bank_account_balance",
        set_={
            "payload": stmt.excluded.payload,
            "http_status": stmt.excluded.http_status,
            "payload_sha256": stmt.excluded.payload_sha256,
            "fetched_at": stmt.excluded.fetched_at,
            "fetched_by_version": stmt.excluded.fetched_by_version,
        },
    ).returning(QiTechRawBankAccountBalance.__table__.c.id)
    return (await db.execute(stmt)).scalar_one()


async def _upsert_raw_statement(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID,
    agencia: str,
    conta: str,
    periodo_inicio: date,
    periodo_fim: date,
    payload: Any,
    http_status: int,
) -> UUID:
    """Retorna o `raw_id` (UUID) da row raw. Mesmo id em re-upsert porque
    a UQ bate (UQ inclui `periodo_inicio`/`periodo_fim`, entao re-fetch do
    mesmo periodo bate). Consumido pelo `_replace_canonical_partition`
    (Fase 1.3) como partition key do DELETE+INSERT no silver wh_extrato_bancario.

    Granularidade do raw eh por PERIODO (nao por dia) — extrato bancario
    eh tipicamente puxado por janela. Reprocessar "dia X" puxa o periodo
    que cobre X; o replace-by-partition opera no periodo inteiro, nao no
    dia. UI deve sinalizar isso ao usuario.
    """
    payload_json = _wrap_payload(payload)
    row = {
        "tenant_id": tenant_id,
        "unidade_administrativa_id": unidade_administrativa_id,
        "agencia": agencia,
        "conta": conta,
        "periodo_inicio": periodo_inicio,
        "periodo_fim": periodo_fim,
        "payload": payload_json,
        "http_status": http_status,
        "payload_sha256": sha256_of_row(payload_json),
        "fetched_at": datetime.now(UTC),
        "fetched_by_version": ADAPTER_VERSION,
    }
    stmt = pg_insert(QiTechRawBankAccountStatement.__table__).values(row)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_wh_qitech_raw_bank_account_statement",
        set_={
            "payload": stmt.excluded.payload,
            "http_status": stmt.excluded.http_status,
            "payload_sha256": stmt.excluded.payload_sha256,
            "fetched_at": stmt.excluded.fetched_at,
            "fetched_by_version": stmt.excluded.fetched_by_version,
        },
    ).returning(QiTechRawBankAccountStatement.__table__.c.id)
    return (await db.execute(stmt)).scalar_one()


# ─── Sync orchestrators ─────────────────────────────────────────────────────


async def sync_balance(
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    agencia: str,
    conta: str,
    data: date,
) -> dict[str, Any]:
    """Sincroniza saldo de uma conta-corrente em uma data.

    GET /v2/bank-account/balance/{agencia}/{conta}/{data}
        -> wh_qitech_raw_bank_account_balance (raw)
        -> wh_saldo_bancario_diario (canonico via mapper)

    Retorno: step com `ok`, `raw_http_status`, `raw_persisted`,
    `canonical_rows_upserted`, `errors[]`, `elapsed_seconds`.
    """
    t0 = time.monotonic()
    step: dict[str, Any] = {
        "name": "bank-account/balance",
        "agencia": agencia,
        "conta": conta,
        "data": data.isoformat(),
        "ok": False,
        "raw_http_status": None,
        "raw_persisted": False,
        "canonical_rows_upserted": 0,
        "errors": [],
        "elapsed_seconds": 0.0,
    }

    # 1. Fetch
    try:
        async with build_async_client(
            tenant_id=tenant_id,
            environment=environment,
            config=config,
            unidade_administrativa_id=unidade_administrativa_id,
        ) as client:
            payload, status = await fetch_balance(
                client=client, agencia=agencia, conta=conta, data=data
            )
        step["raw_http_status"] = status
    except QiTechHttpError as e:
        step["errors"].append(f"fetch: HTTP {e.status_code}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step
    except httpx.HTTPError as e:
        step["errors"].append(f"fetch: {type(e).__name__}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step

    # 2. Raw + 4. Canonico (numa transacao so pra atomicidade)
    # raw_id capturado pra ser usado em Fase 1.3 (_replace_canonical_partition).
    try:
        async with AsyncSessionLocal() as db:
            raw_id = await _upsert_raw_balance(
                db,
                tenant_id=tenant_id,
                unidade_administrativa_id=unidade_administrativa_id,
                agencia=agencia,
                conta=conta,
                data_posicao=data,
                payload=payload,
                http_status=status,
            )
            step["raw_persisted"] = True
            step["raw_id"] = str(raw_id)

            # 3. Map
            canonical_rows = map_bank_account_balance(
                payload=payload,
                tenant_id=tenant_id,
                unidade_administrativa_id=unidade_administrativa_id,
                agencia=agencia,
                conta=conta,
                data_posicao=data,
            )

            # 4. Canonical
            # Fase 1.3: replace-by-partition strict no scope raw_id.
            # bank_account.balance nao tem perfil partial em completeness.py
            # (HTTP 200 = complete implicito), entao passamos 'complete' direto
            # — qualquer falha de fetch ja retornou step["errors"] acima e nao
            # chegou aqui. NA mesma transacao do raw, entao tudo ou nada.
            if canonical_rows:
                result = await _replace_canonical_partition(
                    db,
                    SaldoBancarioDiario,
                    canonical_rows,
                    # Business key — ver uq_wh_saldo_bancario_diario.
                    [
                        "tenant_id", "unidade_administrativa_id",
                        "agencia", "conta", "data_posicao",
                    ],
                    raw_id=raw_id,
                    completeness="complete",
                    tenant_id=tenant_id,
                    endpoint_name="bank_account.balance",
                    data_referencia=data,
                    critical_fields_for_audit=get_critical_fields(
                        SaldoBancarioDiario.__tablename__
                    ),
                    unidade_administrativa_id=unidade_administrativa_id,
                )
                step["canonical_rows_upserted"] = result["inserted"]
                step["canonical_mode"] = result["mode"]
                step["canonical_orphans_removed"] = result["orphans_count"]

            await db.commit()
    except Exception as e:
        step["errors"].append(f"persist: {type(e).__name__}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step

    step["ok"] = not step["errors"]
    step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
    return step


async def sync_statement(
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    agencia: str,
    conta: str,
    inicio: date,
    fim: date,
) -> dict[str, Any]:
    """Sincroniza extrato de uma conta-corrente num periodo.

    GET /v2/bank-account/statement/{agencia}/{conta}/{ini}/{fim}
        -> wh_qitech_raw_bank_account_statement (raw)
        -> wh_extrato_bancario (canonico via mapper, N linhas)
    """
    t0 = time.monotonic()
    step: dict[str, Any] = {
        "name": "bank-account/statement",
        "agencia": agencia,
        "conta": conta,
        "periodo_inicio": inicio.isoformat(),
        "periodo_fim": fim.isoformat(),
        "ok": False,
        "raw_http_status": None,
        "raw_persisted": False,
        "canonical_rows_upserted": 0,
        "errors": [],
        "elapsed_seconds": 0.0,
    }

    if fim < inicio:
        step["errors"].append(
            f"periodo invalido: fim ({fim}) anterior a inicio ({inicio})"
        )
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step

    try:
        async with build_async_client(
            tenant_id=tenant_id,
            environment=environment,
            config=config,
            unidade_administrativa_id=unidade_administrativa_id,
        ) as client:
            payload, status = await fetch_statement(
                client=client,
                agencia=agencia,
                conta=conta,
                inicio=inicio,
                fim=fim,
            )
        step["raw_http_status"] = status
    except QiTechHttpError as e:
        step["errors"].append(f"fetch: HTTP {e.status_code}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step
    except httpx.HTTPError as e:
        step["errors"].append(f"fetch: {type(e).__name__}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step

    try:
        async with AsyncSessionLocal() as db:
            # raw_id capturado pra uso em Fase 1.3 (_replace_canonical_partition).
            # Granularidade: 1 raw_id por (ua, agencia, conta, periodo) — todas
            # as silver rows de movimentos no periodo apontam pro mesmo raw_id.
            raw_id = await _upsert_raw_statement(
                db,
                tenant_id=tenant_id,
                unidade_administrativa_id=unidade_administrativa_id,
                agencia=agencia,
                conta=conta,
                periodo_inicio=inicio,
                periodo_fim=fim,
                payload=payload,
                http_status=status,
            )
            step["raw_persisted"] = True
            step["raw_id"] = str(raw_id)

            canonical_rows = map_bank_account_statement(
                payload=payload,
                tenant_id=tenant_id,
                unidade_administrativa_id=unidade_administrativa_id,
                agencia=agencia,
                conta=conta,
            )

            # Fase 1.3: replace-by-partition strict no scope raw_id.
            # Re-fetch do mesmo periodo -> mesmo raw_id -> replace-by-partition
            # deleta movimentos que sumiram do payload novo. Importante: a
            # granularidade aqui eh por PERIODO (nao por dia). Re-sync de
            # "dia X" puxa o periodo que cobre X; o replace opera no periodo
            # inteiro — movimentos de OUTROS dias do mesmo periodo tambem
            # sao reavaliados. Ver _upsert_raw_statement.
            if canonical_rows:
                result = await _replace_canonical_partition(
                    db,
                    ExtratoBancario,
                    canonical_rows,
                    # Business key — ver uq_wh_extrato_bancario.
                    [
                        "tenant_id", "unidade_administrativa_id",
                        "agencia", "conta", "data_lancamento",
                        "valor", "tipo", "descricao", "contrapartida_doc",
                    ],
                    raw_id=raw_id,
                    completeness="complete",
                    tenant_id=tenant_id,
                    endpoint_name="bank_account.statement",
                    data_referencia=inicio,  # data inicial do periodo (audit)
                    critical_fields_for_audit=get_critical_fields(
                        ExtratoBancario.__tablename__
                    ),
                    unidade_administrativa_id=unidade_administrativa_id,
                )
                step["canonical_rows_upserted"] = result["inserted"]
                step["canonical_mode"] = result["mode"]
                step["canonical_orphans_removed"] = result["orphans_count"]

            await db.commit()
    except Exception as e:
        step["errors"].append(f"persist: {type(e).__name__}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step

    step["ok"] = not step["errors"]
    step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
    return step


# ─── Iteradores por todas as contas configuradas na UA ──────────────────────


async def sync_balance_all_accounts(
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data: date,
) -> list[dict[str, Any]]:
    """Itera sobre `config.enabled_bank_accounts()` chamando sync_balance em cada.

    Sequential (nao paralelo) — Singulare nao documenta limite de RPS na
    familia /v2/bank-account/, melhor ir conservador. Se virar gargalo,
    introduzir asyncio.gather com semaphore.
    """
    steps: list[dict[str, Any]] = []
    for acc in config.enabled_bank_accounts():
        step = await sync_balance(
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
            environment=environment,
            config=config,
            agencia=acc.agencia,
            conta=acc.conta,
            data=data,
        )
        steps.append(step)
    return steps


async def sync_statement_all_accounts(
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    inicio: date,
    fim: date,
) -> list[dict[str, Any]]:
    """Itera extrato em todas as contas habilitadas da UA."""
    steps: list[dict[str, Any]] = []
    for acc in config.enabled_bank_accounts():
        step = await sync_statement(
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
            environment=environment,
            config=config,
            agencia=acc.agencia,
            conta=acc.conta,
            inicio=inicio,
            fim=fim,
        )
        steps.append(step)
    return steps
