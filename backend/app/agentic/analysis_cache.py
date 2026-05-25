"""Cache + audit unificados de execucoes do agente (CLAUDE.md §14 + §19).

A tabela `agent_analysis_run` serve aos 2 propositos:

  1. **Cache funcional** — lookup por `(tenant, agent, version, inputs_hash)`
     evita pagar Anthropic 2x pra mesma analise (mesmo fundo + mesma data +
     mesma versao de prompt/persona/expertises).
  2. **Audit trail** — linhagem completa de cada invocacao (audit_version
     composto, modelo usado, tokens, custo, usuario, timestamp).

Chave de cache (`inputs_hash`):
- sha256 canonical de `(audit_version, inputs_snapshot)`. Inclusao do
  `audit_version` garante invalidacao automatica quando prompt/persona muda
  (novo hash != cache antigo → re-roda no v2).

Invalidacao explicita via `invalidated_at` (soft-delete):
- ETL re-ingere dados de uma data → invalidar runs daquela data
- Botao "re-rodar" na UI → invalidar entrada especifica + criar nova

Convencao: 1 entrada VIVA por chave de cache (partial UQ index garante).
Multiplas invalidadas + 1 viva e o pattern historico esperado.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True, frozen=True)
class CachedAnalysis:
    """Resultado de cache hit — output reaproveitado de execucao previa."""

    id: UUID
    output_data: dict[str, Any]
    output_schema_name: str
    model_used: str
    tokens_input: int
    tokens_output: int
    tokens_cache_read: int
    tokens_cache_creation: int
    cost_brl_estimated: Decimal | None
    audit_version: str
    triggered_at: datetime
    age_seconds: int  # idade do cache em segundos


@dataclass(slots=True)
class PersistRunArgs:
    """Argumentos pra persistir uma execucao (cache miss path)."""

    tenant_id: UUID
    agent_name: str
    agent_version: int
    audit_version: str
    inputs_hash: str
    inputs_snapshot: dict[str, Any]
    output_data: dict[str, Any] | None
    output_schema_name: str
    model_used: str
    tokens_input: int
    tokens_output: int
    tokens_cache_read: int
    tokens_cache_creation: int
    cost_brl_estimated: Decimal | None
    duration_ms: int | None
    status: str  # 'success' | 'error' | 'partial'
    error_message: str | None
    triggered_by_user_id: UUID | None


def hash_inputs(audit_version: str, inputs_snapshot: dict[str, Any]) -> str:
    """sha256 canonical de (audit_version + inputs_snapshot).

    Inclusao do `audit_version` garante invalidacao auto quando qualquer
    componente (prompt, persona, expertises, modelo) muda — novo hash, cache
    miss, re-roda.

    `inputs_snapshot` e serializado com `sort_keys=True` pra determinismo
    cross-platform (dict ordering Python 3.7+ e insertion-order, sort_keys
    canonicaliza).
    """
    payload = {
        "audit_version": audit_version,
        "inputs": inputs_snapshot,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def lookup_cached(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_name: str,
    agent_version: int,
    inputs_hash: str,
) -> CachedAnalysis | None:
    """Busca entrada VIVA do cache.

    Retorna None se nao houver match OU se entrada estiver invalidada.
    Quando ha match com status='error', tambem retorna None — erros nao
    devem servir como cache hit (pode ter sido erro transitorio).
    """
    row = (
        await db.execute(
            text(
                "SELECT id, output_data, output_schema_name, model_used, "
                "  tokens_input, tokens_output, tokens_cache_read, "
                "  tokens_cache_creation, cost_brl_estimated, audit_version, "
                "  triggered_at, status "
                "FROM agent_analysis_run "
                "WHERE tenant_id = :tenant_id "
                "  AND agent_name = :agent_name "
                "  AND agent_version = :agent_version "
                "  AND inputs_hash = :inputs_hash "
                "  AND invalidated_at IS NULL "
                "  AND status != 'error' "
                "ORDER BY triggered_at DESC "
                "LIMIT 1"
            ).bindparams(
                tenant_id=tenant_id,
                agent_name=agent_name,
                agent_version=agent_version,
                inputs_hash=inputs_hash,
            )
        )
    ).first()

    if row is None or row.output_data is None:
        return None

    triggered_at: datetime = row.triggered_at
    now = datetime.now(triggered_at.tzinfo) if triggered_at.tzinfo else datetime.now()
    age = int((now - triggered_at).total_seconds())

    return CachedAnalysis(
        id=row.id,
        output_data=row.output_data,
        output_schema_name=row.output_schema_name,
        model_used=row.model_used,
        tokens_input=row.tokens_input,
        tokens_output=row.tokens_output,
        tokens_cache_read=row.tokens_cache_read,
        tokens_cache_creation=row.tokens_cache_creation,
        cost_brl_estimated=(
            Decimal(str(row.cost_brl_estimated))
            if row.cost_brl_estimated is not None
            else None
        ),
        audit_version=row.audit_version,
        triggered_at=triggered_at,
        age_seconds=age,
    )


async def persist_run(db: AsyncSession, args: PersistRunArgs) -> UUID:
    """Insere registro de execucao. Retorna ID gerado.

    Falha silenciosa NAO e aceitavel aqui — auditoria do projeto exige
    persistencia. Exceptions sobem pro caller.

    Conflito (UQ partial em (tenant, agent, version, inputs_hash) WHERE
    invalidated_at IS NULL) acontece se 2 execucoes paralelas fazem cache
    miss e tentam persistir ao mesmo tempo. Tratado via ON CONFLICT:
    invalida a entrada anterior + insere a nova (perdedor da corrida
    sobrescreve, semantica "ultimo vence").
    """
    new_id = uuid4()
    output_data_json = (
        json.dumps(args.output_data, ensure_ascii=False, default=str)
        if args.output_data is not None
        else None
    )
    inputs_snapshot_json = json.dumps(
        args.inputs_snapshot, ensure_ascii=False, default=str
    )

    # ON CONFLICT: se ja existe entrada viva pra mesma chave, marca a antiga
    # como invalidada (race condition resolution) e insere a nova.
    await db.execute(
        text(
            "UPDATE agent_analysis_run "
            "SET invalidated_at = NOW(), invalidated_reason = 'race_condition' "
            "WHERE tenant_id = :tenant_id "
            "  AND agent_name = :agent_name "
            "  AND agent_version = :agent_version "
            "  AND inputs_hash = :inputs_hash "
            "  AND invalidated_at IS NULL"
        ).bindparams(
            tenant_id=args.tenant_id,
            agent_name=args.agent_name,
            agent_version=args.agent_version,
            inputs_hash=args.inputs_hash,
        )
    )

    await db.execute(
        text(
            "INSERT INTO agent_analysis_run "
            "(id, tenant_id, agent_name, agent_version, audit_version, "
            " inputs_hash, inputs_snapshot, output_data, output_schema_name, "
            " model_used, tokens_input, tokens_output, tokens_cache_read, "
            " tokens_cache_creation, cost_brl_estimated, duration_ms, "
            " status, error_message, triggered_by_user_id) "
            "VALUES (:id, :tenant_id, :agent_name, :agent_version, "
            " :audit_version, :inputs_hash, CAST(:inputs_snapshot AS jsonb), "
            " CAST(:output_data AS jsonb), :output_schema_name, :model_used, "
            " :tokens_input, :tokens_output, :tokens_cache_read, "
            " :tokens_cache_creation, :cost_brl_estimated, :duration_ms, "
            " :status, :error_message, :triggered_by_user_id)"
        ).bindparams(
            id=new_id,
            tenant_id=args.tenant_id,
            agent_name=args.agent_name,
            agent_version=args.agent_version,
            audit_version=args.audit_version,
            inputs_hash=args.inputs_hash,
            inputs_snapshot=inputs_snapshot_json,
            output_data=output_data_json,
            output_schema_name=args.output_schema_name,
            model_used=args.model_used,
            tokens_input=args.tokens_input,
            tokens_output=args.tokens_output,
            tokens_cache_read=args.tokens_cache_read,
            tokens_cache_creation=args.tokens_cache_creation,
            cost_brl_estimated=args.cost_brl_estimated,
            duration_ms=args.duration_ms,
            status=args.status,
            error_message=args.error_message,
            triggered_by_user_id=args.triggered_by_user_id,
        )
    )
    await db.commit()
    return new_id


async def invalidate_runs(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_name: str | None = None,
    inputs_snapshot_match: dict[str, Any] | None = None,
    reason: str,
) -> int:
    """Marca runs como invalidadas (soft delete pra cache).

    Filtros AND combinaveis:
      - tenant_id (obrigatorio — escopo de tenant)
      - agent_name (opcional — invalida so 1 agente)
      - inputs_snapshot_match (opcional — match JSONB contains, ex.:
        `{"data_d0": "2026-05-12"}` invalida todas as runs daquela data)

    Retorna numero de linhas invalidadas. ETL pode invocar via:
        await invalidate_runs(db, tenant_id=t, inputs_snapshot_match={"data_d0": d},
                              reason="data_reingested")
    """
    where_parts = ["tenant_id = :tenant_id", "invalidated_at IS NULL"]
    params: dict[str, Any] = {"tenant_id": tenant_id, "reason": reason}

    if agent_name is not None:
        where_parts.append("agent_name = :agent_name")
        params["agent_name"] = agent_name
    if inputs_snapshot_match is not None:
        where_parts.append("inputs_snapshot @> CAST(:snapshot_match AS jsonb)")
        params["snapshot_match"] = json.dumps(
            inputs_snapshot_match, ensure_ascii=False, default=str
        )

    where_sql = " AND ".join(where_parts)
    result = await db.execute(
        text(
            f"UPDATE agent_analysis_run "
            f"SET invalidated_at = NOW(), invalidated_reason = :reason "
            f"WHERE {where_sql}"
        ).bindparams(**params)
    )
    await db.commit()
    return result.rowcount
