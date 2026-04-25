"""ETL QiTech: fetch -> raw (bronze) -> mapper -> canonico (silver).

Implementa o padrao raw->canonico definido no CLAUDE.md secao 13.2 para todos os
endpoints /netreport/report/market/{tipo}/{data}. Fluxo de cada endpoint:

    fetch_market_report(...)                    # JSON cru da QiTech
        -> upsert wh_qitech_raw_relatorio       # 1 linha por (tenant, tipo, data)
        -> map_<tipo>(payload, ...) -> rows     # mapper puro (sem I/O)
        -> bulk upsert wh_<entidade>            # canonico, idempotente

A persistencia da raw acontece em **transacao separada** da canonica de proposito:
- Raw e a fonte de verdade. Tem que sobreviver mesmo se o mapper quebrar
  (caso contrario, perdemos o payload e nao conseguimos depurar offline).
- Bug no mapper => corrige + re-roda mapper sobre raw existente, sem novo
  round-trip a API paga.

Cada `sync_<tipo>` retorna um `step` (dict) com metricas; `sync_all` agrega
N steps + grava 1 entry em `decision_log`.

Endpoints registrados no MVP:
    - outros-fundos -> wh_posicao_cota_fundo

Para adicionar endpoint novo: criar mapper em `mappers/<tipo>.py`, criar
`sync_<tipo>` aqui, registrar em `_PIPELINE`.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta
from itertools import islice
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechHttpError
from app.modules.integracoes.adapters.admin.qitech.hashing import sha256_of_row
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_conta_corrente,
    map_cpr,
    map_demonstrativo_caixa,
    map_mec,
    map_outros_ativos,
    map_outros_fundos,
    map_rentabilidade,
    map_rf,
    map_rf_compromissadas,
    map_tesouraria,
)
from app.modules.integracoes.adapters.admin.qitech.reports import (
    fetch_market_report,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.movimento_caixa import MovimentoCaixa
from app.warehouse.posicao_compromissada import PosicaoCompromissada
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
from app.warehouse.posicao_outros_ativos import PosicaoOutrosAtivos
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio
from app.warehouse.rentabilidade_fundo import RentabilidadeFundo
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente
from app.warehouse.saldo_tesouraria import SaldoTesouraria

CHUNK_SIZE = 1000
MAX_PG_PARAMS = 30000  # margem abaixo do limite asyncpg/Postgres de 32767


def _chunked(iterable: list, size: int):
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


# ---- Persistencia raw ---------------------------------------------------


def _infer_http_status(payload: Any, tipo_de_mercado: str) -> int:
    """Reconstroi o status HTTP semantico a partir do shape do body.

    `fetch_market_report` ja achatou 200 e 400-com-shape-canonico em "sucesso"
    (ambos retornam body). Mas pra raw queremos preservar a distincao:
        - 200: tem dados (lista nao vazia em `relatórios.<tipo>`)
        - 400: envelope vazio (sem dados pra esse tipo neste dia)

    Heuristica:
        body == {"relatórios": {<tipo>: [<>=1 itens]}}        -> 200
        body == {"relatórios": {}, "message": "Nao ha..."}    -> 400
    """
    if not isinstance(payload, dict):
        return 200  # shape inesperado mas chegou body — tratamos como 200
    rel = payload.get("relatórios")
    if isinstance(rel, dict):
        items = rel.get(tipo_de_mercado)
        if isinstance(items, list) and items:
            return 200
    # Envelope vazio canonico ou shape nao conforme.
    return 400


async def _upsert_raw(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    tipo_de_mercado: str,
    data_posicao: date,
    payload: dict[str, Any],
    http_status: int,
) -> None:
    """Grava 1 linha em `wh_qitech_raw_relatorio` (idempotente por UQ).

    Re-roda o mesmo dia substitui payload + atualiza `fetched_at` e
    `payload_sha256` — preserva historico apenas se conteudo mudou (sha bate).
    """
    row = {
        "tenant_id": tenant_id,
        "tipo_de_mercado": tipo_de_mercado,
        "data_posicao": data_posicao,
        "payload": payload,
        "http_status": http_status,
        "payload_sha256": sha256_of_row(payload),
        "fetched_at": datetime.now(UTC),
        "fetched_by_version": ADAPTER_VERSION,
    }
    stmt = pg_insert(QiTechRawRelatorio.__table__).values(row)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_wh_qitech_raw_relatorio",
        set_={
            "payload": stmt.excluded.payload,
            "http_status": stmt.excluded.http_status,
            "payload_sha256": stmt.excluded.payload_sha256,
            "fetched_at": stmt.excluded.fetched_at,
            "fetched_by_version": stmt.excluded.fetched_by_version,
        },
    )
    await db.execute(stmt)


# ---- Persistencia canonica ----------------------------------------------


async def _bulk_upsert_canonical(
    db: AsyncSession, model, rows: list[dict], conflict_columns: list[str]
) -> int:
    """Upsert idempotente em chunks (replica do padrao Bitfin).

    Resolve 3 problemas conhecidos do `pg_insert().values(rows)`:
    1. **Limite de params**: n_rows * n_cols < 32767 (limite asyncpg).
    2. **Normalizacao de chaves**: bulk VALUES exige rows homogeneas; rows do
       mapper podem omitir chaves quando valor e None — preenchemos None.
    3. **Deduplicacao**: ON CONFLICT falha se o mesmo batch tem duas linhas
       com mesma unique key. Mantem a ultima ocorrencia.
    """
    if not rows:
        return 0

    all_columns = [c.name for c in model.__table__.columns if c.name != "id"]
    normalized = [{col: row.get(col) for col in all_columns} for row in rows]

    seen: dict[tuple, dict] = {}
    for r in normalized:
        seen[tuple(r[c] for c in conflict_columns)] = r
    deduped = list(seen.values())

    chunk_size = max(1, min(CHUNK_SIZE, MAX_PG_PARAMS // len(all_columns)))
    update_cols_names = [
        c.name
        for c in model.__table__.columns
        if c.name not in {"id", *conflict_columns, "ingested_at"}
    ]

    total = 0
    for chunk in _chunked(deduped, chunk_size):
        stmt = pg_insert(model.__table__).values(chunk)
        update_set = {name: stmt.excluded[name] for name in update_cols_names}
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_columns, set_=update_set
        )
        await db.execute(stmt)
        total += len(chunk)
    return total


# ---- Generic endpoint sync ---------------------------------------------


async def _sync_endpoint(
    *,
    tipo_de_mercado: str,
    mapper: Any,  # Callable[..., list[dict]] — typing relaxado pra evitar import circular
    model: Any,
    conflict_columns: list[str],
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """Pipeline generico fetch -> raw -> mapper -> canonico para 1 endpoint.

    Substitui ~80 linhas de boilerplate por endpoint. Cada `sync_<tipo>`
    e uma chamada curta a esta funcao especificando o tipo, mapper e model.

    Pipeline:
        1. Fetch via httpx auth client (token cacheado por tenant+env).
        2. Upsert raw (transacao 1) — sempre persiste, mesmo se mapper falhar.
        3. Map payload -> linhas canonicas (via `mapper`).
        4. Upsert canonico (transacao 2) — independente da raw.

    Retorna `step` com metricas. Erros sao capturados em `step.errors` e
    NAO propagam — `sync_all` distingue falha por endpoint de catastrofica.
    """
    t0 = time.monotonic()
    step: dict[str, Any] = {
        "name": tipo_de_mercado,
        "tipo_de_mercado": tipo_de_mercado,
        "data_posicao": data_posicao.isoformat(),
        "ok": False,
        "raw_http_status": None,
        "raw_persisted": False,
        "canonical_rows_upserted": 0,
        "errors": [],
        "elapsed_seconds": 0.0,
    }

    # --- 1. Fetch -------------------------------------------------------
    try:
        async with build_async_client(
            tenant_id=tenant_id, environment=environment, config=config
        ) as client:
            payload = await fetch_market_report(
                client=client,
                tipo_de_mercado=tipo_de_mercado,
                posicao=data_posicao,
            )
    except QiTechHttpError as e:
        step["errors"].append(f"fetch: HTTP {e.status_code}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step
    except Exception as e:
        step["errors"].append(f"fetch: {type(e).__name__}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step

    step["raw_http_status"] = _infer_http_status(payload, tipo_de_mercado)

    # --- 2. Persiste raw (transacao isolada) ----------------------------
    if not isinstance(payload, dict):
        step["errors"].append(
            f"raw: payload com shape inesperado ({type(payload).__name__}); raw nao gravada"
        )
    else:
        try:
            async with AsyncSessionLocal() as db:
                await _upsert_raw(
                    db,
                    tenant_id=tenant_id,
                    tipo_de_mercado=tipo_de_mercado,
                    data_posicao=data_posicao,
                    payload=payload,
                    http_status=step["raw_http_status"],
                )
                await db.commit()
            step["raw_persisted"] = True
        except Exception as e:
            step["errors"].append(f"raw: {type(e).__name__}: {e}")

    # --- 3. Map ---------------------------------------------------------
    try:
        canonical_rows = mapper(
            payload=payload if isinstance(payload, dict) else {},
            tenant_id=tenant_id,
            data_posicao=data_posicao,
        )
    except Exception as e:
        step["errors"].append(f"map: {type(e).__name__}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step

    # --- 4. Persiste canonico (transacao isolada) -----------------------
    if canonical_rows:
        try:
            async with AsyncSessionLocal() as db:
                count = await _bulk_upsert_canonical(
                    db, model, canonical_rows, conflict_columns
                )
                await db.commit()
            step["canonical_rows_upserted"] = count
        except Exception as e:
            step["errors"].append(f"canonical: {type(e).__name__}: {e}")
            step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
            return step

    step["ok"] = not step["errors"]
    step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
    return step


# ---- Sync por endpoint (1 thin wrapper por tipo) -----------------------


async def sync_outros_fundos(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """outros-fundos -> wh_posicao_cota_fundo."""
    return await _sync_endpoint(
        tipo_de_mercado="outros-fundos",
        mapper=map_outros_fundos,
        model=PosicaoCotaFundo,
        conflict_columns=["tenant_id", "source_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
    )


async def sync_conta_corrente(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """conta-corrente -> wh_saldo_conta_corrente."""
    return await _sync_endpoint(
        tipo_de_mercado="conta-corrente",
        mapper=map_conta_corrente,
        model=SaldoContaCorrente,
        conflict_columns=["tenant_id", "source_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
    )


async def sync_tesouraria(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """tesouraria -> wh_saldo_tesouraria."""
    return await _sync_endpoint(
        tipo_de_mercado="tesouraria",
        mapper=map_tesouraria,
        model=SaldoTesouraria,
        conflict_columns=["tenant_id", "source_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
    )


async def sync_outros_ativos(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """outros-ativos -> wh_posicao_outros_ativos."""
    return await _sync_endpoint(
        tipo_de_mercado="outros-ativos",
        mapper=map_outros_ativos,
        model=PosicaoOutrosAtivos,
        conflict_columns=["tenant_id", "source_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
    )


async def sync_demonstrativo_caixa(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """demonstrativo-caixa -> wh_movimento_caixa."""
    return await _sync_endpoint(
        tipo_de_mercado="demonstrativo-caixa",
        mapper=map_demonstrativo_caixa,
        model=MovimentoCaixa,
        conflict_columns=["tenant_id", "source_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
    )


async def sync_cpr(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """cpr -> wh_cpr_movimento."""
    return await _sync_endpoint(
        tipo_de_mercado="cpr",
        mapper=map_cpr,
        model=CprMovimento,
        conflict_columns=["tenant_id", "source_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
    )


async def sync_mec(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """mec -> wh_mec_evolucao_cotas."""
    return await _sync_endpoint(
        tipo_de_mercado="mec",
        mapper=map_mec,
        model=MecEvolucaoCotas,
        conflict_columns=["tenant_id", "source_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
    )


async def sync_rentabilidade(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """rentabilidade -> wh_rentabilidade_fundo."""
    return await _sync_endpoint(
        tipo_de_mercado="rentabilidade",
        mapper=map_rentabilidade,
        model=RentabilidadeFundo,
        conflict_columns=["tenant_id", "source_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
    )


async def sync_rf(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """rf -> wh_posicao_renda_fixa."""
    return await _sync_endpoint(
        tipo_de_mercado="rf",
        mapper=map_rf,
        model=PosicaoRendaFixa,
        conflict_columns=["tenant_id", "source_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
    )


async def sync_rf_compromissadas(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
) -> dict[str, Any]:
    """rf-compromissadas -> wh_posicao_compromissada."""
    return await _sync_endpoint(
        tipo_de_mercado="rf-compromissadas",
        mapper=map_rf_compromissadas,
        model=PosicaoCompromissada,
        conflict_columns=["tenant_id", "source_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
    )


# ---- Master orchestrator -------------------------------------------------


# (nome_endpoint, sync_fn). Adicionar endpoint novo = adicionar tupla.
_PIPELINE: tuple[
    tuple[str, Any], ...
] = (
    ("outros-fundos", sync_outros_fundos),
    ("conta-corrente", sync_conta_corrente),
    ("tesouraria", sync_tesouraria),
    ("outros-ativos", sync_outros_ativos),
    ("demonstrativo-caixa", sync_demonstrativo_caixa),
    ("cpr", sync_cpr),
    ("mec", sync_mec),
    ("rentabilidade", sync_rentabilidade),
    ("rf", sync_rf),
    ("rf-compromissadas", sync_rf_compromissadas),
)


def _resolve_data_posicao(since: date | None) -> date:
    """No QiTech, `since` representa **data alvo** do sync, nao "desde quando".

    Cada relatorio /market/ e por dia exato (`/{aaaa-mm-dd}` no path). Quando
    o caller nao especifica, usamos D-1 em UTC porque a QiTech publica os
    relatorios do dia X ate ~3h da manha do dia X+1; D-1 garante dado
    consolidado.
    """
    if since is not None:
        return since
    return (datetime.now(UTC) - timedelta(days=1)).date()


async def sync_all(
    tenant_id: UUID,
    config: QiTechConfig,
    since: date | None = None,
    *,
    environment: Environment = Environment.PRODUCTION,
    triggered_by: str = "system:scheduler",
) -> dict[str, Any]:
    """Executa todos os syncs registrados em `_PIPELINE` + grava decision_log.

    Isolamento entre endpoints: falha em 1 endpoint NAO impede o proximo
    rodar (cada `sync_<tipo>` ja captura suas exceptions e devolve `step`
    com `errors`). Falha catastrofica (raise saindo do `sync_<tipo>`) e
    capturada aqui e vai pra `errors` agregado.
    """
    started_at = datetime.now(UTC)
    t0 = time.monotonic()
    data_posicao = _resolve_data_posicao(since)

    steps: list[dict[str, Any]] = []
    errors: list[str] = []
    rows_total = 0

    for nome, sync_fn in _PIPELINE:
        try:
            step = await sync_fn(
                tenant_id=tenant_id,
                environment=environment,
                config=config,
                data_posicao=data_posicao,
            )
            steps.append(step)
            rows_total += int(step.get("canonical_rows_upserted") or 0)
            for err in step.get("errors") or []:
                errors.append(f"{nome}: {err}")
        except Exception as e:
            errors.append(f"{nome}: {type(e).__name__}: {e}")

    elapsed = time.monotonic() - t0
    summary: dict[str, Any] = {
        "ok": not errors,
        "adapter_version": ADAPTER_VERSION,
        "tenant_id": str(tenant_id),
        "environment": environment.value,
        "data_posicao": data_posicao.isoformat(),
        "started_at": started_at.isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "rows_ingested": rows_total,
        "steps": steps,
        "errors": errors,
        "since": since.isoformat() if since else None,
        "triggered_by": triggered_by,
    }

    # Append-only audit trail (CLAUDE.md secao 14.2).
    async with AsyncSessionLocal() as db:
        db.add(
            DecisionLog(
                tenant_id=tenant_id,
                decision_type=DecisionType.SYNC,
                inputs_ref={
                    "data_posicao": summary["data_posicao"],
                    "environment": environment.value,
                    "since": summary["since"],
                },
                rule_or_model="qitech_adapter",
                rule_or_model_version=ADAPTER_VERSION,
                output=summary,
                explanation=(
                    "OK" if not errors else f"{len(errors)} erro(s): {errors}"
                ),
                triggered_by=triggered_by,
            )
        )
        await db.commit()

    return summary
