"""Cron poll: sincroniza status local com a QiTech + marca jobs orfaos.

Por que polling alem do callback:
1. Callback pode falhar/perder (rede, restart do receiver, retry esgotado).
2. QiTech NAO faz cleanup do historico — jobs WAITING podem ficar pendentes
   para sempre (validado: job de 2026-01-15 ainda WAITING em 2026-04-25).
3. Operacionalmente queremos saber se um job demorou demais (sintoma de
   problema na fila da QiTech).

Estrategia (a cada N minutos):
1. Buscar jobs do tenant em WAITING/PROCESSING (status nao-terminal).
2. Para cada (tenant, environment, report_type) com jobs pendentes,
   chamar GET /v2/queue/job?reportType=<tipo>&page=0&limit=200.
3. Para cada `taskId` (== qitech_job_id) na resposta, comparar status:
   - SUCCESS local mas tinha WAITING -> ja foi processado por callback, ok
   - WAITING/PROCESSING aqui mas SUCCESS na QiTech -> callback perdido!
     Tentar processar (mas precisamos do fileLink que callback nao gravou
     ainda — TODO: callback obrigatorio pra arquivo, polling so detecta gap)
   - Update status conforme QiTech reportar.
4. Jobs WAITING > TIMEOUT_MINUTES (default 60) -> marca TIMEOUT.

Nao tenta re-disparar nem baixar arquivo; isso e responsabilidade do
callback receiver (que tem o fileLink). Polling e observabilidade.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechHttpError
from app.modules.integracoes.models.qitech_report_job import (
    QitechJobStatus,
    QitechReportJob,
)
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
)

logger = logging.getLogger("gr.integracoes.qitech.polling")

# A cada N minutos. Hoje so suportamos 1 tenant; quando crescer, considerar
# fila com prioridade ou shard por tenant.
INTERVAL_MINUTES: int = 5

# Jobs WAITING > esse tempo viram TIMEOUT (status terminal, nao pollavel).
# 60 min e generoso — sample mostrou que SUCCESS chega em ~10s, mas
# QiTech as vezes deixa orfao por 3+ meses.
TIMEOUT_MINUTES: int = 60

# Status QiTech sao SCREAMING_CASE no GET; a gente normaliza pra enum.
_PENDING_STATUSES = {QitechJobStatus.WAITING, QitechJobStatus.PROCESSING}


async def _list_qitech_jobs(
    config: QiTechConfig, environment: Environment, report_type: str
) -> list[dict[str, Any]]:
    """GET /v2/queue/job?reportType=<tipo>. Pagina default page=0,limit=200."""
    # tenant_id sentinela aqui — o token cache da auth precisa de UUID,
    # mas como esse polling roda por tenant separadamente, usamos o
    # tenant_id real do caller.
    raise NotImplementedError("usar _list_qitech_jobs_for_tenant")


async def _list_qitech_jobs_for_tenant(
    *,
    tenant_id: Any,
    environment: Environment,
    config: QiTechConfig,
    report_type: str,
) -> list[dict[str, Any]]:
    """GET listagem de jobs do report_type pelo tenant especifico."""
    async with build_async_client(
        tenant_id=tenant_id, environment=environment, config=config
    ) as client:
        resp = await client.get(
            "/v2/queue/job",
            params={"reportType": report_type, "page": 0, "limit": 200},
        )
    if resp.status_code >= 400:
        raise QiTechHttpError(
            status_code=resp.status_code, detail=resp.text[:500]
        )
    body = resp.json()
    return list(body.get("jobs") or [])


async def run() -> dict[str, Any]:
    """Tick do polling. Retorna resumo. Nunca levanta — logs cobrem erros."""
    started_at = datetime.now(UTC)
    summary: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "tenants_processed": 0,
        "jobs_pending_initial": 0,
        "jobs_status_updated": 0,
        "jobs_timed_out": 0,
        "errors": [],
    }

    async with AsyncSessionLocal() as db:
        # 1. Levantar (tenant, environment, report_type) com jobs pendentes
        stmt = (
            select(
                QitechReportJob.tenant_id,
                QitechReportJob.environment,
                QitechReportJob.report_type,
            )
            .where(QitechReportJob.status.in_(_PENDING_STATUSES))
            .group_by(
                QitechReportJob.tenant_id,
                QitechReportJob.environment,
                QitechReportJob.report_type,
            )
        )
        groups = (await db.execute(stmt)).all()

    if not groups:
        return summary

    summary["tenants_processed"] = len({g.tenant_id for g in groups})

    timeout_cutoff = datetime.now(UTC) - timedelta(minutes=TIMEOUT_MINUTES)

    for grp in groups:
        try:
            updated, timed_out = await _process_group(
                tenant_id=grp.tenant_id,
                environment=grp.environment,
                report_type=grp.report_type,
                timeout_cutoff=timeout_cutoff,
            )
            summary["jobs_status_updated"] += updated
            summary["jobs_timed_out"] += timed_out
        except Exception as e:
            err = (
                f"tenant={grp.tenant_id} env={grp.environment.value} "
                f"type={grp.report_type}: {type(e).__name__}: {e}"
            )
            logger.exception("polling group falhou: %s", err)
            summary["errors"].append(err)

    summary["elapsed_seconds"] = round(
        (datetime.now(UTC) - started_at).total_seconds(), 2
    )
    return summary


async def _process_group(
    *,
    tenant_id: Any,
    environment: Environment,
    report_type: str,
    timeout_cutoff: datetime,
) -> tuple[int, int]:
    """Processa 1 grupo (tenant, env, report_type).

    Retorna (n_status_atualizado, n_timeout).
    """
    # Carrega config QiTech do tenant
    async with AsyncSessionLocal() as db:
        cfg_row = await get_config(
            db, tenant_id, SourceType.ADMIN_QITECH, environment
        )
    if cfg_row is None:
        logger.warning(
            "tenant=%s sem config QiTech mas tem jobs pendentes — pulando",
            tenant_id,
        )
        return (0, 0)

    plain = decrypt_config(cfg_row.config)
    config = QiTechConfig.from_dict(plain)
    if not config.has_credentials():
        return (0, 0)

    # Lista jobs na QiTech
    qitech_jobs = await _list_qitech_jobs_for_tenant(
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        report_type=report_type,
    )
    qitech_status_by_id: dict[str, str] = {}
    for j in qitech_jobs:
        task_id = j.get("taskId") or j.get("jobId")
        st = j.get("status")
        if task_id and st:
            qitech_status_by_id[str(task_id)] = str(st)

    # Atualiza local
    n_updated = 0
    n_timed_out = 0
    async with AsyncSessionLocal() as db:
        # Busca jobs pendentes locais
        stmt = select(QitechReportJob).where(
            QitechReportJob.tenant_id == tenant_id,
            QitechReportJob.environment == environment,
            QitechReportJob.report_type == report_type,
            QitechReportJob.status.in_(_PENDING_STATUSES),
        )
        local_jobs = (await db.execute(stmt)).scalars().all()

        for job in local_jobs:
            qitech_st = qitech_status_by_id.get(job.qitech_job_id)
            if qitech_st is None:
                # Job nao aparece mais na lista da QiTech.
                # Pode ser: muito antigo (paginacao), CANCELED silente, ou
                # simplesmente fora da janela. Aplicamos timeout se velho.
                if job.created_at and job.created_at < timeout_cutoff:
                    job.status = QitechJobStatus.TIMEOUT
                    job.error_message = (
                        "polling: nao apareceu na lista QiTech, criado ha mais de "
                        f"{TIMEOUT_MINUTES} min"
                    )
                    n_timed_out += 1
                continue

            try:
                new_status = QitechJobStatus(qitech_st)
            except ValueError:
                logger.warning(
                    "QiTech retornou status desconhecido: %s (jobId=%s)",
                    qitech_st,
                    job.qitech_job_id,
                )
                continue

            if new_status != job.status:
                # Caso especial: SUCCESS na QiTech mas local ainda WAITING
                # significa callback nao chegou. Marcamos PROCESSING (nao
                # SUCCESS) porque sem fileLink nao podemos completar — fica
                # claro pra investigacao.
                if new_status == QitechJobStatus.SUCCESS:
                    if not job.result_downloaded_at:
                        # Nao temos fileLink; deixamos como PROCESSING pra
                        # sinalizar "callback perdido — investigar". Erro
                        # registrado pra auditoria.
                        job.status = QitechJobStatus.PROCESSING
                        job.error_message = (
                            "polling: QiTech reporta SUCCESS mas callback "
                            "nao chegou; fileLink desconhecido"
                        )
                        n_updated += 1
                else:
                    job.status = new_status
                    n_updated += 1

            # Timeout: jobs WAITING criados ha muito tempo
            if (
                job.status == QitechJobStatus.WAITING
                and job.created_at
                and job.created_at < timeout_cutoff
            ):
                job.status = QitechJobStatus.TIMEOUT
                job.error_message = (
                    f"polling: WAITING ha mais de {TIMEOUT_MINUTES} min sem callback"
                )
                n_timed_out += 1

        await db.commit()

    return (n_updated, n_timed_out)
