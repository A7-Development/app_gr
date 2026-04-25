"""Receiver HTTP de webhooks externos (callbacks da QiTech, futuros bureaus, etc).

PUBLICO -- sem auth de usuario. Cada webhook tem sua propria estrategia
de validacao da fonte (assinatura, HMAC, IP whitelist, ...).

QiTech /v2/queue/scheduler/report/* (familia FIDC Estoque, Movimentacao, ...):
    - QiTech NAO assina o callback (validado em 2026-04-25).
    - Defesa = HMAC do jobId no `?token=<hex>` da URL.
    - Ao criar o job (POST), tambem mandamos `callbackUrl` com o token
      ja embutido. Quando o callback chega, validamos.

Schema do callback recebido:
    POST /api/v1/integracoes/webhooks/qitech/job-callback?token=<hmac>
    Headers: content-type: application/json (sem auth da QiTech)
    Body: {
      "webhookId": int,
      "jobId": str,
      "eventType": str,           # camelCase: "fidcEstoque", ...
      "data": {"fileLink": str}
    }

Resposta: 200 OK sempre que processamento for aceito (mesmo que assincrono
ou idempotente). 401 se token invalido. 404 se jobId nao existir. Em todos
os outros erros, 500.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.integracoes.adapters.admin.qitech.report_jobs import (
    process_fidc_estoque_callback,
    verify_callback_token,
)

logger = logging.getLogger("gr.integracoes.webhooks")

router = APIRouter(prefix="/webhooks", tags=["integracoes:webhooks"])


# ---- Schemas --------------------------------------------------------------


class _QitechCallbackData(BaseModel):
    """Payload do campo `data` do callback. Pode ter campos adicionais
    em outras familias de relatorio — por isso `extra='allow'`.

    Atributos snake_case localmente, alias pro camelCase da QiTech.
    """

    file_link: str | None = Field(default=None, alias="fileLink")

    model_config = {"extra": "allow", "populate_by_name": True}


class QitechJobCallbackBody(BaseModel):
    """Schema do body do callback /v2/queue/scheduler/report/*.

    Validado contra payload real recebido em 2026-04-25 do job 908aaf59.
    """

    webhook_id: int | None = Field(default=None, alias="webhookId")
    job_id: str = Field(min_length=1, alias="jobId")
    event_type: str = Field(min_length=1, alias="eventType")
    data: _QitechCallbackData

    model_config = {"extra": "allow", "populate_by_name": True}


class QitechJobCallbackResponse(BaseModel):
    """Resposta sucinta — webhook nao precisa expor detalhes internos."""

    accepted: bool
    job_id: str | None = None
    idempotent: bool = False


# ---- Handlers -------------------------------------------------------------


# eventType da QiTech (camelCase) -> handler async(db, body) -> result.
# Atualmente so fidcEstoque tem mapper canonico; outros tipos vao bater
# aqui no futuro e a gente roteia pro processor certo.
_HANDLERS = {
    "fidcEstoque": process_fidc_estoque_callback,
}


async def _dispatch_qitech_callback(
    db: AsyncSession, body: QitechJobCallbackBody
) -> dict[str, Any]:
    """Roteia o callback pro processor especifico baseado em event_type."""
    handler = _HANDLERS.get(body.event_type)
    if handler is None:
        # eventType nao conhecido — registramos e devolvemos accepted=true
        # mesmo assim (a QiTech nao precisa saber que ainda nao temos mapper).
        logger.warning(
            "qitech callback eventType nao mapeado: %s (jobId=%s)",
            body.event_type,
            body.job_id,
        )
        return {"ok": True, "idempotent": False, "reason": "unmapped_event_type"}

    return await handler(
        db=db,
        qitech_job_id=body.job_id,
        file_link=body.data.file_link or "",
        qitech_webhook_id=body.webhook_id,
    )


# ---- Endpoint -------------------------------------------------------------


@router.post(
    "/qitech/job-callback",
    response_model=QitechJobCallbackResponse,
    status_code=status.HTTP_200_OK,
)
async def qitech_job_callback(
    body: QitechJobCallbackBody,
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str, Query()] = "",
) -> QitechJobCallbackResponse:
    """Receiver de callbacks dos relatorios assincronos QiTech.

    PUBLICO (sem auth de usuario). Validacao por:
    1. HMAC token na query string contra `QITECH_WEBHOOK_SECRET` + jobId.
    2. Lookup do jobId no DB (via processor) — se nao existir, 404.
    3. Idempotencia (processor nao re-baixa se ja processado).

    NAO processa em background no MVP — espera a entrega completar para
    devolver 200/erro. Decisao: download CSV + bulk upsert e o-(N) com N
    pequeno (milhares de linhas). Latencia esperada < 30s, dentro do
    timeout default da QiTech. Se virar problema, mover para BackgroundTasks.
    """
    # 1. Anti-spoof
    if not verify_callback_token(qitech_job_id=body.job_id, token=token):
        logger.warning(
            "qitech callback token invalido jobId=%s eventType=%s",
            body.job_id,
            body.event_type,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token invalido"
        )

    # 2. Roteamento + processamento
    try:
        result = await _dispatch_qitech_callback(db, body)
    except ValueError as e:
        # jobId desconhecido (orfao ou spoof que passou no token check —
        # acontece em DEV quando token nao esta configurado).
        logger.warning(
            "qitech callback jobId desconhecido: %s eventType=%s err=%s",
            body.job_id,
            body.event_type,
            e,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    except Exception as e:
        logger.exception(
            "qitech callback erro inesperado jobId=%s eventType=%s",
            body.job_id,
            body.event_type,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__}",
        ) from e

    # background nao usado por enquanto (parametro existe pra futuro async).
    _ = background

    return QitechJobCallbackResponse(
        accepted=bool(result.get("ok", False)),
        job_id=result.get("job_id"),
        idempotent=bool(result.get("idempotent", False)),
    )
