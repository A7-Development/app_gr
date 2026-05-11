"""ETL orquestrador: MSSQL (ANALYTICS + UNLTD_A7CREDIT) -> gr_db warehouse.

Desenho:
- Cada tabela-alvo tem uma funcao `sync_<tabela>(tenant_id, since)`.
- Extract roda em thread pool (pyodbc e sync); Load em async (SQLAlchemy).
- Upsert idempotente via `ON CONFLICT DO UPDATE` (Postgres).
- Cada sync grava uma entrada em `decision_log` (sistema auditavel).
- Proveniencia completa em cada linha (source_type, source_id, hash_origem, ...).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, date, datetime
from itertools import islice
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import fetch_rows
from app.modules.integracoes.adapters.erp.bitfin.hashing import sha256_of_row
from app.modules.integracoes.adapters.erp.bitfin.queries import analytics, bitfin
from app.modules.integracoes.adapters.erp.bitfin.version import ADAPTER_VERSION
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.warehouse.bitfin_raw_dre import (
    TIPO_ORIGEM_DEMONSTRATIVO,
    TIPO_ORIGEM_VW_DRE,
    BitfinRawDre,
)
from app.warehouse.caixa_snapshot import CaixaSnapshot
from app.warehouse.dim import (
    DimDreClassificacao,
    DimMes,
    DimProduto,
    DimUnidadeAdministrativa,
)
from app.warehouse.dre import DreMensal
from app.warehouse.operacao import Operacao, OperacaoItem
from app.warehouse.titulo import Titulo
from app.warehouse.titulo_snapshot import TituloSnapshot

CHUNK_SIZE = 1000
MAX_PG_PARAMS = 30000  # margem abaixo do limite asyncpg/Postgres de 32767
EPOCH = date(1900, 1, 1)


def _chunked(iterable: list, size: int):
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


def _provenance(source_id: Any, row: dict, source_updated_at: Any = None) -> dict:
    """Campos de proveniencia adicionados a cada linha antes do insert."""
    return {
        "source_type": SourceType.ERP_BITFIN,
        "source_id": str(source_id),
        "source_updated_at": source_updated_at,
        "ingested_at": datetime.now(UTC),
        "hash_origem": sha256_of_row(row),
        "ingested_by_version": ADAPTER_VERSION,
        "trust_level": TrustLevel.HIGH,
        "collected_by": None,
    }


# ---- Mappers ----


def _map_titulo_snapshot(row: dict, tenant_id: UUID) -> dict:
    return {
        "tenant_id": tenant_id,
        **row,
        **_provenance(row["snapshot_id"], row, row["data_ref"]),
    }


def _map_operacao(row: dict, tenant_id: UUID) -> dict:
    # OperacaoResultado nao-preenchido = operacao nao efetivada ainda; usa defaults
    metric_defaults = {
        "prazo_medio_real": 0,
        "prazo_medio_cobrado": 0,
        "total_bruto": 0,
        "total_liquido": 0,
        "total_de_juros": 0,
        "total_de_ad_valorem": 0,
        "total_de_iof": 0,
        "total_de_imposto": 0,
        "total_de_rebate": 0,
        "valor_medio_dos_titulos": 0,
        "quantidade_de_sacados": 0,
        "taxa_de_juros": 0,
        "taxa_de_ad_valorem": 0,
        "taxa_de_iof": 0,
        "taxa_de_imposto": 0,
        "taxa_de_rebate": 0,
        "spread": 0,
        "fator_de_desconto_cobrado": 0,
        "fator_de_desconto_real": 0,
        "floating_para_prazo": 0,
        "total_das_consultas_financeiras": 0,
        "total_dos_registros_bancarios": 0,
        "total_das_consultas_fiscais": 0,
        "total_dos_comunicados_de_cessao": 0,
        "total_dos_documentos_digitais": 0,
        "total_dos_descontos_ou_abatimentos": 0,
    }
    merged = {**metric_defaults, **{k: v for k, v in row.items() if v is not None}}
    return {
        "tenant_id": tenant_id,
        **merged,
        **_provenance(
            row["operacao_id"], row, row.get("data_de_efetivacao") or row["data_de_cadastro"]
        ),
    }


def _map_operacao_item(row: dict, tenant_id: UUID) -> dict:
    defaults = {
        "valor_base": 0,
        "valor_liquido": 0,
        "valor_presente": 0,
        "valor_de_juros": 0,
        "valor_do_ad_valorem": 0,
        "valor_do_iof": 0,
        "valor_do_rebate": 0,
        "saldo_devedor": 0,
        "prazo_real": 0,
        "prazo_cobrado": 0,
        "sugerido_para_exclusao": False,
    }
    merged = {**defaults, **{k: v for k, v in row.items() if v is not None}}
    return {
        "tenant_id": tenant_id,
        **merged,
        **_provenance(row["item_da_operacao_id"], row, row.get("data_de_vencimento_original")),
    }


def _map_titulo(row: dict, tenant_id: UUID) -> dict:
    defaults = {
        "valor_do_pagamento": 0,
        "valor_liquido": 0,
        "saldo_devedor": 0,
        "sustado_judicialmente": False,
    }
    merged = {**defaults, **{k: v for k, v in row.items() if v is not None}}
    return {
        "tenant_id": tenant_id,
        **merged,
        **_provenance(row["titulo_id"], row, row["data_da_situacao"]),
    }


def _map_dre_mensal(row: dict, tenant_id: UUID) -> dict:
    # Unique key e compost; source_id sintetico para manter Auditable consistente
    source_id = (
        f"{row['competencia']}|{row['grupo_dre']}|{row['subgrupo']}|"
        f"{row['descricao']}|{row.get('entidade_id')}|{row.get('produto_id')}|{row['fonte']}"
    )
    return {
        "tenant_id": tenant_id,
        **row,
        **_provenance(source_id, row, row["competencia"]),
    }


def _map_dim_mes(row: dict, tenant_id: UUID) -> dict:
    return {
        "tenant_id": tenant_id,
        **row,
        **_provenance(row["mes_ano"], row, row["mes_ano"]),
    }


def _map_dim_dre_classificacao(row: dict, tenant_id: UUID) -> dict:
    return {
        "tenant_id": tenant_id,
        **row,
        **_provenance(row["classificacao_id"], row, None),
    }


def _map_dim_ua(row: dict, tenant_id: UUID) -> dict:
    """Mapeia Bitfin.UnidadeAdministrativa -> wh_dim_unidade_administrativa.

    Campos especiais:
    - `Ativa` vem do MSSQL como bool (True/False) — preserva tipo.
    - `Alias` vira `nome` (nao ha campo "Nome" no Bitfin).
    - `Classe` opcional (pode ser None).
    """
    return {
        "tenant_id": tenant_id,
        **row,
        **_provenance(row["ua_id"], row, None),
    }


def _map_dim_produto(row: dict, tenant_id: UUID) -> dict:
    """Mapeia Bitfin.Produto -> wh_dim_produto.

    - `Sigla` e `Descricao` ja vem nomeados pelo SELECT (`sigla`, `nome`).
    - `produto_de_risco` vem como bool do MSSQL.
    - `tipo_de_contrato` pode ser None.
    """
    return {
        "tenant_id": tenant_id,
        **row,
        **_provenance(row["produto_id"], row, None),
    }


def _map_caixa_snapshot(row: dict, tenant_id: UUID, data_snapshot: date) -> dict:
    """Mapeia ContaBancaria + ContaCorrente + UA + flags -> wh_caixa_snapshot.

    Granularidade silver: 1 linha por (tenant, conta_bancaria, data_snapshot).
    Ao re-rodar a sync no mesmo dia, UPSERT substitui a row de hoje (saldo
    atualizado). Historico cresce 1 row por (conta, dia).

    Flags `eh_caucao` / `eh_travada` chegam como int 0/1 do CASE WHEN no
    MSSQL — convertidos para bool aqui.
    """
    return {
        "tenant_id": tenant_id,
        "data_snapshot": data_snapshot,
        **row,
        "eh_caucao": bool(row.get("eh_caucao")),
        "eh_travada": bool(row.get("eh_travada")),
        **_provenance(row["conta_bancaria_id"], row, None),
    }


# ---- Upsert helpers ----


async def _bulk_upsert(
    db: AsyncSession, model, rows: list[dict], conflict_columns: list[str]
) -> int:
    """Upsert idempotente em chunks. Retorna total de rows afetadas.

    Resolve 3 problemas:
    1. **Chunk dinamico**: n_rows * n_cols deve ficar abaixo do limite asyncpg
       (32767 params). Calculado a partir do numero de colunas da tabela.
    2. **Row normalization**: bulk `VALUES` exige que todas as rows tenham as
       mesmas chaves. Rows vindas dos mappers podem ter keys faltando quando
       um campo e None/nullable — preenchemos com None explicito.
    3. **Deduplicacao**: `ON CONFLICT DO UPDATE` falha se o mesmo batch tem
       duas linhas com o mesmo unique key. Deduplicamos mantendo a ultima.
    """
    if not rows:
        return 0

    # 1. Lista de colunas do model (exceto `id` autogerado)
    all_columns = [c.name for c in model.__table__.columns if c.name != "id"]

    # 2. Normalizar: toda row tem TODAS as chaves (None para ausentes)
    normalized = [{col: row.get(col) for col in all_columns} for row in rows]

    # 3. Deduplicar por conflict_columns (mantem ultima ocorrencia)
    seen: dict[tuple, dict] = {}
    for row in normalized:
        key = tuple(row[c] for c in conflict_columns)
        seen[key] = row
    deduped = list(seen.values())

    # 4. Chunk dinamico baseado no numero de colunas
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
        stmt = stmt.on_conflict_do_update(index_elements=conflict_columns, set_=update_set)
        await db.execute(stmt)
        total += len(chunk)
    await db.commit()
    return total


# ---- Sync functions (uma por tabela alvo) ----


async def sync_titulo_snapshot(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_analytics, analytics.SELECT_SNAPSHOT_TITULO, (cutoff,)
    )
    mapped = [_map_titulo_snapshot(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(
            db, TituloSnapshot, mapped, ["tenant_id", "data_ref", "source_id"]
        )
    return {"table": "wh_titulo_snapshot", "rows": count}


async def sync_operacao(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_OPERACAO, (cutoff,)
    )
    mapped = [_map_operacao(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, Operacao, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_operacao", "rows": count}


async def sync_operacao_item(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_OPERACAO_ITEM
    )
    mapped = [_map_operacao_item(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, OperacaoItem, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_operacao_item", "rows": count}


async def sync_titulo(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_TITULO, (cutoff,)
    )
    mapped = [_map_titulo(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, Titulo, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_titulo", "rows": count}


async def sync_dre_mensal(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_analytics, analytics.SELECT_DRE, (cutoff,)
    )
    mapped = [_map_dre_mensal(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, DreMensal, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_dre_mensal", "rows": count}


# ---- Bronze (raw) sync handlers --------------------------------------------
#
# Camada raw do DRE Bitfin (CLAUDE.md §13.2). Cada handler agrupa as linhas
# do fetch por competencia e grava 1 row de bronze por competencia
# (payload = JSONB array de linhas). UQ (tenant, tipo_origem, competencia,
# payload_sha256) dedupe fetch identico via ON CONFLICT DO NOTHING — fetch
# com qualquer alteracao no conteudo gera nova row preservando o historico
# de snapshots.


def _group_rows_by_competencia(
    rows: list[dict], competencia_key: str = "competencia"
) -> dict[date, list[dict]]:
    """Agrupa rows do fetch por competencia (descartando colunas exclusivamente
    de snapshot, como `snapshot_at` do DemonstrativoDeResultado, que mudam
    a cada rebuild da fonte e invalidariam o dedup via sha)."""
    by_comp: dict[date, list[dict]] = {}
    for row in rows:
        comp = row[competencia_key]
        # Conteudo "negocio" — sem snapshot_at (timestamp do rebuild do Bitfin).
        content = {k: v for k, v in row.items() if k != "snapshot_at"}
        by_comp.setdefault(comp, []).append(content)
    return by_comp


async def _upsert_bronze_dre(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    tipo_origem: str,
    competencia: date,
    payload: list[dict],
) -> bool:
    """Grava 1 row de bronze. Retorna True se inseriu, False se ja existia
    (mesmo conteudo -> mesmo sha -> ON CONFLICT DO NOTHING)."""
    sha = sha256_of_row({"items": payload})
    row = {
        "tenant_id": tenant_id,
        "tipo_origem": tipo_origem,
        "competencia": competencia,
        "payload": payload,
        "row_count": len(payload),
        "payload_sha256": sha,
        "fetched_at": datetime.now(UTC),
        "fetched_by_version": ADAPTER_VERSION,
    }
    stmt = pg_insert(BitfinRawDre.__table__).values(row).on_conflict_do_nothing(
        constraint="uq_wh_bitfin_raw_dre"
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


async def sync_bitfin_raw_dre_demonstrativo(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Bronze: snapshot granular de `UNLTD_A7CREDIT.dbo.DemonstrativoDeResultado`.

    Fetch full por competencia (>= since). Bitfin rebuilda o snapshot
    inteiro de cada competencia periodicamente; o dedup via sha garante
    que rebuild sem mudanca de conteudo seja no-op.
    """
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows,
        config,
        config.database_bitfin,
        bitfin.SELECT_DRE_DEMONSTRATIVO_RAW,
        (cutoff,),
    )
    by_comp = _group_rows_by_competencia(rows)
    inserted = 0
    async with AsyncSessionLocal() as db:
        for comp, payload in by_comp.items():
            if await _upsert_bronze_dre(
                db,
                tenant_id=tenant_id,
                tipo_origem=TIPO_ORIGEM_DEMONSTRATIVO,
                competencia=comp,
                payload=payload,
            ):
                inserted += 1
        await db.commit()
    return {
        "table": "wh_bitfin_raw_dre",
        "tipo_origem": TIPO_ORIGEM_DEMONSTRATIVO,
        "competencias_processed": len(by_comp),
        "rows": inserted,
    }


