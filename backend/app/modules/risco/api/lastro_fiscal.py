"""Lastro fiscal da carteira (F4) -- feed de ocorrencias SEFAZ + resumo.

GET /risco/lastro-fiscal/resumo       -> KPIs da carteira vigiada
GET /risco/lastro-fiscal/ocorrencias  -> feed paginado (evento x nota,
                                         titulos abertos agregados)

Read puro sobre warehouse (silver SERPRO + ponte titulo<->nota), tenant-
scoped. Ciencia mora aqui (modulo risco); o maquinario de coleta vive em
integracoes (fronteira 2026-07-11).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.risco.services.lastro_fiscal import (
    SEVERIDADES,
    listar_ocorrencias,
    resumo,
)

router = APIRouter(prefix="/lastro-fiscal", tags=["risco:lastro-fiscal"])

_GuardRead = Depends(require_module(Module.RISCO, Permission.READ))


class ResumoLastroFiscal(BaseModel):
    notas_vigiadas: int
    notas_mortas: int
    notas_mortas_saldo: float
    sem_manifestacao: int
    sem_manifestacao_saldo: float
    sem_manifestacao_dias: int
    confirmadas: int
    pct_confirmada: float


class OcorrenciaOut(BaseModel):
    evento_id: UUID
    chave_acesso: str
    codigo: str
    severidade: str
    tp_evento: int
    desc_evento: str | None
    justificativa: str | None
    dh_evento: datetime | None
    autor_documento: str | None
    pos_cessao: bool | None
    nfe_numero: int | None
    emitente_nome: str | None
    emitente_documento: str | None
    destinatario_nome: str | None
    valor_nota: float | None
    situacao_nota: str | None
    qtd_titulos_abertos: int
    saldo_devedor_aberto: float
    primeira_efetivacao: datetime | None


class OcorrenciasPage(BaseModel):
    total: int
    page: int
    page_size: int
    ocorrencias: list[OcorrenciaOut]


@router.get(
    "/resumo", response_model=ResumoLastroFiscal, dependencies=[_GuardRead]
)
async def get_resumo(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ResumoLastroFiscal:
    dados = await resumo(db, principal.tenant_id)
    return ResumoLastroFiscal(**dados)


@router.get(
    "/ocorrencias", response_model=OcorrenciasPage, dependencies=[_GuardRead]
)
async def get_ocorrencias(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    desde: Annotated[datetime | None, Query()] = None,
    severidade: Annotated[list[str] | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> OcorrenciasPage:
    severidades = [s for s in (severidade or []) if s in SEVERIDADES] or None
    dados = await listar_ocorrencias(
        db,
        principal.tenant_id,
        desde=desde,
        severidades=severidades,
        page=page,
        page_size=page_size,
    )
    return OcorrenciasPage(
        total=dados["total"],
        page=dados["page"],
        page_size=dados["page_size"],
        ocorrencias=[OcorrenciaOut(**asdict(o)) for o in dados["ocorrencias"]],
    )
