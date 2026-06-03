"""State machine dispatcher — picks due rows and processes them.

F1.3 do refactor de sync (ver `project_qitech_sync_state_machine` memory).

Tick rodado pelo APScheduler a cada 1 minuto:
1. Reclama orfaos (`in_flight` sem update ha > threshold).
2. SELECT FOR UPDATE SKIP LOCKED N rows com `state IN RETRYABLE_STATES
   AND next_attempt_at <= now()` ORDER BY next_attempt_at LIMIT N.
3. Filtra por `EndpointSpec.state_machine_enabled` em memoria — endpoints
   nao-enabled sao deixados em paz (rollout gradual).
4. Marca IN_FLIGHT.
5. Pra cada row: chama `run_sync_endpoint(since=data_referencia)`. Pos-sync
   le http_status + completeness via fetch_qitech_coverage. Aplica
   `transition(...)` pra calcular novo state + next_attempt_at. UPDATE row.

Tratamento de erros:
- Excecao do adapter: marca row como `not_published` com `last_http_status=None`,
  next_attempt_at calculado pela politica de backoff. Excecao nao derruba o
  tick (proxima row processa).
- Excecao critica (DB down, config invalida): re-raise pra APScheduler
  logar e o tick falhar limpo.

Sleep entre datas: igual ao backfill_service (default 2s) pra nao agredir
o WAF Imperva da Singulare/QiTech.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.coverage import (
    fetch_qitech_coverage,
)
from app.modules.integracoes.models.endpoint_date_state import EndpointDateState
from app.modules.integracoes.models.qitech_report_job import (
    QitechJobStatus,
    QitechReportJob,
)
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
)
from app.modules.integracoes.public import endpoint_catalog
from app.modules.integracoes.services.endpoint_scheduling import (
    SP_TZ,
    anchor_datetime_utc,
)
from app.modules.integracoes.services.state_machine import (
    RETRYABLE_STATES,
    EndpointDateStateValue,
    transition,
)
from app.modules.integracoes.services.sync_runner import run_sync_endpoint
from app.modules.integracoes.services.tolerance import (
    PublicationState,
    ToleranceWindow,
    compute_publication_state,
    count_business_days_between,
    resolve_tolerance_window,
)
from app.shared.endpoint_catalog import EndpointSpec
from app.warehouse.dim_dia_util import DimDiaUtil

logger = logging.getLogger("gr.integracoes.state_machine_dispatcher")

BATCH_SIZE: int = int(os.environ.get("GR_SM_DISPATCHER_BATCH_SIZE", "5"))
INTER_ATTEMPT_SLEEP_S: float = float(
    os.environ.get("GR_SM_DISPATCHER_INTER_ATTEMPT_SLEEP_S", "2.0")
)
# Janela apos a qual uma row em 'in_flight' sem update e considerada
# orfa (processo morreu sem terminar o transition).
_ORPHAN_THRESHOLD_MINUTES: int = int(
    os.environ.get("GR_SM_DISPATCHER_ORPHAN_THRESHOLD_MINUTES", "5")
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — catalogo, tolerancia, calendario
# ─────────────────────────────────────────────────────────────────────────────


def _build_spec_index(source_type: SourceType) -> dict[str, EndpointSpec]:
    """Cria lookup endpoint_name -> EndpointSpec pra source.

    EndpointSpec e frozen dataclass — cache em memoria do processo. Cada
    tick rebuilda (barato; ~13 entries pra QiTech).
    """
    return {spec.name: spec for spec in endpoint_catalog(source_type)}


async def _load_tolerance_for_endpoint(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment,
    unidade_administrativa_id: UUID | None,
    endpoint_name: str,
    spec: EndpointSpec,
) -> ToleranceWindow | None:
    """Resolve janela de tolerancia para (tenant, endpoint), com fallback.

    Override do TSEC sobrescreve campo a campo o default do catalogo. Retorna
    None se a combinacao viola monotonicidade (improvavel, mas defensivo).
    """
    stmt = select(
        TenantSourceEndpointConfig.expected_lag_business_days_override,
        TenantSourceEndpointConfig.tolerance_business_days_override,
        TenantSourceEndpointConfig.give_up_business_days_override,
    ).where(
        TenantSourceEndpointConfig.tenant_id == tenant_id,
        TenantSourceEndpointConfig.source_type == source_type,
        TenantSourceEndpointConfig.environment == environment,
        TenantSourceEndpointConfig.endpoint_name == endpoint_name,
    )
    if unidade_administrativa_id is None:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id.is_(None)
        )
    else:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id
            == unidade_administrativa_id
        )
    row = (await db.execute(stmt)).first()
    ov = row if row is not None else (None, None, None)
    try:
        return resolve_tolerance_window(
            expected_lag_override=ov[0],
            tolerance_override=ov[1],
            give_up_override=ov[2],
            default_expected_lag=spec.default_expected_lag_business_days,
            default_tolerance=spec.default_tolerance_business_days,
            default_give_up=spec.default_give_up_business_days,
        )
    except ValueError:
        return None


async def _load_schedule_for_endpoint(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    environment: Environment,
    unidade_administrativa_id: UUID | None,
    endpoint_name: str,
    spec: EndpointSpec,
) -> tuple[str, str | None]:
    """Resolve (schedule_kind, schedule_value) efetivo do endpoint.

    Override do TSEC OU default do catalogo. `schedule_kind` e NOT NULL no TSEC,
    e kind+value sao acoplados pelo CHECK `ck_tsec_schedule_value_format`, entao
    resolvemos o PAR (se ha linha TSEC, usa o par dela; senao, default do spec).
    Usado pelo gate de ancora pra saber o horario de inicio do ciclo diario
    (`daily_at` HH:MM em SP).
    """
    stmt = select(
        TenantSourceEndpointConfig.schedule_kind,
        TenantSourceEndpointConfig.schedule_value,
    ).where(
        TenantSourceEndpointConfig.tenant_id == tenant_id,
        TenantSourceEndpointConfig.source_type == source_type,
        TenantSourceEndpointConfig.environment == environment,
        TenantSourceEndpointConfig.endpoint_name == endpoint_name,
    )
    if unidade_administrativa_id is None:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id.is_(None)
        )
    else:
        stmt = stmt.where(
            TenantSourceEndpointConfig.unidade_administrativa_id
            == unidade_administrativa_id
        )
    row = (await db.execute(stmt)).first()
    if row is not None and row[0]:
        return (row[0], row[1])
    return (spec.default_schedule_kind.value, spec.default_schedule_value)


async def _load_business_days(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    start: date,
    end: date,
) -> frozenset[date]:
    """Carrega calendario ANBIMA pro range — 1 select por tick."""
    stmt = select(DimDiaUtil.data).where(
        DimDiaUtil.tenant_id == tenant_id,
        DimDiaUtil.data.between(start, end),
        DimDiaUtil.eh_dia_util.is_(True),
    )
    rows = (await db.execute(stmt)).scalars().all()
    return frozenset(rows)


def _anchor_defer_at(
    *,
    reference_date: date,
    now: datetime,
    business_days_set: frozenset[date],
    window: ToleranceWindow,
    schedule_kind: str,
    schedule_value: str | None,
) -> datetime | None:
    """Gate pre-POST: re-agenda rows que ainda nao devem ser tentadas.

    Combina DUAS regras numa so, devolvendo o instante (em UTC) ate o qual a
    row deve dormir, ou None quando ela pode ser tentada agora:

    1. **Publicabilidade** — a fonte nunca tem o dado de uma `reference_date`
       cujo `expected_lag` (dias uteis) ainda nao decorreu. O seeder semeia
       `SEED_AHEAD_BD` dias uteis A FRENTE com `next_attempt_at=now`; sem este
       gate, ~70% das chamadas QiTech de `fidc_estoque` eram queimadas em datas
       futuras (relatorio vazio 0-byte a cada tick).
    2. **Ancora diaria** — para `schedule_kind='daily_at'`, o ciclo do dia so
       comeca no horario HH:MM SP configurado (`schedule_value`, default 09:00
       do catalogo). Antes da ancora nao se tenta; depois da meia-noite a row
       fica retida ate a proxima ancora (hold overnight).

    Implementacao unica: `target_day = max(publishable_day, today)` e
    `earliest = ancora(target_day)`. Se `now < earliest`, devolve `earliest`.

    - `publishable_day` = `expected_lag`-esimo dia util estritamente apos a
      referencia (lag=0 -> a propria referencia). Fallback `today+1` quando o
      calendario carregado nao alcanca (referencia muito a frente; converge).
    - `daily_at` ancora em HH:MM SP; demais kinds (interval/on_demand, hoje
      inexistentes entre endpoints state-machine) caem no floor de
      publicabilidade 09:00 SP — equivalente ao comportamento anterior.

    A data de "hoje" e derivada de `now` em SP (NAO a data UTC) — o ciclo
    diario e definido em horario de Brasilia, e perto da meia-noite UTC a data
    UTC ja virou enquanto em SP ainda e o mesmo dia.
    """
    today_sp = now.astimezone(SP_TZ).date()
    bd_since_ref = count_business_days_between(
        reference_date=reference_date,
        today=today_sp,
        business_days_set=business_days_set,
    )
    if bd_since_ref >= window.expected_lag_business_days:
        publishable_day = today_sp
    else:
        future_bds = sorted(d for d in business_days_set if d > reference_date)
        if len(future_bds) >= window.expected_lag_business_days:
            # lag >= 1 garantido aqui (lag=0 -> bd_since_ref>=0 cai no ramo acima).
            publishable_day = future_bds[window.expected_lag_business_days - 1]
        else:
            publishable_day = today_sp + timedelta(days=1)

    target_day = max(publishable_day, today_sp)
    hhmm = (
        schedule_value
        if (schedule_kind == "daily_at" and schedule_value)
        else "09:00"
    )
    earliest = anchor_datetime_utc(day=target_day, hhmm=hhmm)
    return earliest if now < earliest else None


async def _fetch_latest_raw_status(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    source_type: SourceType,
    endpoint_name: str,
    data_referencia: date,
) -> tuple[int | None, str | None]:
    """Le http_status + completeness do raw layer mais recente pra (endpoint, data).

    Adapter QiTech grava em wh_qitech_raw_relatorio. Pos-run_sync_endpoint,
    aqui le o resultado pra alimentar transition(). Outros adapters podem
    nao ter coverage — fallback retorna (None, None) e transition trata
    como NOT_PUBLISHED.
    """
    if source_type != SourceType.ADMIN_QITECH:
        return (None, None)
    rows = await fetch_qitech_coverage(
        db,
        endpoint_name=endpoint_name,
        tenant_id=tenant_id,
        unidade_administrativa_id=unidade_administrativa_id,
        start_date=data_referencia,
        end_date=data_referencia,
    )
    if not rows:
        return (None, None)
    # 1 row esperada pro range start=end.
    r = rows[0]
    return (r.http_status, r.completeness)


# ─────────────────────────────────────────────────────────────────────────────
# Async report endpoints (job + webhook)
# ─────────────────────────────────────────────────────────────────────────────

# Mapa endpoint_name -> report_type do QitechReportJob, pros endpoints
# assincronos (is_async_report=True). Hoje so fidc_estoque; o report_type
# difere do endpoint_name (hifen vs underscore, sem prefixo 'market.').
_ASYNC_REPORT_TYPE_BY_ENDPOINT: dict[str, str] = {
    "market.fidc_estoque": "fidc-estoque",
}

# Estados de QitechReportJob que significam "POST ja feito, resultado ainda
# a caminho" — enquanto um job esta nesses estados, NAO disparamos outro
# (anti job-storm). SUCCESS/EMPTY/ERROR sao terminais: liberam re-POST.
_ACTIVE_REPORT_JOB_STATUSES = (
    QitechJobStatus.WAITING,
    QitechJobStatus.PROCESSING,
)


async def _has_active_async_report_job(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    report_type: str,
    reference_date: date,
) -> bool:
    """True se ha QitechReportJob WAITING/PROCESSING pra (tenant, ua, data).

    Guard de in-flight: equivalente ao `_active_async_job_dates_for_fidc_estoque`
    do reconciler legado. Sem ele, o dispatcher dispararia um job novo a cada
    poll enquanto o callback do anterior nao chega — job-storm na QiTech.
    """
    stmt = select(QitechReportJob.id).where(
        QitechReportJob.tenant_id == tenant_id,
        QitechReportJob.report_type == report_type,
        QitechReportJob.reference_date == reference_date,
        QitechReportJob.status.in_(_ACTIVE_REPORT_JOB_STATUSES),
    )
    if unidade_administrativa_id is not None:
        stmt = stmt.where(
            QitechReportJob.unidade_administrativa_id == unidade_administrativa_id
        )
    else:
        stmt = stmt.where(QitechReportJob.unidade_administrativa_id.is_(None))
    return (await db.execute(stmt.limit(1))).first() is not None


async def _process_async_report_row(
    row: EndpointDateState,
    *,
    spec: EndpointSpec,
) -> dict[str, Any]:
    """Processa 1 row de endpoint assincrono (job + webhook).

    Diferenca do fluxo sincrono (`_process_row`): o resultado de um POST nao
    fica disponivel na hora — chega depois via webhook
    (`process_fidc_estoque_callback`), que grava o raw. Por isso aqui:

    1. LE o raw PRIMEIRO. Se ja ha dado (webhook de um POST anterior ja
       chegou) -> transition normal -> COMPLETE/EMPTY/PARTIAL.
    2. Se nao ha dado E nao ha job ativo (WAITING/PROCESSING) -> dispara um
       POST novo via run_sync_endpoint. O resultado vira no proximo poll.
    3. Se nao ha dado MAS ha job ativo -> NAO dispara (guard de in-flight);
       so re-agenda.

    Em todos os casos o `transition` final usa a leitura do raw (passos 1/2/3),
    NUNCA o resultado imediato do POST (que seria sempre "sem dado"). Assim o
    backoff de tolerancia (30min/2h/12h) governa o ritmo de re-POST e o
    give_up_business_days eventualmente leva a ABANDONED — sem o cap cego de
    tentativas do reconciler legado.
    """
    out: dict[str, Any] = {"row_id": str(row.id), "ok": False, "new_state": None}
    source_type = SourceType(row.source_type)
    environment = Environment(row.environment)
    report_type = _ASYNC_REPORT_TYPE_BY_ENDPOINT.get(row.endpoint_name)

    now = datetime.now(UTC)
    today = now.date()

    # 1. Le o estado atual do raw (resultado de webhook de POST anterior).
    async with AsyncSessionLocal() as db:
        http_status, completeness = await _fetch_latest_raw_status(
            db,
            tenant_id=row.tenant_id,
            unidade_administrativa_id=row.unidade_administrativa_id,
            source_type=source_type,
            endpoint_name=row.endpoint_name,
            data_referencia=row.data_referencia,
        )

    has_data = http_status is not None and 200 <= http_status < 300

    # 2. Resolve tolerancia + calendario ANTES de decidir POSTar — precisamos
    #    do estado de publicacao pra nao disparar job em data ja vencida
    #    (FURO_DEFINITIVO -> ABANDONED sem martelar a fonte morta).
    async with AsyncSessionLocal() as db:
        window = await _load_tolerance_for_endpoint(
            db,
            tenant_id=row.tenant_id,
            source_type=source_type,
            environment=environment,
            unidade_administrativa_id=row.unidade_administrativa_id,
            endpoint_name=row.endpoint_name,
            spec=spec,
        )
    if window is None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(EndpointDateState)
                .where(EndpointDateState.id == row.id)
                .values(
                    state=EndpointDateStateValue.NOT_STARTED.value,
                    next_attempt_at=now + timedelta(hours=1),
                    updated_at=now,
                )
            )
            await db.commit()
        out["error"] = "invalid_tolerance_window"
        return out

    cal_start = min(row.data_referencia, today) - timedelta(days=60)
    cal_end = today + timedelta(days=5)
    async with AsyncSessionLocal() as db:
        business_days_set = await _load_business_days(
            db, tenant_id=row.tenant_id, start=cal_start, end=cal_end
        )
        schedule_kind, schedule_value = await _load_schedule_for_endpoint(
            db,
            tenant_id=row.tenant_id,
            source_type=source_type,
            environment=environment,
            unidade_administrativa_id=row.unidade_administrativa_id,
            endpoint_name=row.endpoint_name,
            spec=spec,
        )

    tolerance_state = compute_publication_state(
        reference_date=row.data_referencia,
        today=today,
        business_days_set=business_days_set,
        window=window,
    )

    # Gate de ancora: nao tenta antes do dado ser publicavel (expected_lag) NEM
    # antes do horario de inicio do ciclo diario (daily_at HH:MM SP). Re-agenda
    # SEM POSTar (evita job vazio 0-byte a cada tick e tentativas de madrugada).
    # `has_data` tem precedencia: se um webhook ja entregou o dado (caso raro
    # de data "futura" com payload), segue pro transition normal -> COMPLETE.
    defer_at = (
        None
        if has_data
        else _anchor_defer_at(
            reference_date=row.data_referencia,
            now=now,
            business_days_set=business_days_set,
            window=window,
            schedule_kind=schedule_kind,
            schedule_value=schedule_value,
        )
    )
    if defer_at is not None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(EndpointDateState)
                .where(EndpointDateState.id == row.id)
                .values(
                    state=EndpointDateStateValue.NOT_STARTED.value,
                    next_attempt_at=defer_at,
                    updated_at=now,
                )
            )
            await db.commit()
        out["ok"] = True
        out["new_state"] = EndpointDateStateValue.NOT_STARTED.value
        out["deferred_future_reference"] = True
        return out

    posted = False
    # 3. Sem dado ainda E dentro da janela de give_up — dispara POST so se nao
    #    houver job ativo (guard de in-flight). Data ja em FURO_DEFINITIVO nao
    #    dispara: o transition abaixo a leva direto a ABANDONED.
    if (
        not has_data
        and report_type is not None
        and tolerance_state != PublicationState.FURO_DEFINITIVO
    ):
        async with AsyncSessionLocal() as db:
            active = await _has_active_async_report_job(
                db,
                tenant_id=row.tenant_id,
                unidade_administrativa_id=row.unidade_administrativa_id,
                report_type=report_type,
                reference_date=row.data_referencia,
            )
        if not active:
            try:
                await run_sync_endpoint(
                    row.tenant_id,
                    source_type,
                    row.endpoint_name,
                    environment=environment,
                    since=row.data_referencia,
                    triggered_by=f"state_machine:{row.id}",
                    unidade_administrativa_id=row.unidade_administrativa_id,
                )
                posted = True
            except Exception as e:
                logger.exception(
                    "state_machine(async): POST falhou pra row=%s endpoint=%s data=%s",
                    row.id,
                    row.endpoint_name,
                    row.data_referencia,
                )
                out["error"] = f"{type(e).__name__}: {e}"

    # 4. Transita com base na LEITURA do raw (has_data ? 200 : None) — nunca
    #    no resultado imediato do POST (que seria sempre "sem dado").
    updates = transition(
        data_referencia=row.data_referencia,
        today=today,
        now=now,
        business_days_set=business_days_set,
        window=window,
        refresh_complete_window_business_days=(
            spec.refresh_complete_window_business_days
        ),
        http_status=http_status if has_data else None,
        completeness=completeness if has_data else None,
        previous_attempts_count=row.attempts_count,
    )

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(EndpointDateState)
            .where(EndpointDateState.id == row.id)
            .values(**updates, updated_at=now)
        )
        await db.commit()

    out["ok"] = True
    out["new_state"] = updates["state"]
    out["http_status"] = http_status if has_data else None
    out["completeness"] = completeness if has_data else None
    out["async_posted"] = posted
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────


async def _reclaim_orphans() -> int:
    """Reclama rows em `in_flight` sem update ha > threshold.

    Worker morreu (OOM kill, restart) deixando row em in_flight pra sempre.
    Volta pro estado anterior implicito: not_started com next_attempt_at=now.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=_ORPHAN_THRESHOLD_MINUTES)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(EndpointDateState)
            .where(
                EndpointDateState.state == EndpointDateStateValue.IN_FLIGHT.value,
                EndpointDateState.updated_at < cutoff,
            )
            .values(
                state=EndpointDateStateValue.NOT_STARTED.value,
                next_attempt_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()
        if result.rowcount:
            logger.warning(
                "state_machine: reclaimed %d orfaos (in_flight sem update > %dmin)",
                result.rowcount,
                _ORPHAN_THRESHOLD_MINUTES,
            )
        return result.rowcount or 0


async def _pick_due_rows(limit: int) -> list[EndpointDateState]:
    """SELECT FOR UPDATE SKIP LOCKED das proximas N rows due.

    Marca cada uma como in_flight na mesma transacao — workers concorrentes
    nao pegam as mesmas rows.
    """
    now = datetime.now(UTC)
    retryable_values = [s.value for s in RETRYABLE_STATES]
    async with AsyncSessionLocal() as db:
        stmt = (
            select(EndpointDateState)
            .where(
                EndpointDateState.state.in_(retryable_values),
                or_(
                    EndpointDateState.next_attempt_at.is_(None),
                    EndpointDateState.next_attempt_at <= now,
                ),
            )
            .order_by(EndpointDateState.next_attempt_at.asc().nulls_first())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        if not rows:
            return []
        ids = [r.id for r in rows]
        await db.execute(
            update(EndpointDateState)
            .where(EndpointDateState.id.in_(ids))
            .values(
                state=EndpointDateStateValue.IN_FLIGHT.value,
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()
        # Re-fetch sem o lock pra usar nos workers (lock liberado no commit).
        return rows


async def _process_row(
    row: EndpointDateState,
    *,
    spec_index: dict[str, EndpointSpec],
) -> dict[str, Any]:
    """Processa 1 row in_flight — chama sync, le resultado, calcula transition,
    atualiza row.

    Retorna dict com {ok, error, new_state} pro logging.
    """
    out: dict[str, Any] = {"row_id": str(row.id), "ok": False, "new_state": None}

    spec = spec_index.get(row.endpoint_name)
    if spec is None or not spec.state_machine_enabled:
        # Endpoint saiu do catalogo OU flag desligada — devolve a row pro estado
        # anterior implicito (not_started) com next_attempt_at no futuro (1h)
        # pra ela nao re-aparecer no proximo tick.
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(EndpointDateState)
                .where(EndpointDateState.id == row.id)
                .values(
                    state=EndpointDateStateValue.NOT_STARTED.value,
                    next_attempt_at=datetime.now(UTC) + timedelta(hours=1),
                    updated_at=datetime.now(UTC),
                )
            )
            await db.commit()
        out["error"] = "endpoint_not_enabled"
        return out

    # Endpoints assincronos (job + webhook) tem fluxo proprio: o POST nao
    # devolve o dado na hora, entao nao da pra ler o raw logo apos run_sync.
    # Delega pro branch async (guard de in-flight + transition na leitura do raw).
    if spec.is_async_report:
        return await _process_async_report_row(row, spec=spec)

    source_type = SourceType(row.source_type)
    environment = Environment(row.environment)
    now = datetime.now(UTC)
    today = now.date()

    # Resolve tolerancia + calendario ANTES de chamar o sync — pra barrar
    # `data_referencia` ainda nao publicavel (seed +N d.u. a frente) sem bater
    # na fonte (geraria chamada inutil / 0-byte a cada tick). Ver gate abaixo.
    async with AsyncSessionLocal() as db:
        window = await _load_tolerance_for_endpoint(
            db,
            tenant_id=row.tenant_id,
            source_type=source_type,
            environment=environment,
            unidade_administrativa_id=row.unidade_administrativa_id,
            endpoint_name=row.endpoint_name,
            spec=spec,
        )

    if window is None:
        # Combinacao override+default violou monotonicidade — re-fila pra 1h
        # e loga (operador conserta TSEC).
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(EndpointDateState)
                .where(EndpointDateState.id == row.id)
                .values(
                    state=EndpointDateStateValue.NOT_STARTED.value,
                    next_attempt_at=now + timedelta(hours=1),
                    updated_at=now,
                )
            )
            await db.commit()
        out["error"] = "invalid_tolerance_window"
        return out

    # Calendario: carrega janela ampla pra cobrir give_up_business_days * ~2
    # (precisa de uteis entre data_referencia e today).
    cal_start = min(row.data_referencia, today) - timedelta(days=60)
    cal_end = today + timedelta(days=5)
    async with AsyncSessionLocal() as db:
        business_days_set = await _load_business_days(
            db, tenant_id=row.tenant_id, start=cal_start, end=cal_end
        )
        schedule_kind, schedule_value = await _load_schedule_for_endpoint(
            db,
            tenant_id=row.tenant_id,
            source_type=source_type,
            environment=environment,
            unidade_administrativa_id=row.unidade_administrativa_id,
            endpoint_name=row.endpoint_name,
            spec=spec,
        )

    # Gate de ancora (mesma logica do branch async): nao chama o sync antes do
    # dado ser publicavel NEM antes do horario de inicio do ciclo diario.
    defer_at = _anchor_defer_at(
        reference_date=row.data_referencia,
        now=now,
        business_days_set=business_days_set,
        window=window,
        schedule_kind=schedule_kind,
        schedule_value=schedule_value,
    )
    if defer_at is not None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(EndpointDateState)
                .where(EndpointDateState.id == row.id)
                .values(
                    state=EndpointDateStateValue.NOT_STARTED.value,
                    next_attempt_at=defer_at,
                    updated_at=now,
                )
            )
            await db.commit()
        out["ok"] = True
        out["new_state"] = EndpointDateStateValue.NOT_STARTED.value
        out["deferred_future_reference"] = True
        return out

    # Chama o sync — captura excecoes pra nao derrubar o tick.
    http_status: int | None = None
    completeness: str | None = None
    sync_error: str | None = None
    try:
        await run_sync_endpoint(
            row.tenant_id,
            source_type,
            row.endpoint_name,
            environment=environment,
            since=row.data_referencia,
            triggered_by=f"state_machine:{row.id}",
            unidade_administrativa_id=row.unidade_administrativa_id,
        )
    except Exception as e:
        sync_error = f"{type(e).__name__}: {e}"
        logger.exception(
            "state_machine: sync falhou pra row=%s endpoint=%s data=%s",
            row.id,
            row.endpoint_name,
            row.data_referencia,
        )

    # Le resultado do raw layer (ou retorna None,None se nao gravou).
    async with AsyncSessionLocal() as db:
        if sync_error is None:
            http_status, completeness = await _fetch_latest_raw_status(
                db,
                tenant_id=row.tenant_id,
                unidade_administrativa_id=row.unidade_administrativa_id,
                source_type=source_type,
                endpoint_name=row.endpoint_name,
                data_referencia=row.data_referencia,
            )

    updates = transition(
        data_referencia=row.data_referencia,
        today=today,
        now=now,
        business_days_set=business_days_set,
        window=window,
        refresh_complete_window_business_days=(
            spec.refresh_complete_window_business_days
        ),
        http_status=http_status,
        completeness=completeness,
        previous_attempts_count=row.attempts_count,
    )

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(EndpointDateState)
            .where(EndpointDateState.id == row.id)
            .values(**updates, updated_at=now)
        )
        await db.commit()

    out["ok"] = True
    out["new_state"] = updates["state"]
    out["http_status"] = http_status
    out["completeness"] = completeness
    if sync_error:
        out["error"] = sync_error
    return out