async def sync_bitfin_raw_dre_vw(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Bronze: snapshot consolidado de `ANALYTICS.dbo.vw_DRE`.

    Mantido como espelho do que o Bitfin reporta como DRE — fonte para
    reconciliacao "nossa regra vs Bitfin". O silver `wh_dre_mensal` hoje
    le direto desta view (sync_dre_mensal); PR 3 vai trocar para ler do
    bronze, eliminando o fetch duplicado.
    """
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows,
        config,
        config.database_analytics,
        analytics.SELECT_DRE_VW_RAW,
        (cutoff,),
    )
    by_comp = _group_rows_by_competencia(rows)
    inserted = 0
    async with AsyncSessionLocal() as db:
        for comp, payload in by_comp.items():
            if await _upsert_bronze_dre(
                db,
                tenant_id=tenant_id,
                tipo_origem=TIPO_ORIGEM_VW_DRE,
                competencia=comp,
                payload=payload,
            ):
                inserted += 1
        await db.commit()
    return {
        "table": "wh_bitfin_raw_dre",
        "tipo_origem": TIPO_ORIGEM_VW_DRE,
        "competencias_processed": len(by_comp),
        "rows": inserted,
    }


async def sync_dim_mes(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_analytics, analytics.SELECT_DIM_MES, (EPOCH,)
    )
    mapped = [_map_dim_mes(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, DimMes, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_dim_mes", "rows": count}


async def sync_dim_dre_classificacao(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_analytics, analytics.SELECT_DIM_DRE_CLASSIFICACAO
    )
    mapped = [_map_dim_dre_classificacao(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, DimDreClassificacao, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_dim_dre_classificacao", "rows": count}


async def sync_dim_ua(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Full refresh da dim UA — Bitfin tem poucas linhas (ordem de 3-10)
    e raramente mudam; custo desprezivel."""
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_UNIDADE_ADMINISTRATIVA
    )
    mapped = [_map_dim_ua(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(
            db, DimUnidadeAdministrativa, mapped, ["tenant_id", "source_id"]
        )
    return {"table": "wh_dim_unidade_administrativa", "rows": count}


async def sync_dim_produto(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Full refresh da dim Produto — Bitfin tem ~20 linhas, full table
    sempre. Custo desprezivel."""
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_PRODUTO
    )
    mapped = [_map_dim_produto(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, DimProduto, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_dim_produto", "rows": count}


async def sync_caixa_snapshot(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Snapshot diario do saldo das ContaBancaria-de-UA do tenant.

    `since` ignorado — sempre captura o saldo ATUAL (ContaCorrente.Saldo
    no momento da execucao) e marca `data_snapshot = today`. Multiple
    execucoes de sync no mesmo dia upsertam a mesma row.

    Volume: poucas dezenas de linhas por execucao (uma por conta de UA).
    """
    today = datetime.now(UTC).date()
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_CAIXA_SNAPSHOT
    )
    mapped = [_map_caixa_snapshot(r, tenant_id, today) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(
            db, CaixaSnapshot, mapped, ["tenant_id", "data_snapshot", "source_id"]
        )
    return {"table": "wh_caixa_snapshot", "rows": count}


# ---- Master orchestrator ----

SYNC_PIPELINE = [
    sync_dim_mes,
    sync_dim_dre_classificacao,
    sync_dim_ua,
    sync_dim_produto,
    sync_titulo_snapshot,
    sync_operacao,
    sync_operacao_item,
    sync_titulo,
    # Bronze antes do silver: PR 3 vai refatorar sync_dre_mensal pra ler
    # do bronze, eliminando o fetch duplicado contra vw_DRE.
    sync_bitfin_raw_dre_demonstrativo,
    sync_bitfin_raw_dre_vw,
    sync_dre_mensal,
    sync_caixa_snapshot,
]


async def sync_all(
    tenant_id: UUID,
    config: BitfinConfig,
    since: date | None = None,
    *,
    triggered_by: str = "system:scheduler",
    endpoint_name: str | None = None,
) -> dict[str, Any]:
    """Executa todas as syncs em sequencia + registra no decision_log.

    `triggered_by` identifica quem disparou o ciclo (scheduler automatico,
    bootstrap CLI, ou usuario via API: "user:<uuid>").

    `endpoint_name`: opcional. Quando o caller e o `adapter_sync_endpoint`
    novo (per-endpoint), passa "bitfin.full_sync" para que a entry de
    decision_log carimbe a dimensao endpoint. Caller legacy nao passa,
    e a entry fica com `endpoint_name=None` (compativel com modo legacy).
    """
    started_at = datetime.now(UTC)
    t0 = time.monotonic()
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for sync_fn in SYNC_PIPELINE:
        try:
            result = await sync_fn(tenant_id, config, since=since)
            results.append(result)
        except Exception as e:
            errors.append(f"{sync_fn.__name__}: {type(e).__name__}: {e}")

    elapsed = time.monotonic() - t0
    summary = {
        "adapter_version": ADAPTER_VERSION,
        "started_at": started_at.isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "tables": results,
        "errors": errors,
        "since": since.isoformat() if since else None,
    }

    # Log no decision_log (append-only)
    async with AsyncSessionLocal() as db:
        db.add(
            DecisionLog(
                tenant_id=tenant_id,
                decision_type=DecisionType.SYNC,
                inputs_ref={"since": summary["since"]},
                rule_or_model="bitfin_adapter",
                rule_or_model_version=ADAPTER_VERSION,
                endpoint_name=endpoint_name,
                output=summary,
                explanation=("OK" if not errors else f"{len(errors)} erro(s): {errors}"),
                triggered_by=triggered_by,
            )
        )
        await db.commit()

    return summary
