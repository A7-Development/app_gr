"""Persistencia da conciliacao de cobranca: ocorrencias (bronze) + wh_boleto.

- `persist_ocorrencias` grava os registros de detalhe parseados no bronze
  (`wh_cnab_raw_ocorrencia`), vinculados ao arquivo.
- `upsert_boletos` grava/atualiza o canonico `wh_boleto` por
  (tenant, banco_origem, numero_documento, data_ref) -- re-rodar o mesmo dia
  atualiza o estado vigente em vez de duplicar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse.boleto import Boleto
from app.warehouse.cnab_raw_arquivo import CnabRawArquivo
from app.warehouse.cnab_raw_ocorrencia import CnabRawOcorrencia

# Colunas mutaveis de wh_boleto atualizadas no conflito (a chave UQ + id +
# source_type ficam fixos).
_BOLETO_UPDATE_COLS = (
    "nosso_numero",
    "sacado_documento",
    "sacado_nome",
    "valor_boleto",
    "valor_pago",
    "data_vencimento",
    "data_pagamento",
    "estado",
    "codigo_ocorrencia",
    "data_ocorrencia",
    "arquivo_id",
    "source_id",
    "ingested_by_version",
    "trust_level",
)


# Postgres/asyncpg limita um statement a 32767 parametros (bind). Um retorno
# CNAB grande (muitos titulos num dia) estoura o INSERT multi-VALUES, entao
# inserimos em chunks. Tamanhos folgados: ocorrencia ~10 cols, boleto ~20 cols.
_CHUNK_OCORRENCIA = 2000
_CHUNK_BOLETO = 800


async def persist_ocorrencias(
    db: AsyncSession,
    *,
    arquivo: CnabRawArquivo,
    ocorrencias: list[Any],
    fetched_at: datetime | None = None,
) -> int:
    """Insere as ocorrencias parseadas no bronze. Returns quantas gravou.

    `ocorrencias` sao objetos com `.linha_num`, `.tipo_registro`, `.payload`
    (ex.: `OcorrenciaParsed` do parser). Idempotencia macro e do arquivo (UQ
    por sha): so chamamos isto quando o arquivo foi inserido agora.
    """
    if not ocorrencias:
        return 0
    fetched_at = fetched_at or datetime.now(UTC)
    rows = [
        {
            "id": uuid4(),
            "tenant_id": arquivo.tenant_id,
            "arquivo_id": arquivo.id,
            "banco": arquivo.banco,
            "tipo_arquivo": arquivo.tipo_arquivo,
            "linha_num": o.linha_num,
            "tipo_registro": o.tipo_registro,
            "payload": o.payload,
            "fetched_at": fetched_at,
            "fetched_by_version": arquivo.fetched_by_version,
        }
        for o in ocorrencias
    ]
    for i in range(0, len(rows), _CHUNK_OCORRENCIA):
        await db.execute(
            pg_insert(CnabRawOcorrencia), rows[i : i + _CHUNK_OCORRENCIA]
        )
    return len(rows)


async def upsert_boletos(db: AsyncSession, values: list[dict[str, Any]]) -> int:
    """Upsert de wh_boleto por uq_wh_boleto. Returns quantos boletos afetou."""
    if not values:
        return 0
    rows = [{"id": uuid4(), **v} for v in values]
    for i in range(0, len(rows), _CHUNK_BOLETO):
        chunk = rows[i : i + _CHUNK_BOLETO]
        stmt = pg_insert(Boleto).values(chunk)
        update_set: dict[str, Any] = {
            col: getattr(stmt.excluded, col) for col in _BOLETO_UPDATE_COLS
        }
        update_set["ingested_at"] = func.now()
        stmt = stmt.on_conflict_do_update(
            constraint="uq_wh_boleto", set_=update_set
        )
        await db.execute(stmt)
    return len(rows)