async def dispatch_due() -> dict[str, Any]:
    """Tick principal do scheduler.

    Reclama orfaos -> Pega N rows due -> processa serialmente com sleep
    entre attempts. Workers concorrentes nao pegam mesmas rows (lock).

    Returns: summary com counters pra logging.
    """
    summary: dict[str, Any] = {
        "orphans_reclaimed": 0,
        "rows_picked": 0,
        "rows_processed_ok": 0,
        "rows_skipped_disabled": 0,
        "rows_errored": 0,
        "elapsed_seconds": 0.0,
    }
    started_at = datetime.now(UTC)

    summary["orphans_reclaimed"] = await _reclaim_orphans()

    rows = await _pick_due_rows(BATCH_SIZE)
    summary["rows_picked"] = len(rows)
    if not rows:
        summary["elapsed_seconds"] = round(
            (datetime.now(UTC) - started_at).total_seconds(), 2
        )
        return summary

    # Cache spec_index por source_type (em memoria, custa proximo de zero).
    spec_cache: dict[SourceType, dict[str, EndpointSpec]] = {}

    for i, row in enumerate(rows):
        source_type = SourceType(row.source_type)
        if source_type not in spec_cache:
            spec_cache[source_type] = _build_spec_index(source_type)

        try:
            result = await _process_row(row, spec_index=spec_cache[source_type])
        except Exception as e:
            # Excecao critica fora do path coberto em _process_row — loga
            # e devolve row pro estado retentavel pra nao ficar presa.
            logger.exception(
                "state_machine: _process_row crashou pra row=%s: %s", row.id, e
            )
            summary["rows_errored"] += 1
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(EndpointDateState)
                    .where(EndpointDateState.id == row.id)
                    .values(
                        state=EndpointDateStateValue.NOT_STARTED.value,
                        next_attempt_at=datetime.now(UTC) + timedelta(hours=1),
                        updated_at=datetime.now(UTC),
                    )
                )
                await db.commit()
            continue

        if result.get("error") == "endpoint_not_enabled":
            summary["rows_skipped_disabled"] += 1
        elif result.get("ok"):
            summary["rows_processed_ok"] += 1
            logger.info(
                "state_machine: row=%s endpoint=%s data=%s new_state=%s "
                "http=%s completeness=%s",
                row.id,
                row.endpoint_name,
                row.data_referencia,
                result["new_state"],
                result.get("http_status"),
                result.get("completeness"),
            )
        else:
            summary["rows_errored"] += 1

        # Pause entre attempts pra nao agredir WAF Imperva — mesmo padrao
        # do backfill_service. Skip no ultimo da batelada.
        if i < len(rows) - 1 and INTER_ATTEMPT_SLEEP_S > 0:
            await asyncio.sleep(INTER_ATTEMPT_SLEEP_S)

    summary["elapsed_seconds"] = round(
        (datetime.now(UTC) - started_at).total_seconds(), 2
    )
    return summary


# Suprime warning de unused import (and_ usado em variante futura)
__all__ = ["dispatch_due"]
_ = and_
