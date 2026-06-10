"""Serasa PJ — service que orquestra consulta + persistencia raw/silver + audit.

Pipeline (espelha o padrao QiTech, adaptado para query sob demanda):

    1. Le `tenant_source_config` (decifrado) para `BUREAU_SERASA_PJ`.
    2. Materializa `SerasaPjConfig`.
    3. Chama `query_pj_analitico(...)` -> `BureauQueryResult` (HTTP a Serasa).
    4. Tx 1 (isolada): INSERT bronze (`wh_serasa_pj_raw_relatorio`).
       Retorna `raw_id`.
    5. Chama `map_pj_analitico(raw_id=..., payload=result.payload)` ->
       `SerasaPjMappedRows`.
    6. Tx 2 (isolada): UPSERT silver — consulta + filhas (socios,
       restricoes, participacoes, enderecos) com
       `pg_insert(...).on_conflict_do_update(index_elements=
       ["tenant_id", "source_id"])`. Idempotente.
    7. Tx 3 (isolada): INSERT decision_log com tipo `SYNC`,
       `rule_or_model="serasa_pj_adapter"`,
       `rule_or_model_version=ADAPTER_VERSION`.

Por que separar em 3 transacoes:
    - Bronze e a fonte de verdade — sobrevive mesmo se mapper quebrar.
      Bug no mapper -> corrige + re-roda mapper sobre raw existente
      (sem novo round-trip pago a Serasa).
    - Silver depende de bronze (FK), entao o INSERT do bronze tem que
      commitar antes do silver tentar gravar.
    - Decision_log e independente — falhar a auditoria nao pode reverter
      a consulta (que ja custou dinheiro real).

Erros: a consulta Serasa pode falhar (HTTP, auth, network); o service
captura e retorna `ok=False` com `errors` populado. Falha no INSERT
bronze tambem cai em `ok=False`, mas o `BureauQueryResult` ja foi
recebido — log do payload bruto vai pro stderr para debug post-mortem.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.bureau.serasa_pj.client import (
    BureauQueryResult,
    query_pj_analitico,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.config import (
    SerasaPjConfig,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.errors import (
    SerasaPjAdapterError,
    SerasaPjHttpError,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.hashing import (
    sha256_of_row,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.mappers.pj_analitico import (
    SerasaPjMappedRows,
    map_pj_analitico,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.version import (
    ADAPTER_VERSION,
)
from app.modules.integracoes.services.serasa_liminar_sentinela import (
    ConsultaAvaliada,
    has_negativos_visiveis,
)
from app.modules.integracoes.services.serasa_liminar_sentinela import (
    process_consulta as process_liminar_consulta,
)
from app.modules.integracoes.services.source_config import (
    get_decrypted_config,
)
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.warehouse.serasa_pj_atraso_medio_mensal import (
    SerasaPjAtrasoMedioMensal,
)
from app.warehouse.serasa_pj_business_reference import (
    SerasaPjBusinessReference,
)
from app.warehouse.serasa_pj_consulta import SerasaPjConsulta
from app.warehouse.serasa_pj_endereco import SerasaPjEndereco
from app.warehouse.serasa_pj_inquiry_anterior import SerasaPjInquiryAnterior
from app.warehouse.serasa_pj_inquiry_mensal import SerasaPjInquiryMensal
from app.warehouse.serasa_pj_pagamento_bucket import SerasaPjPagamentoBucket
from app.warehouse.serasa_pj_pagamento_evolucao_mensal import (
    SerasaPjPagamentoEvolucaoMensal,
)
from app.warehouse.serasa_pj_participacao import SerasaPjParticipacao
from app.warehouse.serasa_pj_payment_comparative import (
    SerasaPjPaymentComparative,
)
from app.warehouse.serasa_pj_predecessor import SerasaPjPredecessor
from app.warehouse.serasa_pj_raw_relatorio import SerasaPjRawRelatorio
from app.warehouse.serasa_pj_restricao import SerasaPjRestricao
from app.warehouse.serasa_pj_restricao_summary import SerasaPjRestricaoSummary
from app.warehouse.serasa_pj_socio import SerasaPjSocio

logger = logging.getLogger("gr.integracoes.serasa_pj")

_RULE_NAME = "serasa_pj_adapter"


async def remap_from_raw(
    *,
    raw_id: UUID,
) -> dict[str, Any]:
    """Re-mapeia silver a partir de uma linha bronze ja persistida.

    Usado durante iteracao do mapper: quando refatoramos a logica de
    parse, podemos re-rodar `map_pj_analitico` sobre o payload imutavel
    em `wh_serasa_pj_raw_relatorio` sem pagar consulta nova.

    UPSERT idempotente em `wh_serasa_pj_consulta` (e filhas via CASCADE)
    pelo source_id determinista — re-mapear substitui linhas existentes.

    Args:
        raw_id: PK da linha em `wh_serasa_pj_raw_relatorio`.

    Returns:
        Dict com formato similar ao `execute_pj_query`, mas sem campos
        de chamada HTTP (latency_ms, etc).
    """
    summary: dict[str, Any] = {
        "ok": False,
        "raw_id": str(raw_id),
        "consulta_id": None,
        "cnpj": None,
        "requested_report": None,
        "actual_report_returned": None,
        "reciprocity_downgrade": None,
        "counts": {
            "socios": 0,
            "restricoes": 0,
            "restricao_summaries": 0,
            "participacoes": 0,
            "enderecos": 0,
            "pagamento_buckets": 0,
            "consultas_listadas_detalhe": 0,
            "predecessores": 0,
            "consultas_total_12m": 0,
            "business_references": 0,
            "pagamento_evolucao_mensal": 0,
            "atraso_medio_mensal": 0,
            "payment_comparatives": 0,
        },
        "adapter_version": ADAPTER_VERSION,
        "errors": [],
        "remap": True,
    }

    # Carrega raw.
    async with AsyncSessionLocal() as db:
        raw = await db.get(SerasaPjRawRelatorio, raw_id)
    if raw is None:
        summary["errors"].append(f"raw_id={raw_id} nao encontrado")
        return summary

    summary["cnpj"] = raw.cnpj
    summary["requested_report"] = raw.requested_report
    summary["actual_report_returned"] = raw.actual_report_returned
    summary["reciprocity_downgrade"] = (
        raw.requested_report != raw.actual_report_returned
    )

    # Re-mapeia.
    try:
        rows: SerasaPjMappedRows = map_pj_analitico(
            payload=raw.payload,
            tenant_id=raw.tenant_id,
            raw_id=raw.id,
            cnpj=raw.cnpj,
            consulted_at=raw.fetched_at,
            requested_report=raw.requested_report,
            actual_report_returned=raw.actual_report_returned,
        )
    except Exception as e:
        summary["errors"].append(f"map: {type(e).__name__}: {e}")
        return summary

    # UPSERT silver (mesma transacao).
    try:
        async with AsyncSessionLocal() as db:
            await _upsert_silver(db, rows)
            await db.commit()
        summary["consulta_id"] = str(rows.consulta["id"])
        summary["counts"] = {
            "socios": len(rows.socios),
            "restricoes": len(rows.restricoes),
            "restricao_summaries": len(rows.restricao_summaries),
            "participacoes": len(rows.participacoes),
            "enderecos": len(rows.enderecos),
            "pagamento_buckets": len(rows.pagamento_buckets),
            "consultas_listadas_detalhe": len(rows.inquiries_anteriores),
            "predecessores": len(rows.predecessores),
            "consultas_total_12m": _sum_occurrences(rows.inquiries_mensais),
            "business_references": len(rows.business_references),
            "pagamento_evolucao_mensal": len(
                rows.pagamento_evolucao_mensal
            ),
            "atraso_medio_mensal": len(rows.atraso_medio_mensal),
            "payment_comparatives": len(rows.payment_comparatives),
        }
        summary["ok"] = True
    except Exception as e:
        summary["errors"].append(f"silver: {type(e).__name__}: {e}")

    return summary


async def execute_pj_query(
    *,
    tenant_id: UUID,
    cnpj: str,
    triggered_by: str,
    environment: Environment = Environment.PRODUCTION,
    report_type: str | None = None,
    cost_center: str | None = None,
    raise_on_downgrade: bool = False,
) -> dict[str, Any]:
    """Consulta Serasa PJ e persiste raw + silver + audit em transacoes isoladas.

    Args:
        tenant_id: dono da credencial e da consulta.
        cnpj: 14 digitos (com ou sem mascara — normalizado pelo client).
        triggered_by: rastreio livre do que disparou a consulta — ex.:
            `dossie:<id>`, `workflow_run:<id>`, `user:<id>`,
            `system:scheduler`. Vai pra raw.triggered_by + decision_log.
        environment: sandbox/UAT (`SANDBOX`) ou producao (`PRODUCTION`).
        report_type: override do tipo de relatorio. Default vem do config
            (`RELATORIO_AVANCADO_PJ_ANALITICO`).
        cost_center: rotulo curto pra X-Cost-Center (truncado a 12 chars
            pelo client). Util quando dossie tem ID curto.
        raise_on_downgrade: se True, levanta excecao quando a Serasa
            devolver relatorio diferente do solicitado (reciprocidade
            quebrada). Default False — caller decide o que fazer.

    Returns:
        Dict com:
            ok (bool), raw_id (UUID|None), consulta_id (UUID|None),
            cnpj (str), requested_report, actual_report_returned,
            reciprocity_downgrade (bool), counts (dict), latency_ms,
            adapter_version, errors (list[str]).
    """
    summary: dict[str, Any] = {
        "ok": False,
        "raw_id": None,
        "consulta_id": None,
        "cnpj": cnpj,
        "requested_report": None,
        "actual_report_returned": None,
        "reciprocity_downgrade": None,
        "counts": {
            "socios": 0,
            "restricoes": 0,
            "restricao_summaries": 0,
            "participacoes": 0,
            "enderecos": 0,
            "pagamento_buckets": 0,
            "consultas_listadas_detalhe": 0,
            "predecessores": 0,
            "consultas_total_12m": 0,
            "business_references": 0,
            "pagamento_evolucao_mensal": 0,
            "atraso_medio_mensal": 0,
            "payment_comparatives": 0,
        },
        "latency_ms": None,
        "adapter_version": ADAPTER_VERSION,
        "errors": [],
        "triggered_by": triggered_by,
        "environment": environment.value,
    }

    # ─── 0. Carregar config ────────────────────────────────────────────────
    try:
        async with AsyncSessionLocal() as db:
            config_dict = await get_decrypted_config(
                db,
                tenant_id,
                SourceType.BUREAU_SERASA_PJ,
                environment=environment,
            )
    except Exception as e:
        summary["errors"].append(
            f"config: {type(e).__name__}: {e}"
        )
        await _audit(
            tenant_id=tenant_id,
            triggered_by=triggered_by,
            summary=summary,
        )
        return summary

    if config_dict is None:
        summary["errors"].append(
            f"sem tenant_source_config para BUREAU_SERASA_PJ/"
            f"{environment.value} no tenant {tenant_id}"
        )
        await _audit(
            tenant_id=tenant_id,
            triggered_by=triggered_by,
            summary=summary,
        )
        return summary

    config = SerasaPjConfig.from_dict(config_dict)

    # ─── 1. Consulta Serasa (HTTP) ─────────────────────────────────────────
    try:
        result: BureauQueryResult = await query_pj_analitico(
            tenant_id=tenant_id,
            environment=environment,
            config=config,
            cnpj=cnpj,
            report_type=report_type,
            cost_center=cost_center,
            raise_on_downgrade=raise_on_downgrade,
        )
    except SerasaPjAdapterError as e:
        summary["errors"].append(f"query: {type(e).__name__}: {e}")
        # Pra HTTP errors, anexa status_code + body retornado pela Serasa
        # (truncado em 1000 chars no client). Util pra debug de 4xx/5xx
        # quando a mensagem da Serasa explica o problema (CNPJ invalido,
        # endpoint sem permissao, scope insuficiente).
        if isinstance(e, SerasaPjHttpError):
            if e.status_code is not None:
                summary["errors"].append(
                    f"query.status_code: {e.status_code}"
                )
            if e.detail:
                summary["errors"].append(f"query.body: {e.detail}")
        await _audit(
            tenant_id=tenant_id,
            triggered_by=triggered_by,
            summary=summary,
        )
        return summary

    summary["requested_report"] = result.requested_report
    summary["actual_report_returned"] = result.actual_report_returned
    summary["reciprocity_downgrade"] = (
        result.requested_report != result.actual_report_returned
    )
    summary["latency_ms"] = result.latency_ms

    # ─── 2. Tx 1: INSERT bronze ────────────────────────────────────────────
    raw_id = uuid4()
    try:
        async with AsyncSessionLocal() as db:
            await _insert_raw(
                db,
                raw_id=raw_id,
                tenant_id=tenant_id,
                cnpj=result.payload.get("documentId")
                or result.payload.get("DocumentId")
                or _strip_non_digits(cnpj),
                result=result,
                environment=environment,
                triggered_by=triggered_by,
            )
            await db.commit()
        summary["raw_id"] = raw_id
    except Exception as e:
        # Bronze nao gravou — perdemos o payload em RAM. Log no stderr
        # pra investigacao (a Serasa ja foi cobrada, e o dado importa).
        logger.exception(
            "serasa_pj.execute: falha ao gravar raw — payload em log",
        )
        summary["errors"].append(f"raw: {type(e).__name__}: {e}")
        await _audit(
            tenant_id=tenant_id,
            triggered_by=triggered_by,
            summary=summary,
        )
        return summary

    # ─── 3. Map ────────────────────────────────────────────────────────────
    try:
        rows: SerasaPjMappedRows = map_pj_analitico(
            payload=result.payload,
            tenant_id=tenant_id,
            raw_id=raw_id,
            cnpj=cnpj,
            consulted_at=_consulted_at_from_raw(),
            requested_report=result.requested_report,
            actual_report_returned=result.actual_report_returned,
        )
    except Exception as e:
        summary["errors"].append(f"map: {type(e).__name__}: {e}")
        await _audit(
            tenant_id=tenant_id,
            triggered_by=triggered_by,
            summary=summary,
        )
        return summary

    # ─── 4. Tx 2: UPSERT silver ────────────────────────────────────────────
    try:
        async with AsyncSessionLocal() as db:
            await _upsert_silver(db, rows)
            # Sentinela de liminar (mesma tx do silver): maquina de
            # estados + transicoes/alertas no decision_log.
            await process_liminar_consulta(
                db,
                ConsultaAvaliada(
                    tenant_id=tenant_id,
                    cnpj=rows.consulta["cnpj"],
                    raw_id=raw_id,
                    consulted_at=rows.consulta["consulted_at"],
                    negative_summary_message=rows.consulta[
                        "negative_summary_message"
                    ],
                    negativos_visiveis=has_negativos_visiveis(rows.consulta),
                    triggered_by=triggered_by,
                ),
            )
            await db.commit()
        summary["consulta_id"] = rows.consulta["id"]
        summary["counts"] = {
            "socios": len(rows.socios),
            "restricoes": len(rows.restricoes),
            "restricao_summaries": len(rows.restricao_summaries),
            "participacoes": len(rows.participacoes),
            "enderecos": len(rows.enderecos),
            "pagamento_buckets": len(rows.pagamento_buckets),
            "consultas_listadas_detalhe": len(rows.inquiries_anteriores),
            "predecessores": len(rows.predecessores),
            "consultas_total_12m": _sum_occurrences(rows.inquiries_mensais),
            "business_references": len(rows.business_references),
            "pagamento_evolucao_mensal": len(
                rows.pagamento_evolucao_mensal
            ),
            "atraso_medio_mensal": len(rows.atraso_medio_mensal),
            "payment_comparatives": len(rows.payment_comparatives),
        }
    except Exception as e:
        summary["errors"].append(f"silver: {type(e).__name__}: {e}")
        await _audit(
            tenant_id=tenant_id,
            triggered_by=triggered_by,
            summary=summary,
        )
        return summary

    summary["ok"] = True
    await _audit(
        tenant_id=tenant_id,
        triggered_by=triggered_by,
        summary=summary,
    )
    return summary


# ─── Persistencia ──────────────────────────────────────────────────────────


async def _insert_raw(
    db: AsyncSession,
    *,
    raw_id: UUID,
    tenant_id: UUID,
    cnpj: Any,
    result: BureauQueryResult,
    environment: Environment,
    triggered_by: str,
) -> None:
    """INSERT na tabela bronze. Sem upsert — toda consulta gera linha nova."""
    cnpj_clean = _strip_non_digits(cnpj)
    db.add(
        SerasaPjRawRelatorio(
            id=raw_id,
            tenant_id=tenant_id,
            cnpj=cnpj_clean,
            requested_report=result.requested_report,
            actual_report_returned=result.actual_report_returned,
            environment=environment,
            status_code=result.status_code,
            cost_center=result.cost_center,
            triggered_by=triggered_by,
            payload=result.payload,
            payload_sha256=sha256_of_row(result.payload),
            latency_ms=result.latency_ms,
            fetched_by_version=result.adapter_version,
        )
    )


async def _upsert_silver(
    db: AsyncSession, rows: SerasaPjMappedRows
) -> None:
    """UPSERT idempotente do header + 4 tabelas filhas em UMA transacao.

    Header (consulta) vai primeiro. Em remap (segundo mapeamento sobre
    o mesmo raw), o UPSERT preserva o `id` da linha existente — mesmo
    que o mapper tenha gerado UUID novo. Capturamos o `id` real via
    RETURNING e propagamos para todas as filhas, evitando FK violation.

    Ordem:
        1. UPSERT consulta + RETURNING id
        2. Se remap detectou (real_id != id gerado pelo mapper),
           reescreve `consulta_id` em todas as filhas
        3. UPSERT cada filha
    """
    real_consulta_id = await _upsert_consulta_returning_id(
        db, rows.consulta, ["tenant_id", "source_id"]
    )

    if real_consulta_id != rows.consulta["id"]:
        # Remap: linha existente preservou o id antigo. Realinha filhas.
        rows.consulta["id"] = real_consulta_id
        for child_list in (
            rows.socios,
            rows.restricoes,
            rows.restricao_summaries,
            rows.participacoes,
            rows.enderecos,
            rows.pagamento_buckets,
            rows.inquiries_anteriores,
            rows.predecessores,
            rows.inquiries_mensais,
            rows.business_references,
            rows.pagamento_evolucao_mensal,
            rows.atraso_medio_mensal,
            rows.payment_comparatives,
        ):
            for r in child_list:
                r["consulta_id"] = real_consulta_id

    if rows.socios:
        await _upsert_many(
            db, SerasaPjSocio, rows.socios, ["tenant_id", "source_id"]
        )
    if rows.restricoes:
        await _upsert_many(
            db,
            SerasaPjRestricao,
            rows.restricoes,
            ["tenant_id", "source_id"],
        )
    if rows.restricao_summaries:
        await _upsert_many(
            db,
            SerasaPjRestricaoSummary,
            rows.restricao_summaries,
            ["tenant_id", "source_id"],
        )
    if rows.participacoes:
        await _upsert_many(
            db,
            SerasaPjParticipacao,
            rows.participacoes,
            ["tenant_id", "source_id"],
        )
    if rows.enderecos:
        await _upsert_many(
            db,
            SerasaPjEndereco,
            rows.enderecos,
            ["tenant_id", "source_id"],
        )
    if rows.pagamento_buckets:
        await _upsert_many(
            db,
            SerasaPjPagamentoBucket,
            rows.pagamento_buckets,
            ["tenant_id", "source_id"],
        )
    if rows.inquiries_anteriores:
        await _upsert_many(
            db,
            SerasaPjInquiryAnterior,
            rows.inquiries_anteriores,
            ["tenant_id", "source_id"],
        )
    if rows.predecessores:
        await _upsert_many(
            db,
            SerasaPjPredecessor,
            rows.predecessores,
            ["tenant_id", "source_id"],
        )
    if rows.inquiries_mensais:
        await _upsert_many(
            db,
            SerasaPjInquiryMensal,
            rows.inquiries_mensais,
            ["tenant_id", "source_id"],
        )
    if rows.business_references:
        await _upsert_many(
            db,
            SerasaPjBusinessReference,
            rows.business_references,
            ["tenant_id", "source_id"],
        )
    if rows.pagamento_evolucao_mensal:
        await _upsert_many(
            db,
            SerasaPjPagamentoEvolucaoMensal,
            rows.pagamento_evolucao_mensal,
            ["tenant_id", "source_id"],
        )
    if rows.atraso_medio_mensal:
        await _upsert_many(
            db,
            SerasaPjAtrasoMedioMensal,
            rows.atraso_medio_mensal,
            ["tenant_id", "source_id"],
        )
    if rows.payment_comparatives:
        await _upsert_many(
            db,
            SerasaPjPaymentComparative,
            rows.payment_comparatives,
            ["tenant_id", "source_id"],
        )


async def persist_serasa_pj_silver(
    db: AsyncSession, rows: SerasaPjMappedRows
) -> None:
    """UPSERT silver reutilizavel (header + filhas) — wrapper publico de
    `_upsert_silver`. Usado pelo relay Bitfin (`adapters/erp/bitfin/
    serasa_relay.py`) pra gravar no mesmo wh_serasa_pj_* sem duplicar a logica.
    O caller commita.
    """
    await _upsert_silver(db, rows)


async def _upsert_consulta_returning_id(
    db: AsyncSession,
    row: dict[str, Any],
    conflict_columns: list[str],
) -> UUID:
    """UPSERT na consulta retornando o `id` real persistido.

    No INSERT puro: retorna o `id` que veio no row.
    No ON CONFLICT UPDATE: retorna o `id` da linha existente (preservado
    porque `id` esta fora dos `update_cols`).

    Indispensavel para remap onde mapper gera UUID novo a cada chamada
    mas o banco preserva o id da consulta original.
    """
    table = SerasaPjConsulta.__table__
    table_col_names = {c.name for c in table.columns}
    norm = {k: v for k, v in row.items() if k in table_col_names}
    stmt = pg_insert(table).values(norm)
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in table.columns
        if c.name not in {"id", "ingested_at", *conflict_columns}
        and c.name in norm
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_columns, set_=update_cols
    ).returning(table.c.id)
    result = await db.execute(stmt)
    return result.scalar_one()


async def _upsert_one(
    db: AsyncSession,
    model: Any,
    row: dict[str, Any],
    conflict_columns: list[str],
) -> None:
    """UPSERT de uma unica row.

    Colunas ausentes em `row` sao omitidas do INSERT — deixa o
    `server_default` (gen_random_uuid, now()) preencher.
    """
    table = model.__table__
    table_col_names = {c.name for c in table.columns}
    norm = {k: v for k, v in row.items() if k in table_col_names}
    stmt = pg_insert(table).values(norm)
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in table.columns
        if c.name not in {"id", "ingested_at", *conflict_columns}
        and c.name in norm
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_columns, set_=update_cols
    )
    await db.execute(stmt)


async def _upsert_many(
    db: AsyncSession,
    model: Any,
    rows: list[dict[str, Any]],
    conflict_columns: list[str],
) -> None:
    """UPSERT em batch — colunas ausentes nas rows sao omitidas (server_default).

    Para batch INSERT VALUES o postgres exige rows homogeneas: usamos
    a uniao das chaves presentes em qualquer row, e preenchemos None
    nas demais. Colunas que NENHUMA row trouxe ficam fora do INSERT.
    """
    if not rows:
        return
    table = model.__table__
    table_col_names = {c.name for c in table.columns}

    # Uniao de chaves presentes nas rows, intersectada com a tabela.
    used_cols: list[str] = sorted(
        {k for r in rows for k in r if k in table_col_names}
    )

    normalized = [{col: r.get(col) for col in used_cols} for r in rows]
    # Dedup pela conflict key dentro do batch (ON CONFLICT falha se houver
    # duplicata no mesmo INSERT).
    seen: dict[tuple, dict] = {}
    for r in normalized:
        seen[tuple(r[c] for c in conflict_columns)] = r
    deduped = list(seen.values())

    stmt = pg_insert(table).values(deduped)
    update_cols = {
        col: stmt.excluded[col]
        for col in used_cols
        if col not in {"id", "ingested_at", *conflict_columns}
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_columns, set_=update_cols
    )
    await db.execute(stmt)


# ─── Auditoria ─────────────────────────────────────────────────────────────


async def _audit(
    *,
    tenant_id: UUID,
    triggered_by: str,
    summary: dict[str, Any],
) -> None:
    """Grava entrada em decision_log. Falha aqui nao bloqueia retorno."""
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                DecisionLog(
                    tenant_id=tenant_id,
                    decision_type=DecisionType.SYNC,
                    rule_or_model=_RULE_NAME,
                    rule_or_model_version=ADAPTER_VERSION,
                    triggered_by=triggered_by,
                    inputs_ref={
                        "cnpj": summary.get("cnpj"),
                        "environment": summary.get("environment"),
                        "report_type": summary.get("requested_report"),
                    },
                    output={
                        "ok": summary["ok"],
                        "raw_id": str(summary["raw_id"])
                        if summary["raw_id"]
                        else None,
                        "consulta_id": str(summary["consulta_id"])
                        if summary["consulta_id"]
                        else None,
                        "actual_report_returned": summary.get(
                            "actual_report_returned"
                        ),
                        "reciprocity_downgrade": summary.get(
                            "reciprocity_downgrade"
                        ),
                        "counts": summary["counts"],
                        "latency_ms": summary["latency_ms"],
                        "errors": summary["errors"],
                    },
                    explanation=(
                        "Serasa PJ Business Information Report — "
                        f"CNPJ {summary.get('cnpj')}"
                    ),
                )
            )
            await db.commit()
    except Exception:
        # Audit best-effort — log mas nao propaga.
        logger.exception(
            "serasa_pj._audit: falha ao gravar decision_log "
            "(consulta ja persistida; auditoria perdida)"
        )


# ─── Helpers ───────────────────────────────────────────────────────────────


def _strip_non_digits(value: Any) -> str:
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def _sum_occurrences(rows: list[dict[str, Any]]) -> int:
    """Soma `occurrences` de linhas mensais de inquiry — total real de consultas.

    `len(rows)` aqui sempre devolve ~13 (1 bucket por mes do historico Serasa,
    incluindo meses sem consulta), entao len NAO conta consultas. So esta soma e
    o numero real.
    """
    return sum(int(r.get("occurrences") or 0) for r in rows)


def _consulted_at_from_raw():
    """`consulted_at` no silver = `now()` no momento do mapper.

    Em transacao isolada do INSERT bronze, os timestamps acabam diferindo
    em milissegundos. Aceitavel — a fonte da verdade pra `quando consulta
    foi feita` e o `fetched_at` da bronze (server_default now()), e o
    silver usa o tempo da execucao do mapper (proximo o suficiente).
    """
    from datetime import UTC, datetime

    return datetime.now(UTC)
