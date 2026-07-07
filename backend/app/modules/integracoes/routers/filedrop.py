"""File Gateway HTTP -- endpoints do Strata Collector (landing zone).

MOTIVO (auth): endpoints autenticados por TOKEN DE AGENTE (maquina), nao por
JWT de usuario — o chamador e um servico no servidor do cliente, sem sessao.
Mesmo precedente dos webhooks (routers/webhooks.py): "cada integracao de
maquina tem sua propria estrategia de validacao". `require_module` nao se
aplica (nao ha usuario); o escopo de tenant vem da credencial validada.

Rotas:
    POST /api/v1/filedrop/upload   multipart (source_label + files[])
    GET  /api/v1/filedrop/ping     heartbeat + politica de coleta
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.integracoes.models.agent_credential import AgentCredential
from app.modules.integracoes.services import filedrop as svc

logger = logging.getLogger("gr.integracoes.filedrop")

router = APIRouter(prefix="/filedrop", tags=["integracoes:filedrop"])


# ---- Auth (token de agente) ------------------------------------------------


async def get_agent_credential(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> AgentCredential:
    """Resolve `Authorization: Bearer strata_agt_...` para a credencial ativa."""
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    credential = await svc.get_active_credential(db, token)
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de agente invalido ou revogado.",
        )
    return credential


# ---- Schemas ---------------------------------------------------------------


class FileReceiptOut(BaseModel):
    nome_arquivo: str
    status: str  # received | duplicate | rejected
    sha256: str | None = None
    motivo: str | None = None


class UploadResponse(BaseModel):
    source_label: str
    received: int
    duplicates: int
    rejected: int
    results: list[FileReceiptOut]


class PingResponse(BaseModel):
    agent_name: str
    watch_config: dict[str, Any]
    server_time: str
    max_file_bytes: int
    max_files_per_request: int


# ---- Endpoints -------------------------------------------------------------


@router.get("/ping", response_model=PingResponse)
async def ping(
    db: Annotated[AsyncSession, Depends(get_db)],
    credential: Annotated[AgentCredential, Depends(get_agent_credential)],
    x_agent_version: Annotated[str | None, Header()] = None,
) -> PingResponse:
    """Heartbeat: marca last_seen_at e devolve a politica de coleta.

    O agente e burro — pastas vigiadas, globs e labels moram na
    `watch_config` do servidor. Trocar politica nao exige mexer na maquina
    do cliente.
    """
    settings = get_settings()
    await svc.touch_heartbeat(db, credential, agent_version=x_agent_version)
    await db.commit()
    return PingResponse(
        agent_name=credential.name,
        watch_config=credential.watch_config or {},
        server_time=datetime.now(UTC).isoformat(),
        max_file_bytes=settings.FILEDROP_MAX_FILE_BYTES,
        max_files_per_request=settings.FILEDROP_MAX_FILES_PER_REQUEST,
    )


@router.post("/upload", response_model=UploadResponse)
async def upload(
    db: Annotated[AsyncSession, Depends(get_db)],
    credential: Annotated[AgentCredential, Depends(get_agent_credential)],
    source_label: Annotated[str, Form(min_length=1, max_length=64)],
    files: Annotated[list[UploadFile], File()],
    x_agent_version: Annotated[str | None, Header()] = None,
) -> UploadResponse:
    """Recebe um batch de arquivos de UM source_label.

    Resposta e por-arquivo (`received | duplicate | rejected`) — o agente
    marca localmente o que ja subiu e nunca precisa reenviar duplicado
    (mas reenviar e inofensivo: dedup por sha).
    """
    settings = get_settings()
    if len(files) > settings.FILEDROP_MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"Batch com {len(files)} arquivos excede o limite de "
                f"{settings.FILEDROP_MAX_FILES_PER_REQUEST} por request."
            ),
        )

    incoming: list[svc.IncomingFile] = []
    for f in files:
        body = await f.read()
        incoming.append(
            svc.IncomingFile(
                nome_arquivo=f.filename or "sem-nome",
                content_type=f.content_type,
                body=body,
            )
        )

    receipts = await svc.receive_files(
        db,
        credential,
        source_label=source_label,
        files=incoming,
        agent_version=x_agent_version,
    )

    counts = {"received": 0, "duplicate": 0, "rejected": 0}
    for r in receipts:
        counts[r.status] += 1
    logger.info(
        "filedrop upload tenant=%s label=%s received=%d dup=%d rejected=%d",
        credential.tenant_id,
        source_label,
        counts["received"],
        counts["duplicate"],
        counts["rejected"],
    )
    return UploadResponse(
        source_label=source_label,
        received=counts["received"],
        duplicates=counts["duplicate"],
        rejected=counts["rejected"],
        results=[
            FileReceiptOut(
                nome_arquivo=r.nome_arquivo,
                status=r.status,
                sha256=r.sha256,
                motivo=r.motivo,
            )
            for r in receipts
        ],
    )
