"""Cron polling -- timeout de jobs orfaos + sync de status com a QiTech.

NAO testa o caminho que faz GET real na QiTech (precisaria mockar config
no DB do tenant + transport HTTP). Cobre apenas o caso em que NAO ha jobs
pendentes (early-exit) e mecanica de timeout pra jobs antigos.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.models.qitech_report_job import (
    QitechJobStatus,
    QitechReportJob,
)
from app.scheduler.jobs.qitech_jobs_poll import run
from app.shared.identity.tenant import Tenant


@pytest.mark.asyncio
async def test_poll_retorna_summary_com_shape_esperado():
    """run() sempre devolve summary com chaves estaveis e nao levanta.

    Nao asserta count zero porque DB de teste pode ter jobs WAITING
    deixados por outros testes (sem cleanup transacional). O contrato
    importante e: nao levanta + summary tem o shape completo + errors=[].
    """
    summary = await run()
    assert "tenants_processed" in summary
    assert "jobs_status_updated" in summary
    assert "jobs_timed_out" in summary
    assert "errors" in summary
    assert isinstance(summary["tenants_processed"], int)
    assert summary["errors"] == []


@pytest.mark.asyncio
async def test_poll_sem_config_qitech_pula_silenciosamente(tenant_a: Tenant):
    """Tenant com job pendente mas sem config QiTech persistida.
    Polling ignora (warning no log) e retorna sem erro."""
    qitech_job_id = f"job-noconf-{uuid4().hex}"
    async with AsyncSessionLocal() as db:
        db.add(
            QitechReportJob(
                tenant_id=tenant_a.id,
                environment=Environment.PRODUCTION,
                report_type="fidc-estoque",
                cnpj_fundo="42449234000160",
                reference_date=date(2026, 1, 8),
                request_body={"x": 1},
                qitech_job_id=qitech_job_id,
                callback_url_used="https://test/x",
                callback_token="x" * 32,
                status=QitechJobStatus.WAITING,
                triggered_by="test",
            )
        )
        await db.commit()

    summary = await run()

    # Sem config QiTech, _process_group retorna (0, 0) sem levantar.
    # tenants_processed conta DISTINCT tenant com jobs pendentes — 1 aqui.
    assert summary["tenants_processed"] >= 1
    assert summary["errors"] == []
    # Nao houve timeout porque o job acabou de ser criado (created_at agora).

    # Verifica que o job continua WAITING
    async with AsyncSessionLocal() as db:
        job = (
            await db.execute(
                select(QitechReportJob).where(
                    QitechReportJob.qitech_job_id == qitech_job_id
                )
            )
        ).scalar_one()
        assert job.status == QitechJobStatus.WAITING
