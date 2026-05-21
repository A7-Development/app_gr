"""Reconciler service — auto-heal de syncs QiTech.

Padrao "reconciliation loop" (Kubernetes controller pattern) aplicado a
dados: detecta drift entre **estado desejado** (todos os dias uteis ANBIMA
da janela devem estar coletados com dado integro) e **estado real**
(linhas em wh_qitech_raw_relatorio), enfileira BackfillJob pros furos.

Fase 1.6 (2026-05-16) — candidate set ampliado: alem de GAP (dia sem
nenhuma linha raw), agora cobre tambem PARTIAL (200 com subset esperado
ausente — caso MEC/RF que ficava preso indefinidamente) e NOT_PUBLISHED
(4xx-as-row gravado por excecao do vendor). Cooldown por estado de
tolerancia (ATRASADO 4h, SUSPEITO 24h) modula a frequencia de retry;
FURO_DEFINITIVO sai do candidate set sozinho.

Roadmap pendente:
- Token bucket/circuit breaker (Fase 2)
- Health score + alertas (Fase 3)

Algoritmo (por tick, default a cada 30 min):

    1. List enabled configs de admin:qitech (tenants ativos, env=production).
    2. Para cada (tenant, ua) na lista:
       a. Chama get_source_coverage com lookback=N dias.
       b. Para cada endpoint do catalogo com count_gap > 0:
          i.  Se ja existe BackfillJob ativo (pending/running) pra
              (tenant, ua, endpoint), pula — nao duplica.
          ii. Cria BackfillJob com created_by='system:reconciler' e
              registra entry no decision_log.

Idempotencia: skip por job ativo + BackfillJob.create dedupe de datas. Re-rodar
o reconciler 2x em sequencia (no caso patologico) gera no maximo 2 jobs com
datas iguais, mas o segundo nao chega a criar nada por causa do skip.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.custodia import (
    resolve_cnpj_by_ua_id,
)
from app.modules.integracoes.models.backfill_job import BackfillJob
from app.modules.integracoes.models.qitech_report_job import (
    QitechJobStatus,
    QitechReportJob,
)
from app.modules.integracoes.services.backfill_service import create_backfill_job
from app.modules.integracoes.services.coverage import (
    CoverageStatus,
    PublicationState,
    get_source_coverage,
)
from app.modules.integracoes.services.eligibility import list_enabled_configs
from app.modules.integracoes.services.endpoint_routing import (
    is_state_machine_enabled,
)
from app.shared.audit_log.decision_log import DecisionLog, DecisionType

logger = logging.getLogger("gr.integracoes.reconciler")

RECONCILER_CREATED_BY = "system:reconciler"


@dataclass(frozen=True)
class GapToHeal:
    """Drift detectado: um endpoint de uma UA tem N datas a curar.

    Nome legado — apos 2026-05-16 cobre tambem PARTIAL e NOT_PUBLISHED,
    nao apenas GAP. Renomear quebraria callers; o conceito ficou o mesmo:
    'datas que o sistema precisa retentar'.
    """

    tenant_id: UUID
    unidade_administrativa_id: UUID | None
    endpoint_name: str
    dates: list[date]


async def _has_active_backfill_job(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    unidade_administrativa_id: UUID | None,
    endpoint_name: str,
) -> bool:
    """True se existe BackfillJob pending/running pra (tenant, ua, endpoint).

    Evita o reconciler criar 2 jobs em ticks consecutivos antes do worker
    pegar o primeiro. Tambem evita stomp em backfill manual disparado pela UI.
    """
    stmt = select(BackfillJob.id).where(
        BackfillJob.tenant_id == tenant_id,
        BackfillJob.source_type == source_type.value,
        BackfillJob.endpoint_name == endpoint_name,
        BackfillJob.status.in_(["pending", "running"]),
    )
    if unidade_administrativa_id is not None:
        stmt = stmt.where(
            BackfillJob.unidade_administrativa_id == unidade_administrativa_id
        )
    else:
        stmt = stmt.where(BackfillJob.unidade_administrativa_id.is_(None))
    return (await db.execute(stmt.limit(1))).first() is not None


async def _count_attempts_by_date(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    unidade_administrativa_id: UUID | None,
    endpoint_name: str,
    dates: list[date],
) -> dict[date, int]:
    """Conta quantos BackfillJobs ja tocaram cada data (histórico completo).

    Soma de `dates_pending + dates_done` (cancelled e failed contam tambem,
    porque ja consumiram chamada API). Resultado alimenta o cap de
    tentativas — datas com >= MAX_ATTEMPTS sao puladas pra nao martelar
    fonte "morta" 1440x na janela de 30 dias (Fase 1.5).

    Fase 2 vai substituir este contador grosseiro pela tabela
    `qitech_retry_state` com backoff exponencial + status='unrecoverable'.
    """
    if not dates:
        return {}
    # Unnest dates_pending + dates_done em rows individuais via SQL nativo —
    # SQLAlchemy func.unnest sobre array Postgres da o array exato sem
    # carregar JSONB inteiro em Python. Bem mais leve quando ha milhares
    # de jobs historicos.
    stmt = select(
        func.unnest(
            func.array_cat(BackfillJob.dates_pending, BackfillJob.dates_done)
        ).label("d")
    ).where(
        BackfillJob.tenant_id == tenant_id,
        BackfillJob.source_type == source_type.value,
        BackfillJob.endpoint_name == endpoint_name,
    )
    if unidade_administrativa_id is not None:
        stmt = stmt.where(
            BackfillJob.unidade_administrativa_id == unidade_administrativa_id
        )
    else:
        stmt = stmt.where(BackfillJob.unidade_administrativa_id.is_(None))

    counts: dict[date, int] = dict.fromkeys(dates, 0)
    dates_set = set(dates)
    for row in (await db.execute(stmt)).all():
        d = row[0]
        if d in dates_set:
            counts[d] += 1
    return counts


async def _last_attempt_at_by_date(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    unidade_administrativa_id: UUID | None,
    endpoint_name: str,
    dates: list[date],
) -> dict[date, datetime]:
    """Para cada data candidata, MAX(BackfillJob.created_at) entre os jobs
    que tocaram aquela data.

    Usado pelo modulator de cadencia: data em estado ATRASADO so e
    re-enfileirada se passaram >= 4h desde a ultima tentativa. SUSPEITO
    espera >= 24h. ESPERADO entra a cada tick (skip_window = 0).
    """
    if not dates:
        return {}
    stmt = select(
        func.unnest(
            func.array_cat(BackfillJob.dates_pending, BackfillJob.dates_done)
        ).label("d"),
        BackfillJob.created_at,
    ).where(
        BackfillJob.tenant_id == tenant_id,
        BackfillJob.source_type == source_type.value,
        BackfillJob.endpoint_name == endpoint_name,
    )
    if unidade_administrativa_id is not None:
        stmt = stmt.where(
            BackfillJob.unidade_administrativa_id == unidade_administrativa_id
        )
    else:
        stmt = stmt.where(BackfillJob.unidade_administrativa_id.is_(None))

    out: dict[date, datetime] = {}
    dates_set = set(dates)
    for row in (await db.execute(stmt)).all():
        d = row[0]
        if d in dates_set:
            ts = row[1]
            if d not in out or ts > out[d]:
                out[d] = ts
    return out


# Janelas de cooldown por estado — quanto tempo esperar entre tentativas.
# ESPERADO: sem cooldown (cada tick do reconciler pode disparar).
# ATRASADO: 4h.
# SUSPEITO: 24h.
# FURO_DEFINITIVO: skip total (filtrado antes de chegar aqui).
_COOLDOWN_BY_STATE: dict[PublicationState, timedelta] = {
    PublicationState.ESPERADO: timedelta(seconds=0),
    PublicationState.ATRASADO: timedelta(hours=4),
    PublicationState.SUSPEITO: timedelta(hours=24),
}


def _dates_due_for_retry(
    *,
    candidates: list[tuple[date, PublicationState]],
    last_attempt_by_date: dict[date, datetime],
    now: datetime,
) -> list[date]:
    """Filtra datas pelo cooldown do estado de tolerancia.

    Retorna apenas as datas cuja ultima tentativa esta mais antiga que o
    cooldown do estado, ou que nunca foram tentadas (sem entrada em
    `last_attempt_by_date`).
    """
    out: list[date] = []
    for d, state in candidates:
        cooldown = _COOLDOWN_BY_STATE.get(state)
        if cooldown is None:
            # FURO_DEFINITIVO ou estado desconhecido — skip.
            continue
        last_at = last_attempt_by_date.get(d)
        if last_at is None or (now - last_at) >= cooldown:
            out.append(d)
    return out


async def _active_async_job_dates_for_fidc_estoque(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
) -> set[date]:
    """Datas com QitechReportJob ativo (WAITING/PROCESSING) pra fidc_estoque.

    Especifico do fluxo assincrono job+webhook (`market.fidc_estoque`). Se
    o POST ja foi feito e o callback ainda nao chegou, o reconciler nao
    deve disparar OUTRO job na QiTech — desperdicia recurso e pode
    confundir o tracker. Skip ate o callback chegar (sucesso ou timeout).

    Demais endpoints sincronos nao precisam dessa protecao — eles upsertam
    raw direto, idempotente. Re-disparar custa 1 chamada extra mas o silver
    nao quebra.
    """
    if unidade_administrativa_id is None:
        return set()
    cnpj = await resolve_cnpj_by_ua_id(
        tenant_id=tenant_id,
        unidade_administrativa_id=unidade_administrativa_id,
    )
    if not cnpj:
        return set()
    cnpj_digits = "".join(c for c in cnpj if c.isdigit())
    stmt = select(QitechReportJob.reference_date).where(
        QitechReportJob.tenant_id == tenant_id,
        QitechReportJob.cnpj_fundo == cnpj_digits,
        QitechReportJob.report_type == "fidc-estoque",
        QitechReportJob.status.in_(
            [QitechJobStatus.WAITING, QitechJobStatus.PROCESSING]
        ),
    )
    return {r[0] for r in (await db.execute(stmt)).all()}


async def find_qitech_gaps_to_heal(
    db: AsyncSession,
    *,
    lookback_days: int,
) -> list[GapToHeal]:
    """Detecta furos a curar em todas (tenant, UA) com QiTech enabled.

    Retorna lista de drifts ja filtrada (sem duplicar com jobs ativos).
    Cap por endpoint = MAX_GAPS_PER_JOB pra nao criar jobs gigantescos
    quando lookback for grande e endpoint estiver muito atrasado.

    Args:
        db: sessao async.
        lookback_days: tamanho da janela de auto-heal em dias corridos.
            Cobertura usa esse N pra calcular start_date = today - N.

    Returns:
        Lista de `GapToHeal`. Vazia se nenhum tenant tem furos ou se
        todos os endpoints com furos ja tem job ativo.
    """
    out: list[GapToHeal] = []

    configs = await list_enabled_configs(
        db,
        SourceType.ADMIN_QITECH,
        Environment.PRODUCTION,
    )
    if not configs:
        return out

    for cfg in configs:
        # Coverage service tem toda a logica de status — reutilizar evita
        # divergencia entre "o que UI mostra como gap" vs "o que reconciler
        # tenta curar".
        cov = await get_source_coverage(
            db,
            source_type=SourceType.ADMIN_QITECH,
            tenant_id=cfg.tenant_id,
            unidade_administrativa_id=cfg.unidade_administrativa_id,
            range_days=lookback_days,
        )

        # Fidc_estoque assincrono: filtra datas com job ativo (POST feito,
        # callback pendente) — evita criar 2o job na QiTech.
        async_active_dates = await _active_async_job_dates_for_fidc_estoque(
            db,
            tenant_id=cfg.tenant_id,
            unidade_administrativa_id=cfg.unidade_administrativa_id,
        )

        for ep in cov.endpoints:
            if not ep.supported:
                continue
            # State machine gate (F3, 2026-05-21): endpoints com
            # `state_machine_enabled=True` no catalogo sao curados pelo
            # `state_machine_dispatcher` — reconciler pula pra nao causar
            # double-fetch.
            if is_state_machine_enabled(SourceType.ADMIN_QITECH, ep.name):
                continue
            retryable_total = (
                ep.count_gap + ep.count_partial + ep.count_not_published
            )
            if retryable_total == 0:
                continue
            # Carrega (data, tolerance_state) — coverage ja calculou pra
            # gente. FURO_DEFINITIVO sai imediatamente: reconciler nao tenta
            # mais sozinho, operador reabre manual via UI.
            gap_candidates: list[tuple[date, PublicationState]] = [
                (d.data, d.tolerance_state)
                for d in ep.days
                if d.status in _RETRYABLE_STATUSES
                and d.tolerance_state is not None
                and d.tolerance_state != PublicationState.FURO_DEFINITIVO
            ]
            if not gap_candidates:
                continue
            gap_dates = [d for d, _ in gap_candidates]

            # Anti-duplicacao do job assincrono (fidc_estoque) — datas com
            # QitechReportJob WAITING/PROCESSING saem do candidato.
            if ep.name == "market.fidc_estoque" and async_active_dates:
                gap_candidates = [
                    (d, st) for (d, st) in gap_candidates if d not in async_active_dates
                ]
                gap_dates = [d for d, _ in gap_candidates]
                if not gap_dates:
                    continue

            # Modulacao de cadencia por estado (2026-05-15): respeita cooldown
            # entre tentativas — ESPERADO sem espera, ATRASADO 4h, SUSPEITO 24h.
            # Evita martelar fonte que ja foi tentada recentemente sem barrar
            # tentativas em estado "recente" (D+1 ainda esperado).
            last_attempt = await _last_attempt_at_by_date(
                db,
                tenant_id=cfg.tenant_id,
                source_type=SourceType.ADMIN_QITECH,
                unidade_administrativa_id=cfg.unidade_administrativa_id,
                endpoint_name=ep.name,
                dates=gap_dates,
            )
            now = datetime.now(UTC)
            due_dates_set = set(
                _dates_due_for_retry(
                    candidates=gap_candidates,
                    last_attempt_by_date=last_attempt,
                    now=now,
                )
            )
            if not due_dates_set:
                continue
            gap_dates = [d for d in gap_dates if d in due_dates_set]

            # Fase 1.5: cap absoluto de tentativas por data (defesa adicional
            # contra estado SUSPEITO que ja foi tentado N+ vezes mesmo
            # respeitando cooldown). Evita martelar fonte morta indefinidamente.
            attempts = await _count_attempts_by_date(
                db,
                tenant_id=cfg.tenant_id,
                source_type=SourceType.ADMIN_QITECH,
                unidade_administrativa_id=cfg.unidade_administrativa_id,
                endpoint_name=ep.name,
                dates=gap_dates,
            )
            stale_dates = {d for d, n in attempts.items() if n >= _MAX_ATTEMPTS_PER_DATE}
            if stale_dates:
                logger.info(
                    "reconciler: skipping %d stale date(s) for %s/%s/%s "
                    "(>= %d attempts)",
                    len(stale_dates),
                    cfg.tenant_id,
                    cfg.unidade_administrativa_id,
                    ep.name,
                    _MAX_ATTEMPTS_PER_DATE,
                )
                gap_dates = [d for d in gap_dates if d not in stale_dates]
            if not gap_dates:
                continue

            # Cap defensivo de tamanho — janela grande + endpoint sem dado
            # historico podia gerar BackfillJob com centenas de datas.
            if len(gap_dates) > _MAX_GAPS_PER_JOB:
                gap_dates = gap_dates[-_MAX_GAPS_PER_JOB:]
                logger.warning(
                    "reconciler: capping retryable for %s/%s/%s at %d "
                    "(was %d, processing most recent)",
                    cfg.tenant_id,
                    cfg.unidade_administrativa_id,
                    ep.name,
                    _MAX_GAPS_PER_JOB,
                    retryable_total,
                )

            already_running = await _has_active_backfill_job(
                db,
                tenant_id=cfg.tenant_id,
                source_type=SourceType.ADMIN_QITECH,
                unidade_administrativa_id=cfg.unidade_administrativa_id,
                endpoint_name=ep.name,
            )
            if already_running:
                continue

            out.append(
                GapToHeal(
                    tenant_id=cfg.tenant_id,
                    unidade_administrativa_id=cfg.unidade_administrativa_id,
                    endpoint_name=ep.name,
                    dates=gap_dates,
                )
            )
    return out


async def _record_reconciler_decision(
    *,
    tenant_id: UUID,
    summary: dict[str, Any],
) -> None:
    """Append-only audit (CLAUDE.md §14.2) — entry por execucao do reconciler.

    Granularidade: 1 entry POR TICK que efetivamente enfileirou algo. Quando
    o tick nao detecta nada, nao gravamos — evita ruido no log.
    """
    async with AsyncSessionLocal() as db:
        db.add(
            DecisionLog(
                tenant_id=tenant_id,
                decision_type=DecisionType.SYNC,
                rule_or_model="qitech_reconciler",
                rule_or_model_version="phase1_v1.0.0",
                inputs_ref={
                    "lookback_days": summary.get("lookback_days"),
                    "phase": "1",
                },
                output=summary,
                explanation="auto-heal gap detection + BackfillJob enqueue",
                triggered_by=RECONCILER_CREATED_BY,
            )
        )
        await db.commit()


async def enqueue_reconciler_jobs(
    gaps: list[GapToHeal],
) -> list[dict[str, Any]]:
    """Cria 1 BackfillJob por gap detectado. Retorna lista de summaries."""
    summaries: list[dict[str, Any]] = []
    if not gaps:
        return summaries

    # Agrega por tenant pra registrar 1 decision_log por tenant impactado.
    by_tenant: dict[UUID, list[dict[str, Any]]] = {}

    for gap in gaps:
        try:
            async with AsyncSessionLocal() as db:
                job = await create_backfill_job(
                    db,
                    tenant_id=gap.tenant_id,
                    source_type=SourceType.ADMIN_QITECH,
                    environment=Environment.PRODUCTION,
                    unidade_administrativa_id=gap.unidade_administrativa_id,
                    endpoint_name=gap.endpoint_name,
                    dates=gap.dates,
                    created_by=RECONCILER_CREATED_BY,
                )
            summary = {
                "job_id": str(job.id),
                "tenant_id": str(gap.tenant_id),
                "ua_id": (
                    str(gap.unidade_administrativa_id)
                    if gap.unidade_administrativa_id
                    else None
                ),
                "endpoint": gap.endpoint_name,
                "dates_count": len(gap.dates),
                "ok": True,
            }
        except Exception as e:
            summary = {
                "job_id": None,
                "tenant_id": str(gap.tenant_id),
                "ua_id": (
                    str(gap.unidade_administrativa_id)
                    if gap.unidade_administrativa_id
                    else None
                ),
                "endpoint": gap.endpoint_name,
                "dates_count": len(gap.dates),
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
            }
            logger.exception(
                "reconciler: failed to enqueue job for %s/%s/%s",
                gap.tenant_id,
                gap.unidade_administrativa_id,
                gap.endpoint_name,
            )
        summaries.append(summary)
        by_tenant.setdefault(gap.tenant_id, []).append(summary)

    # 1 entry de decision_log por tenant — alivia ruido vs 1 por gap.
    for tenant_id, tenant_summaries in by_tenant.items():
        await _record_reconciler_decision(
            tenant_id=tenant_id,
            summary={
                "jobs": tenant_summaries,
                "jobs_count": len(tenant_summaries),
                "jobs_succeeded": sum(1 for s in tenant_summaries if s["ok"]),
                "jobs_failed": sum(1 for s in tenant_summaries if not s["ok"]),
            },
        )
    return summaries


async def run_reconciler_tick() -> dict[str, Any]:
    """Executa um ciclo completo do reconciler (detect + enqueue).

    Chamado pelo APScheduler em `app/scheduler/jobs/reconciler.py`. Tambem
    pode ser disparado manualmente via script pra debug.

    Returns:
        Summary com metricas do tick — usado pra logging + observabilidade
        futura (Fase 3).
    """
    settings = get_settings()
    if not settings.RECONCILER_ENABLED:
        logger.debug("reconciler: disabled via settings, skipping tick")
        return {
            "ok": True,
            "skipped": True,
            "reason": "disabled",
            "lookback_days": settings.RECONCILER_LOOKBACK_DAYS,
        }

    t0 = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        gaps = await find_qitech_gaps_to_heal(
            db,
            lookback_days=settings.RECONCILER_LOOKBACK_DAYS,
        )

    job_summaries = await enqueue_reconciler_jobs(gaps)
    elapsed = (datetime.now(UTC) - t0).total_seconds()

    return {
        "ok": True,
        "skipped": False,
        "lookback_days": settings.RECONCILER_LOOKBACK_DAYS,
        "gaps_detected": len(gaps),
        "jobs_enqueued": sum(1 for s in job_summaries if s["ok"]),
        "jobs_failed": sum(1 for s in job_summaries if not s["ok"]),
        "elapsed_seconds": round(elapsed, 2),
    }


# Candidate set inclui dias em GAP (sem row), PARTIAL (200 com subset
# esperado ausente) e NOT_PUBLISHED (4xx-as-row). Os tres podem evoluir
# no proximo retry: GAP -> 200 quando vendor publicar; PARTIAL ->
# complete quando administradora republicar; NOT_PUBLISHED -> 200
# quando vendor liberar o relatorio. Adicionado em 2026-05-16 pra
# fechar o gap "partial gruda pra sempre" — ver memoria
# project_qitech_response_semantics.
_RETRYABLE_STATUSES = (
    CoverageStatus.GAP,
    CoverageStatus.PARTIAL,
    CoverageStatus.NOT_PUBLISHED,
)


# Cap defensivo por (tenant, ua, endpoint). Janela grande + endpoint sem
# historico nao deve criar BackfillJob com 500 datas — quebraria em retries
# e seguraria fila por horas. 60 ~ 3 meses de dias uteis — suficiente pra
# Fase 1 com lookback default 30.
_MAX_GAPS_PER_JOB: int = 60

# Cap de tentativas por data (Fase 1.5, 2026-05-13). Quando uma data ja foi
# tentada N+ vezes em BackfillJob historicos, o reconciler para de re-tentar.
# Evita martelar fonte morta 1440x/30d na janela default.
#
# 8 escolhido pra cobrir: 1 tentativa inicial automatica (sync_dispatcher) +
# ate ~6 re-tries do reconciler ao longo do dia + 1 margem. Apos isso, dia
# fica "stale" ate Fase 2 (politica de retry com backoff exponencial +
# unrecoverable state) substituir essa logica.
_MAX_ATTEMPTS_PER_DATE: int = 8
