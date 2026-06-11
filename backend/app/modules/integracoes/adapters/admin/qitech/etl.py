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

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.integracoes.adapters.admin.qitech.completeness import (
    assess_completeness,
)
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.admin.qitech.critical_fields import (
    get_critical_fields,
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
from app.modules.integracoes.services.qitech_ua_classe import get_expected_classes
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.shared.audit_log.helpers import log_silver_replacement
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.dia_util_qitech import DiaUtilQitech
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


async def _resolve_ua_nome(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
) -> str | None:
    """Resolve o nome da UA via SELECT por PK (usado pelo completeness).

    Retorna None quando `unidade_administrativa_id` e None (rows legacy
    pre-Phase F) ou se a UA nao for encontrada. Sem UA o inspector ainda
    classifica via perfil default (`complete` se payload nao vazio).
    """
    if unidade_administrativa_id is None:
        return None
    stmt = select(UnidadeAdministrativa.nome).where(
        UnidadeAdministrativa.id == unidade_administrativa_id,
        UnidadeAdministrativa.tenant_id == tenant_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _upsert_raw(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    tipo_de_mercado: str,
    data_posicao: date,
    payload: dict[str, Any],
    http_status: int,
    unidade_administrativa_id: UUID | None = None,
) -> tuple[UUID, str | None]:
    """Grava 1 linha em `wh_qitech_raw_relatorio` (idempotente por UQ).

    Retorna `(raw_id, completeness)` — `raw_id` eh o UUID da row raw
    (mesma id em re-upsert porque UQ bate). `completeness` eh o resultado
    de `assess_completeness` (`complete | partial | empty` ou None).

    O par eh consumido pelo `_replace_canonical_partition` (Fase 1.3,
    refactor "espelho fiel" 2026-05-20): `raw_id` vira a partition key
    do DELETE+INSERT no silver, e `completeness` decide se o write eh
    strict (so substitui em complete).

    Re-roda o mesmo dia substitui payload + atualiza `fetched_at` e
    `payload_sha256` — preserva historico apenas se conteudo mudou (sha bate).

    Multi-UA (Phase F): UQ inclui `unidade_administrativa_id`, entao 2 UAs
    do mesmo tenant podem fetchar o mesmo (tipo, data) sem colidir.
    """
    ua_nome = await _resolve_ua_nome(
        db,
        tenant_id=tenant_id,
        unidade_administrativa_id=unidade_administrativa_id,
    )
    # Catalogo de classes (qitech_ua_classe): so faz sentido em http 200
    # (4xx/5xx ja resolve `empty` antes de olhar o payload). Set vazio =
    # sem catalogo -> assessor cai na heuristica legada.
    expected_classes: set[str] = set()
    if http_status == 200:
        expected_classes = await get_expected_classes(
            db,
            tenant_id=tenant_id,
            unidade_administrativa_id=unidade_administrativa_id,
            tipo_de_mercado=tipo_de_mercado,
            on_date=data_posicao,
        )
    completeness = assess_completeness(
        tipo_de_mercado=tipo_de_mercado,
        payload=payload,
        http_status=http_status,
        ua_nome=ua_nome,
        expected_classes=expected_classes,
    )
    row = {
        "tenant_id": tenant_id,
        "tipo_de_mercado": tipo_de_mercado,
        "data_posicao": data_posicao,
        "unidade_administrativa_id": unidade_administrativa_id,
        "payload": payload,
        "http_status": http_status,
        "payload_sha256": sha256_of_row(payload),
        "fetched_at": datetime.now(UTC),
        "fetched_by_version": ADAPTER_VERSION,
        "completeness": completeness,
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
            "completeness": stmt.excluded.completeness,
        },
    ).returning(QiTechRawRelatorio.__table__.c.id)
    raw_id = (await db.execute(stmt)).scalar_one()
    return raw_id, completeness


# ---- Persistencia canonica ----------------------------------------------


async def _bulk_upsert_canonical(
    db: AsyncSession,
    model,
    rows: list[dict],
    conflict_columns: list[str],
    *,
    unidade_administrativa_id: UUID | None = None,
) -> int:
    """Upsert idempotente em chunks (replica do padrao Bitfin).

    Resolve 3 problemas conhecidos do `pg_insert().values(rows)`:
    1. **Limite de params**: n_rows * n_cols < 32767 (limite asyncpg).
    2. **Normalizacao de chaves**: bulk VALUES exige rows homogeneas; rows do
       mapper podem omitir chaves quando valor e None — preenchemos None.
    3. **Deduplicacao**: ON CONFLICT falha se o mesmo batch tem duas linhas
       com mesma unique key. Mantem a ultima ocorrencia.

    Multi-UA (Phase F): se `unidade_administrativa_id` for fornecido, e
    injetado em todas as rows que nao trouxerem o campo do mapper. Mappers
    podem sobrescrever, mas em geral o caller passa UA do contexto e os
    mappers nao se preocupam.
    """
    if not rows:
        return 0

    all_columns = [c.name for c in model.__table__.columns if c.name != "id"]
    has_ua_column = "unidade_administrativa_id" in all_columns

    normalized: list[dict] = []
    for row in rows:
        norm = {col: row.get(col) for col in all_columns}
        if (
            has_ua_column
            and unidade_administrativa_id is not None
            and norm.get("unidade_administrativa_id") is None
        ):
            norm["unidade_administrativa_id"] = unidade_administrativa_id
        normalized.append(norm)

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


# ---- Replace-by-partition (Fase 1.3, "espelho fiel QiTech") ------------


async def _replace_canonical_partition(
    db: AsyncSession,
    model: Any,
    rows: list[dict[str, Any]],
    conflict_columns: list[str],
    *,
    raw_id: UUID,
    completeness: str | None,
    tenant_id: UUID,
    endpoint_name: str,
    data_referencia: date,
    critical_fields_for_audit: list[str] | None = None,
    unidade_administrativa_id: UUID | None = None,
    triggered_by: str = "qitech_adapter",
) -> dict[str, Any]:
    """Replace-by-partition strict no scope `raw_id` -- "espelho fiel QiTech".

    Substitui `_bulk_upsert_canonical` na Fase 1.3. Politica do refactor
    "espelho fiel" (2026-05-20):

        completeness == 'complete'  -> UPSERT + DELETE de orfas na partition
        completeness != 'complete'  -> no-op no silver (raw ja foi gravado
                                       fora; silver preserva o que tinha)

    A partition do silver eh `WHERE raw_id = :raw_id`. Re-fetch do mesmo
    (tenant, endpoint, data, ua) gera o mesmo raw_id (UQ bate -> UPSERT
    in-place na raw), entao todas as silver rows projetadas daquele raw
    sao re-avaliadas no contexto do payload novo:

      1. Rows com mesma business key -> UPDATE (sobrescreve)
      2. Rows novas -> INSERT (com raw_id=raw_id)
      3. Rows que SUMIRAM do payload novo -> DELETE (orfas) + audit

    Auditoria das orfas (CLAUDE.md secao 14, decisao 2026-05-20 audit nivel
    (ii) — "keys + campos criticos"): cada DELETE em massa grava 1 entry
    `DATA_CORRECTION` no `decision_log` com:
      - inputs_ref: {raw_id, endpoint, data, ua}
      - output: {removed_count, business_keys, snapshot_critical_fields}
      - explanation: texto em pt-BR

    `critical_fields_for_audit` define quais colunas da silver vao no
    snapshot. Tipicamente sao os campos de valor/status que importam pra
    reconstrucao forense ("quanto valia o titulo que sumiu"). Definido
    por mapper na Fase 1.4.

    Returns dict com:
      - mode: 'replace' | 'noop'
      - reason: motivo do mode
      - inserted: int (rows inseridas/atualizadas)
      - orphans_count: int
    """
    if completeness != "complete":
        # Politica strict: payload precisa estar complete pra disparar
        # qualquer mutacao no silver. Outras states (partial, empty, None)
        # significam que a fonte esta degradada -- preservamos o silver.
        return {
            "mode": "noop",
            "reason": f"completeness={completeness!r}",
            "inserted": 0,
            "orphans_count": 0,
        }

    critical_fields_for_audit = critical_fields_for_audit or []
    table_name = model.__tablename__
    all_columns = [c.name for c in model.__table__.columns if c.name != "id"]
    has_ua_column = "unidade_administrativa_id" in all_columns

    # Snapshot columns pro audit -- filtra apenas as que existem no model.
    snapshot_col_names = ["id", *conflict_columns, *critical_fields_for_audit]
    snapshot_col_names = list(dict.fromkeys(snapshot_col_names))  # dedup mantendo ordem
    snapshot_columns = [
        model.__table__.c[c] for c in snapshot_col_names if c in model.__table__.c
    ]

    if not rows:
        # Payload complete vazio: tudo no partition sumiu da fonte.
        # DELETE all + audit.
        result = await db.execute(
            delete(model.__table__)
            .where(model.__table__.c.raw_id == raw_id)
            .returning(*snapshot_columns)
        )
        orphans = [dict(r) for r in result.mappings().all()]
        if orphans:
            await log_silver_replacement(
                db,
                tenant_id=tenant_id,
                adapter_name="qitech_adapter",
                adapter_version=ADAPTER_VERSION,
                endpoint_name=endpoint_name,
                table_name=table_name,
                raw_id=raw_id,
                data_referencia=data_referencia,
                unidade_administrativa_id=unidade_administrativa_id,
                orphan_rows=orphans,
                conflict_columns=conflict_columns,
                triggered_by=triggered_by,
                reason="empty_complete_payload",
            )
        return {
            "mode": "replace",
            "reason": "empty_complete_payload",
            "inserted": 0,
            "orphans_count": len(orphans),
        }

    # Normaliza rows: injeta UA + raw_id sempre. raw_id eh injetado em
    # TODAS as rows -- distinguir de _bulk_upsert_canonical que nao tinha
    # essa coluna.
    normalized: list[dict[str, Any]] = []
    for row in rows:
        norm = {col: row.get(col) for col in all_columns}
        if (
            has_ua_column
            and unidade_administrativa_id is not None
            and norm.get("unidade_administrativa_id") is None
        ):
            norm["unidade_administrativa_id"] = unidade_administrativa_id
        norm["raw_id"] = raw_id
        normalized.append(norm)

    # Dedup defensivo por business key (mesma logica do _bulk).
    seen: dict[tuple, dict[str, Any]] = {}
    for r in normalized:
        seen[tuple(r[c] for c in conflict_columns)] = r
    deduped = list(seen.values())

    # UPSERT em chunks. RETURNING id acumula ids inseridos/atualizados
    # pra construir o NOT IN do DELETE depois.
    chunk_size = max(1, min(CHUNK_SIZE, MAX_PG_PARAMS // len(all_columns)))
    update_cols_names = [
        c.name
        for c in model.__table__.columns
        if c.name not in {"id", *conflict_columns, "ingested_at"}
    ]

    inserted_ids: list[Any] = []
    for chunk in _chunked(deduped, chunk_size):
        stmt = pg_insert(model.__table__).values(chunk)
        update_set = {name: stmt.excluded[name] for name in update_cols_names}
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_columns, set_=update_set
        ).returning(model.__table__.c.id)
        res = await db.execute(stmt)
        inserted_ids.extend(res.scalars().all())

    # DELETE de orfas: rows com mesmo raw_id que NAO foram tocadas pelo INSERT.
    delete_stmt = (
        delete(model.__table__)
        .where(model.__table__.c.raw_id == raw_id)
        .where(model.__table__.c.id.not_in(inserted_ids))
        .returning(*snapshot_columns)
    )
    result = await db.execute(delete_stmt)
    orphans = [dict(r) for r in result.mappings().all()]

    if orphans:
        await log_silver_replacement(
            db,
            tenant_id=tenant_id,
            adapter_name="qitech_adapter",
            adapter_version=ADAPTER_VERSION,
            endpoint_name=endpoint_name,
            table_name=table_name,
            raw_id=raw_id,
            data_referencia=data_referencia,
            unidade_administrativa_id=unidade_administrativa_id,
            orphan_rows=orphans,
            conflict_columns=conflict_columns,
            triggered_by=triggered_by,
            reason="upsert_with_orphan_delete",
        )

    return {
        "mode": "replace",
        "reason": "upsert_with_orphan_delete",
        "inserted": len(inserted_ids),
        "orphans_count": len(orphans),
    }


# ---- 4xx-as-row helper -------------------------------------------------


async def _persist_error_raw(
    *,
    tenant_id: UUID,
    tipo_de_mercado: str,
    data_posicao: date,
    unidade_administrativa_id: UUID | None,
    http_status: int,
    error_detail: str,
    step: dict[str, Any],
) -> None:
    """Grava raw sentinel quando o vendor devolveu HTTP error real.

    Payload sentinel: `{"_error": <detail truncado>, "_status": <int>}`.
    sha256 derivado de (status, detail[:200]) — estavel quando o vendor
    repete o mesmo erro em multiplos dias (ex.: 401 com credencial vencida
    durante uma janela). Idempotente sob re-run via UQ
    `uq_wh_qitech_raw_relatorio`.

    Falha gravando raw nao propaga: registra em `step["errors"]` e segue.
    O caller ja vai retornar com erro do sync; este helper e best-effort
    pra evitar gap silencioso no coverage.
    """
    try:
        async with AsyncSessionLocal() as db:
            # Sentinel 4xx — descartamos raw_id e completeness retornados.
            # Nao ha rows canonicas pra gravar (payload eh sentinel de erro),
            # entao replace-by-partition nao se aplica aqui.
            await _upsert_raw(
                db,
                tenant_id=tenant_id,
                tipo_de_mercado=tipo_de_mercado,
                data_posicao=data_posicao,
                payload={
                    "_error": error_detail[:500],
                    "_status": http_status,
                },
                http_status=http_status,
                unidade_administrativa_id=unidade_administrativa_id,
            )
            await db.commit()
        step["raw_persisted"] = True
    except Exception as e:
        step["errors"].append(f"raw_error_sentinel: {type(e).__name__}: {e}")


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
    unidade_administrativa_id: UUID | None = None,
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
            tenant_id=tenant_id,
            environment=environment,
            config=config,
            unidade_administrativa_id=unidade_administrativa_id,
        ) as client:
            payload = await fetch_market_report(
                client=client,
                tipo_de_mercado=tipo_de_mercado,
                posicao=data_posicao,
            )
    except QiTechHttpError as e:
        # 4xx-as-row generalizado (Sub-fase 2B, 2026-05-15): se o vendor
        # devolveu status HTTP real (401/403/404/429/5xx, ou 400 sem shape
        # canonico), grava raw como sentinel pra coverage marcar
        # `not_published` em vez de `gap`. Sinaliza ao polling adaptive
        # "ja tentei este dia" e evita re-enfileiramento eterno do
        # reconciler/watermark scanner.
        #
        # Falhas de rede (status_code IS None — timeout, DNS, connect refused)
        # NAO viram row: sao do nosso lado, devem ser retentadas em ticks
        # subsequentes. Gravar como not_published mascararia o problema.
        if e.status_code is not None:
            step["raw_http_status"] = e.status_code
            await _persist_error_raw(
                tenant_id=tenant_id,
                tipo_de_mercado=tipo_de_mercado,
                data_posicao=data_posicao,
                unidade_administrativa_id=unidade_administrativa_id,
                http_status=e.status_code,
                error_detail=str(e),
                step=step,
            )
        step["errors"].append(f"fetch: HTTP {e.status_code}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step
    except Exception as e:
        step["errors"].append(f"fetch: {type(e).__name__}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step

    step["raw_http_status"] = _infer_http_status(payload, tipo_de_mercado)

    # --- 2. Persiste raw (transacao isolada) ----------------------------
    # Captura raw_id + completeness pra usar na fase 4 (replace-by-partition
    # strict). Em re-upsert do mesmo (tenant, tipo, data, ua), o raw_id eh
    # o mesmo da row pre-existente (UQ bate -> DO UPDATE com RETURNING).
    raw_id: UUID | None = None
    raw_completeness: str | None = None
    if not isinstance(payload, dict):
        step["errors"].append(
            f"raw: payload com shape inesperado ({type(payload).__name__}); raw nao gravada"
        )
    else:
        try:
            async with AsyncSessionLocal() as db:
                raw_id, raw_completeness = await _upsert_raw(
                    db,
                    tenant_id=tenant_id,
                    tipo_de_mercado=tipo_de_mercado,
                    data_posicao=data_posicao,
                    payload=payload,
                    http_status=step["raw_http_status"],
                    unidade_administrativa_id=unidade_administrativa_id,
                )
                await db.commit()
            step["raw_persisted"] = True
            step["raw_id"] = str(raw_id)
            step["raw_completeness"] = raw_completeness
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
    # Fase 1.3 (refactor "espelho fiel QiTech", 2026-05-20): substituido
    # _bulk_upsert_canonical por _replace_canonical_partition. Politica:
    #   - completeness == 'complete' -> UPSERT + DELETE de orfaos da partition
    #   - outros (partial, empty, None) -> no-op no silver (preserva)
    # raw_id eh capturado da Fase 2 acima; fallback pro path legado quando
    # raw_id eh None (payload com shape ruim — raw nao foi gravado).
    if canonical_rows:
        try:
            async with AsyncSessionLocal() as db:
                if raw_id is None:
                    # Fallback: payload com shape ruim; raw nao foi gravado.
                    # Usa UPSERT puro (legado) — nao temos partition key.
                    count = await _bulk_upsert_canonical(
                        db,
                        model,
                        canonical_rows,
                        conflict_columns,
                        unidade_administrativa_id=unidade_administrativa_id,
                    )
                    step["canonical_rows_upserted"] = count
                    step["canonical_mode"] = "upsert_legacy_no_raw_id"
                else:
                    result = await _replace_canonical_partition(
                        db,
                        model,
                        canonical_rows,
                        conflict_columns,
                        raw_id=raw_id,
                        completeness=raw_completeness,
                        tenant_id=tenant_id,
                        endpoint_name=f"market.{tipo_de_mercado}",
                        data_referencia=data_posicao,
                        critical_fields_for_audit=get_critical_fields(
                            model.__tablename__
                        ),
                        unidade_administrativa_id=unidade_administrativa_id,
                    )
                    step["canonical_rows_upserted"] = result["inserted"]
                    step["canonical_mode"] = result["mode"]
                    step["canonical_reason"] = result["reason"]
                    step["canonical_orphans_removed"] = result["orphans_count"]
                await db.commit()
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
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """outros-fundos -> wh_posicao_cota_fundo."""
    return await _sync_endpoint(
        tipo_de_mercado="outros-fundos",
        mapper=map_outros_fundos,
        model=PosicaoCotaFundo,
        # Business key — ver uq_wh_posicao_cota_fundo.
        conflict_columns=[
            "tenant_id", "data_posicao", "carteira_cliente_id", "ativo_codigo",
        ],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def sync_conta_corrente(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """conta-corrente -> wh_saldo_conta_corrente."""
    return await _sync_endpoint(
        tipo_de_mercado="conta-corrente",
        mapper=map_conta_corrente,
        model=SaldoContaCorrente,
        # Business key — ver uq_wh_saldo_conta_corrente.
        conflict_columns=[
            "tenant_id", "data_posicao", "carteira_cliente_id", "codigo",
        ],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def sync_tesouraria(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """tesouraria -> wh_saldo_tesouraria."""
    return await _sync_endpoint(
        tipo_de_mercado="tesouraria",
        mapper=map_tesouraria,
        model=SaldoTesouraria,
        # Business key — ver uq_wh_saldo_tesouraria.
        conflict_columns=["tenant_id", "data_posicao", "carteira_cliente_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def sync_outros_ativos(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """outros-ativos -> wh_posicao_outros_ativos."""
    return await _sync_endpoint(
        tipo_de_mercado="outros-ativos",
        mapper=map_outros_ativos,
        model=PosicaoOutrosAtivos,
        # Business key — ver uq_wh_posicao_outros_ativos.
        conflict_columns=[
            "tenant_id", "data_posicao", "carteira_cliente_id", "codigo",
        ],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def sync_demonstrativo_caixa(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """demonstrativo-caixa -> wh_movimento_caixa."""
    return await _sync_endpoint(
        tipo_de_mercado="demonstrativo-caixa",
        mapper=map_demonstrativo_caixa,
        model=MovimentoCaixa,
        # Business key da partition — ver uq_wh_movimento_caixa_raw_seq
        # (migration f4a2c9d8e1b7, 2026-05-30). `seq_no` (posicao no snapshot)
        # desambigua os lancamentos byte-iguais legitimos que antes barravam a
        # business key. raw_id e injetado por _replace_canonical_partition.
        conflict_columns=["tenant_id", "raw_id", "seq_no"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def sync_cpr(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """cpr -> wh_cpr_movimento."""
    return await _sync_endpoint(
        tipo_de_mercado="cpr",
        mapper=map_cpr,
        model=CprMovimento,
        # Business key — ver uq_wh_cpr_movimento.
        conflict_columns=[
            "tenant_id", "data_posicao", "carteira_cliente_id",
            "descricao", "valor",
        ],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def sync_mec(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """mec -> wh_mec_evolucao_cotas."""
    return await _sync_endpoint(
        tipo_de_mercado="mec",
        mapper=map_mec,
        model=MecEvolucaoCotas,
        # Business key — ver uq_wh_mec_evolucao_cotas.
        conflict_columns=["tenant_id", "data_posicao", "carteira_cliente_id"],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def sync_rentabilidade(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """rentabilidade -> wh_rentabilidade_fundo."""
    return await _sync_endpoint(
        tipo_de_mercado="rentabilidade",
        mapper=map_rentabilidade,
        model=RentabilidadeFundo,
        # Business key — ver uq_wh_rentabilidade_fundo.
        conflict_columns=[
            "tenant_id", "data_posicao", "carteira_cliente_id", "indexador",
        ],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def sync_rf(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """rf -> wh_posicao_renda_fixa."""
    return await _sync_endpoint(
        tipo_de_mercado="rf",
        mapper=map_rf,
        model=PosicaoRendaFixa,
        # Business key — ver uq_wh_posicao_renda_fixa.
        conflict_columns=[
            "tenant_id", "data_posicao", "carteira_cliente_id", "codigo",
        ],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def sync_rf_compromissadas(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    data_posicao: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """rf-compromissadas -> wh_posicao_compromissada."""
    return await _sync_endpoint(
        tipo_de_mercado="rf-compromissadas",
        mapper=map_rf_compromissadas,
        model=PosicaoCompromissada,
        # Business key — ver uq_wh_posicao_compromissada.
        conflict_columns=[
            "tenant_id", "data_posicao", "carteira_cliente_id", "codigo",
        ],
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        data_posicao=data_posicao,
        unidade_administrativa_id=unidade_administrativa_id,
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


async def _mark_dia_util_qitech(
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID,
    data_posicao: date,
) -> bool:
    """Marca o dia em `wh_dia_util_qitech` quando ha sinal de publicacao QiTech.

    Regra Fase C (2026-05-13): MEC continua sendo a tabela-pulse, mas a funcao
    agora e **data-driven** — consulta o estado real no DB ao inves de inspecionar
    `steps` em memoria. Isso desacopla o marcador do caminho que disparou o sync,
    permitindo que tanto `sync_all` (legado, pipeline inteiro) quanto
    `adapter_sync_endpoint` (per-endpoint, Sub-fase 2A) cheguem aqui.

    O bug que motivou a refatoracao: o scheduler novo (per-endpoint) so chamava
    `adapter_sync_endpoint`, que nunca passava por `_mark_dia_util_qitech`.
    Resultado: dias com MEC silver populado nao apareciam no Calendar da pagina
    cota-sub. Ex.: 2026-05-12 — 14/14 endpoints com raw 200 e 2 linhas em
    wh_mec_evolucao_cotas, mas wh_dia_util_qitech sem entrada.

    Sinais consultados:
      * MEC silver (`wh_mec_evolucao_cotas`) tem >=1 linha p/ (tenant, ua, data)?
        - Sim: dia marcado como `completo`.
        - Nao: retorna False, nao escreve (preserva semantica "ausencia").
      * Raw QiTech (`wh_qitech_raw_relatorio`) — quantos `tipo_de_mercado`
        distintos com `http_status=200`? -> `relatorios_recebidos`.
      * `relatorios_esperados` = `len(_PIPELINE)` (constante).

    Idempotente via UQ `(tenant_id, ua_id, data_posicao, source_type)`. Re-rodar
    o mesmo dia atualiza contadores e `ingested_at`.

    Returns:
        True se gravou/atualizou; False se MEC silver ainda nao tem o dia.
    """
    async with AsyncSessionLocal() as db:
        # MEC silver presente para o dia? Sinal de "QiTech publicou".
        mec_present_stmt = select(
            func.count(MecEvolucaoCotas.id)
        ).where(
            MecEvolucaoCotas.tenant_id == tenant_id,
            MecEvolucaoCotas.unidade_administrativa_id == unidade_administrativa_id,
            MecEvolucaoCotas.data_posicao == data_posicao,
        )
        mec_count = (await db.execute(mec_present_stmt)).scalar_one()
        if mec_count <= 0:
            return False

        # Quantos endpoints market.* chegaram com sucesso (raw http 200)?
        # Reflete a realidade independentemente de qual caminho fez o sync.
        recebidos_stmt = select(
            func.count(func.distinct(QiTechRawRelatorio.tipo_de_mercado))
        ).where(
            QiTechRawRelatorio.tenant_id == tenant_id,
            QiTechRawRelatorio.unidade_administrativa_id == unidade_administrativa_id,
            QiTechRawRelatorio.data_posicao == data_posicao,
            QiTechRawRelatorio.http_status == 200,
        )
        recebidos = (await db.execute(recebidos_stmt)).scalar_one() or 0
        esperados = len(_PIPELINE)

        row = {
            "tenant_id": tenant_id,
            "unidade_administrativa_id": unidade_administrativa_id,
            "data_posicao": data_posicao,
            "source_type": "admin:qitech",
            "status": "completo",
            "relatorios_esperados": esperados,
            "relatorios_recebidos": recebidos,
            "ingested_by_version": ADAPTER_VERSION,
        }
        stmt = pg_insert(DiaUtilQitech.__table__).values(row)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_wh_dia_util_qitech",
            set_={
                "status": stmt.excluded.status,
                "relatorios_esperados": stmt.excluded.relatorios_esperados,
                "relatorios_recebidos": stmt.excluded.relatorios_recebidos,
                "ingested_at": datetime.now(UTC),
                "ingested_by_version": stmt.excluded.ingested_by_version,
            },
        )
        await db.execute(stmt)
        await db.commit()
    return True


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
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """Executa todos os syncs registrados em `_PIPELINE` + grava decision_log.

    Isolamento entre endpoints: falha em 1 endpoint NAO impede o proximo
    rodar (cada `sync_<tipo>` ja captura suas exceptions e devolve `step`
    com `errors`). Falha catastrofica (raise saindo do `sync_<tipo>`) e
    capturada aqui e vai pra `errors` agregado.

    Multi-UA (Phase F): `unidade_administrativa_id` propaga para fetch
    (chave de cache de token) + raw + canonical (vincula linhas a UA).
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
                unidade_administrativa_id=unidade_administrativa_id,
            )
            steps.append(step)
            rows_total += int(step.get("canonical_rows_upserted") or 0)
            for err in step.get("errors") or []:
                errors.append(f"{nome}: {err}")
        except Exception as e:
            errors.append(f"{nome}: {type(e).__name__}: {e}")

    # Fase C (CLAUDE.md §13.2.1): marcar dia em wh_dia_util_qitech se MEC
    # publicou. O marcador agora e data-driven (consulta MEC silver + raw
    # http=200 diretamente do banco), entao independe de `sync_all` vs
    # `adapter_sync_endpoint`. Mesma chamada serve a ambos os caminhos.
    dia_util_marcado = False
    if unidade_administrativa_id is not None:
        try:
            dia_util_marcado = await _mark_dia_util_qitech(
                tenant_id=tenant_id,
                unidade_administrativa_id=unidade_administrativa_id,
                data_posicao=data_posicao,
            )
        except Exception as e:
            errors.append(f"dia_util_qitech: {type(e).__name__}: {e}")

    elapsed = time.monotonic() - t0
    summary: dict[str, Any] = {
        "ok": not errors,
        "adapter_version": ADAPTER_VERSION,
        "tenant_id": str(tenant_id),
        "unidade_administrativa_id": (
            str(unidade_administrativa_id)
            if unidade_administrativa_id
            else None
        ),
        "environment": environment.value,
        "data_posicao": data_posicao.isoformat(),
        "started_at": started_at.isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "rows_ingested": rows_total,
        "steps": steps,
        "errors": errors,
        "since": since.isoformat() if since else None,
        "triggered_by": triggered_by,
        "dia_util_marcado": dia_util_marcado,
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
