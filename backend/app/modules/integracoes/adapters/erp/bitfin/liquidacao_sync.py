"""Sync do desfecho declarado de liquidacao: Bitfin -> wh_liquidacao.

Endpoint proprio (`bitfin.liquidacoes`), independente do `bitfin.full_sync` —
F3 do programa antifraude de auto-liquidacao. Grao = 1 linha por EVENTO DE
DESFECHO (nao por titulo: um titulo pode passar por multiplas recompras).

Fontes (todas declaradas pelo ERP — zero inferencia estatistica aqui):

1. `CobrancaAcoesOcorrencia` 36/37    -> canal `bancaria` (com praca declarada)
2. Titulo Situacao 1/2 sem 36/37      -> canal `baixa_manual` + evidencia
                                         (baixa_confirmada | sem_registro |
                                         sem_ocorrencia)
3. `RecompraItem` (Recompra efetivada)-> canal `recompra` / recompra_efetivada
4. `TituloTransferencia` Motivo=Recompra -> canal `recompra` / transferencia
5. Titulo Situacao 3 sem transferencia / Situacao 9
                                      -> canal `baixa_administrativa` / `perda`

Full refresh idempotente (~106k eventos; upsert por tenant+source_id).
Eventos nao sao deletados no re-sync — desfecho declarado nao "des-acontece";
correcao na fonte reescreve a mesma business key.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import fetch_rows
from app.modules.integracoes.adapters.erp.bitfin.etl import _bulk_upsert, _provenance
from app.modules.integracoes.adapters.erp.bitfin.queries import bitfin
from app.modules.integracoes.adapters.erp.bitfin.version import ADAPTER_VERSION
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.warehouse.liquidacao import Liquidacao

CANAL_BANCARIA = "bancaria"
CANAL_RECOMPRA = "recompra"
CANAL_BAIXA_MANUAL = "baixa_manual"
CANAL_BAIXA_ADMINISTRATIVA = "baixa_administrativa"
CANAL_PERDA = "perda"

EVIDENCIA_BAIXA_CONFIRMADA = "baixa_confirmada"
EVIDENCIA_SEM_REGISTRO = "sem_registro"
EVIDENCIA_SEM_OCORRENCIA = "sem_ocorrencia"
EVIDENCIA_RECOMPRA_EFETIVADA = "recompra_efetivada"
EVIDENCIA_TRANSFERENCIA = "transferencia"

_SITUACAO_PERDA = 9

_BASE_FIELDS = (
    "titulo_id",
    "operacao_id",
    "unidade_administrativa_id",
    "situacao_titulo",
    "valor_titulo",
)


def _base(row: dict, tenant_id: UUID, source_id: str) -> dict:
    """Common columns + provenance for one outcome event row."""
    out = {"tenant_id": tenant_id}
    for field in _BASE_FIELDS:
        out[field] = row.get(field)
    out["data_evento"] = row["data_evento"]
    out.update(_provenance(source_id, row, row.get("data_evento")))
    return out


def _map_bancaria(row: dict, tenant_id: UUID) -> dict:
    return {
        **_base(row, tenant_id, f"liq:{row['titulo_id']}"),
        "canal": CANAL_BANCARIA,
        "evidencia": None,
        "meio_codigo": (row.get("meio_codigo") or "").strip() or None,
        "data_credito": row.get("data_credito"),
        "valor_pago": row.get("valor_pago"),
        "juros": row.get("juros"),
        "agencia_id": row.get("agencia_id"),
        "local_pagamento": row.get("local_pagamento"),
        "pago_fora_praca_sacado": row.get("pago_fora_praca_sacado"),
        "pago_na_praca_cliente": row.get("pago_na_praca_cliente"),
        "pago_na_agencia_cliente": row.get("pago_na_agencia_cliente"),
        "pago_na_agencia_sacado": row.get("pago_na_agencia_sacado"),
        "pago_em_banco_digital": row.get("pago_em_banco_digital"),
        "registrado": row.get("registrado"),
        "carteira_bancaria_id": row.get("carteira_bancaria_id"),
    }


def _classificar_evidencia_manual(row: dict) -> str:
    """S3v3: declared evidence class of a manual write-off.

    baixa_confirmada  o boleto teve ocorrencia 05 (Baixa Confirmada) — foi
                      baixado POR INSTRUCAO e o titulo liquidou por fora
                      (padrao MFL, sinal FORTE). NAO depende do flag
                      `Registrado` atual: apos a baixa o Bitfin flipa
                      Registrado=0 / Baixado=1 (validado em prod — a regra
                      "registrado E 05" zerava a classe inteira).
    sem_registro      titulo nunca entrou em cobranca bancaria (sem
                      ProcedimentoDeCobranca) — deposito direto plausivel
                      (produtos de deposito em conta).
    sem_ocorrencia    entrou em cobranca mas nenhuma ocorrencia de
                      liquidacao/baixa — fraco (cobertura CNAB ou baixa
                      silenciosa).
    """
    if bool(row.get("teve_baixa_confirmada")):
        return EVIDENCIA_BAIXA_CONFIRMADA
    if not bool(row.get("tem_procedimento")):
        return EVIDENCIA_SEM_REGISTRO
    return EVIDENCIA_SEM_OCORRENCIA


def _map_baixa_manual(row: dict, tenant_id: UUID) -> dict:
    return {
        **_base(row, tenant_id, f"man:{row['titulo_id']}"),
        "canal": CANAL_BAIXA_MANUAL,
        "evidencia": _classificar_evidencia_manual(row),
        "valor_pago": row.get("valor_pago"),
        "registrado": row.get("registrado"),
        "carteira_bancaria_id": row.get("carteira_bancaria_id"),
    }


def _map_recompra(row: dict, tenant_id: UUID) -> dict:
    return {
        **_base(row, tenant_id, f"rec:{row['recompra_id']}:{row['titulo_id']}"),
        "canal": CANAL_RECOMPRA,
        "evidencia": EVIDENCIA_RECOMPRA_EFETIVADA,
        "valor_pago": row.get("valor_pago"),
        "juros": row.get("juros"),
        "recompra_id": row.get("recompra_id"),
    }


def _map_transferencia(row: dict, tenant_id: UUID) -> dict:
    return {
        **_base(
            row,
            tenant_id,
            f"tra:{row['titulo_id']}:{row.get('operacao_destino_id')}",
        ),
        "canal": CANAL_RECOMPRA,
        "evidencia": EVIDENCIA_TRANSFERENCIA,
    }


def _map_baixa_admin(row: dict, tenant_id: UUID) -> dict:
    perda = row.get("situacao_titulo") == _SITUACAO_PERDA
    prefix = "per" if perda else "bxa"
    return {
        **_base(row, tenant_id, f"{prefix}:{row['titulo_id']}"),
        "canal": CANAL_PERDA if perda else CANAL_BAIXA_ADMINISTRATIVA,
        "evidencia": None,
        "valor_pago": row.get("valor_pago"),
    }


async def sync_liquidacoes(
    tenant_id: UUID,
    config: BitfinConfig,
    *,
    triggered_by: str = "system:scheduler",
    endpoint_name: str | None = None,
) -> dict[str, Any]:
    """Full refresh dos eventos de desfecho declarado. Summary auditavel."""
    started_at = datetime.now(UTC)
    t0 = time.monotonic()
    db_name = config.database_bitfin

    bancaria_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_LIQUIDACAO_BANCARIA
    )
    manual_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_LIQUIDACAO_SEM_TRILHO
    )
    recompra_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_LIQUIDACAO_RECOMPRA
    )
    transferencia_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_LIQUIDACAO_TRANSFERENCIA
    )
    baixa_admin_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_LIQUIDACAO_BAIXA_ADMIN
    )

    eventos: list[dict] = []
    eventos.extend(_map_bancaria(r, tenant_id) for r in bancaria_rows)
    eventos.extend(_map_baixa_manual(r, tenant_id) for r in manual_rows)
    eventos.extend(_map_recompra(r, tenant_id) for r in recompra_rows)
    eventos.extend(_map_transferencia(r, tenant_id) for r in transferencia_rows)
    eventos.extend(_map_baixa_admin(r, tenant_id) for r in baixa_admin_rows)

    evidencias_manual: dict[str, int] = {}
    for ev in eventos:
        if ev["canal"] == CANAL_BAIXA_MANUAL:
            key = ev["evidencia"] or "?"
            evidencias_manual[key] = evidencias_manual.get(key, 0) + 1

    async with AsyncSessionLocal() as db:
        n_upserted = await _bulk_upsert(
            db, Liquidacao, eventos, ["tenant_id", "source_id"]
        )
        summary: dict[str, Any] = {
            # Chaves consumidas pelo EndpointSyncResult do router de endpoints.
            "ok": True,
            "rows_ingested": n_upserted,
            "started_at": started_at.isoformat(),
            "steps": [{"table": "wh_liquidacao", "rows": n_upserted}],
            "errors": [],
            "adapter_version": ADAPTER_VERSION,
            "elapsed_seconds": round(time.monotonic() - t0, 2),
            "synced_at": datetime.now(UTC).isoformat(),
            "table": "wh_liquidacao",
            "rows": n_upserted,
            "canais": {
                CANAL_BANCARIA: len(bancaria_rows),
                CANAL_BAIXA_MANUAL: len(manual_rows),
                f"{CANAL_RECOMPRA}:{EVIDENCIA_RECOMPRA_EFETIVADA}": len(recompra_rows),
                f"{CANAL_RECOMPRA}:{EVIDENCIA_TRANSFERENCIA}": len(transferencia_rows),
                "baixa_administrativa_ou_perda": len(baixa_admin_rows),
            },
            "evidencias_baixa_manual": evidencias_manual,
        }
        db.add(
            DecisionLog(
                tenant_id=tenant_id,
                decision_type=DecisionType.SYNC,
                inputs_ref={"endpoint": endpoint_name},
                rule_or_model="bitfin_adapter",
                rule_or_model_version=ADAPTER_VERSION,
                endpoint_name=endpoint_name,
                output=summary,
                explanation=(
                    f"liquidacoes declaradas: {n_upserted} eventos "
                    f"({len(bancaria_rows)} bancarias, {len(manual_rows)} baixas "
                    f"manuais, {len(recompra_rows) + len(transferencia_rows)} "
                    f"recompras)"
                ),
                triggered_by=triggered_by,
            )
        )
        await db.commit()

    return summary
