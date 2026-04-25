"""Endpoints REST pra relatorios assincronos QiTech.

Familia /v2/queue/scheduler/report/* — POST cria job, callback traz arquivo.
Aqui expomos:

    POST /integracoes/qitech/jobs/fidc-estoque/dispatch
        -> dispara request_fidc_estoque_report (cria job no DB, posta na QiTech)
    GET  /integracoes/qitech/jobs
        -> lista jobs do tenant (status, fileLink, etc) -- pra UI exibir historico

Auth: require_module(Module.INTEGRACOES, Permission.WRITE/READ).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Environment, Module, Permission, SourceType
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.errors import (
    QiTechAdapterError,
    QiTechHttpError,
)
from app.modules.integracoes.adapters.admin.qitech.report_jobs import (
    request_fidc_estoque_report,
)
from app.modules.integracoes.models.qitech_report_job import (
    QitechJobStatus,
    QitechReportJob,
)
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
)

router = APIRouter(prefix="/qitech/jobs", tags=["integracoes:qitech-jobs"])

_GuardWrite = Depends(require_module(Module.INTEGRACOES, Permission.WRITE))
_GuardRead = Depends(require_module(Module.INTEGRACOES, Permission.READ))


# ---- Schemas --------------------------------------------------------------


class DispatchFidcEstoquePayload(BaseModel):
    """Body do POST que dispara um relatorio FIDC Estoque."""

    cnpj_fundo: str = Field(min_length=14, max_length=18)
    reference_date: date
    environment: Environment = Environment.PRODUCTION


class JobOut(BaseModel):
    """Representacao da tabela qitech_report_job pra resposta."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_type: str
    cnpj_fundo: str
    reference_date: date
    environment: Environment
    qitech_job_id: str
    qitech_webhook_id: int | None
    status: QitechJobStatus
    result_file_link: str | None
    triggered_by: str
    error_message: str | None
    created_at: Any
    completed_at: Any | None


# ---- Endpoints ------------------------------------------------------------


@router.post(
    "/fidc-estoque/dispatch",
    response_model=JobOut,
    status_code=status.HTTP_201_CREATED,
)
async def dispatch_fidc_estoque(
    payload: DispatchFidcEstoquePayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> JobOut:
    """Dispara POST /v2/queue/scheduler/report/fidc-estoque + cria job no DB.

    QiTech responde imediatamente com {jobId, status:WAITING}; o callback
    chega minutos depois em /webhooks/qitech/job-callback. Ate la, o status
    fica WAITING ou PROCESSING — UI pode pollar GET /jobs pra atualizar.
    """
    # 1. Carrega config QiTech do tenant
    cfg_row = await get_config(
        db,
        principal.tenant_id,
        SourceType.ADMIN_QITECH,
        payload.environment,
    )
    if cfg_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Sem config QiTech para {payload.environment.value}. "
                f"Configure via PUT /integracoes/sources/admin:qitech/config."
            ),
        )
    plain = decrypt_config(cfg_row.config)
    config = QiTechConfig.from_dict(plain)
    if not config.has_credentials():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Config QiTech sem credenciais (client_id / client_secret).",
        )

    # 2. Dispara
    try:
        job = await request_fidc_estoque_report(
            db=db,
            tenant_id=principal.tenant_id,
            environment=payload.environment,
            config=config,
            cnpj_fundo=payload.cnpj_fundo,
            reference_date=payload.reference_date,
            triggered_by=f"user:{principal.user_id}",
        )
    except QiTechHttpError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"QiTech retornou {e.status_code}: {e}",
        ) from e
    except QiTechAdapterError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e

    return JobOut.model_validate(job)


@router.get("", response_model=list[JobOut])
async def list_jobs(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    report_type: Annotated[str | None, Query()] = None,
    job_status: Annotated[QitechJobStatus | None, Query(alias="status")] = None,
    cnpj_fundo: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    _: None = _GuardRead,
) -> list[JobOut]:
    """Lista jobs do tenant ordenados por created_at desc.

    Filtros opcionais: report_type, status, cnpj_fundo. Limite default 50.
    """
    stmt = (
        select(QitechReportJob)
        .where(QitechReportJob.tenant_id == principal.tenant_id)
        .order_by(desc(QitechReportJob.created_at))
        .limit(limit)
    )
    if report_type:
        stmt = stmt.where(QitechReportJob.report_type == report_type)
    if job_status:
        stmt = stmt.where(QitechReportJob.status == job_status)
    if cnpj_fundo:
        stmt = stmt.where(QitechReportJob.cnpj_fundo == cnpj_fundo)

    rows = (await db.execute(stmt)).scalars().all()
    return [JobOut.model_validate(r) for r in rows]


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: Annotated[UUID, Path()],
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardRead,
) -> JobOut:
    """Detalhe de 1 job — incluindo error_message e result_file_link
    (presigned, expira ~24h)."""
    stmt = select(QitechReportJob).where(
        QitechReportJob.tenant_id == principal.tenant_id,
        QitechReportJob.id == job_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job nao encontrado"
        )
    return JobOut.model_validate(row)
