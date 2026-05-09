"""Smoke real do flow FIDC Estoque (assincrono):
1. Cria QitechReportJob a partir do POST 908aaf59 ja disparado
2. Simula callback recebido (file_link real do S3 da QiTech)
3. Valida pipeline completo no DB do tenant a7-credit
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from uuid import UUID

from sqlalchemy import select

import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.report_jobs import (
    process_fidc_estoque_callback,
)
from app.modules.integracoes.models.qitech_report_job import (
    QitechJobStatus,
    QitechReportJob,
)

A7_TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")

# Dados reais do POST que disparamos durante a investigacao do schema:
QITECH_JOB_ID = "908aaf59-d676-4076-a374-a8b2218d08e9-1777142308866"
WEBHOOK_ID = 809341
FILE_LINK = (
    "https://fidc-custodia.s3.amazonaws.com/fidcEstoque-1777142302020.csv"
    "?AWSAccessKeyId=AKIAQZRWSMGJNGVYPIWU&Expires=1778942307"
    "&Signature=nFZHTVcz3%2BJrrULkD5epkepUwRo%3D"
)
REFERENCE_DATE = date(2026, 1, 8)


async def main() -> int:
    # 1. Verifica se o job ja esta no DB; se nao, cria (simula POST registro)
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(
                select(QitechReportJob).where(
                    QitechReportJob.qitech_job_id == QITECH_JOB_ID
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            print(f"[smoke] criando QitechReportJob para {QITECH_JOB_ID[:20]}...")
            job = QitechReportJob(
                tenant_id=A7_TENANT_ID,
                environment=Environment.PRODUCTION,
                report_type="fidc-estoque",
                cnpj_fundo="42449234000160",
                reference_date=REFERENCE_DATE,
                request_body={
                    "callbackUrl": "https://webhook.site/5d37be20-...",
                    "cnpjFundo": "42449234000160",
                    "date": "2026-01-08",
                },
                qitech_job_id=QITECH_JOB_ID,
                callback_url_used="https://webhook.site/5d37be20-...",
                callback_token="manual-smoke",
                status=QitechJobStatus.WAITING,
                triggered_by="smoke_fidc_estoque:cli",
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            local_job_id = job.id
            print(f"[smoke] job criado id={local_job_id}")
        else:
            local_job_id = existing.id
            print(f"[smoke] job ja existia id={local_job_id} status={existing.status}")
            if existing.result_downloaded_at is not None:
                print("[smoke] AVISO: result_downloaded_at preenchido — ja processado")

    # 2. Simula recepcao do callback (chamando process_fidc_estoque_callback)
    print("[smoke] processando callback...")
    print(f"  jobId       = {QITECH_JOB_ID}")
    print(f"  webhookId   = {WEBHOOK_ID}")
    print(f"  fileLink    = {FILE_LINK[:80]}...")
    print()

    async with AsyncSessionLocal() as db:
        result = await process_fidc_estoque_callback(
            db=db,
            local_job_id=local_job_id,
            qitech_job_id=QITECH_JOB_ID,
            file_link=FILE_LINK,
            qitech_webhook_id=WEBHOOK_ID,
        )

    print("=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
