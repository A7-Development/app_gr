"""Perfil deterministico de liquidacoes (matriz Cedente x sinais).

GET /risco/padroes-liquidacao?janela=30d -> KPIs de perfil + matriz por cedente
(ocorrencias de sinal + mix de canal + alertas de regra dura + recencia + Delta
vs janela anterior).

100% factual: le deteccao_score.features + regra_dura; ignora o score do modelo
(esse vive no painel /risco/cedentes). Read puro sobre silver, tenant-scoped.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.risco.services.padroes_liquidacao import JANELAS, perfil

router = APIRouter(tags=["risco:padroes-liquidacao"])

_GuardRead = Depends(require_module(Module.RISCO, Permission.READ))


class CedentePerfilRow(BaseModel):
    cedente_documento: str
    cedente_nome: str | None
    n_liq: int
    valor: float
    ultima_liq: datetime | None
    n_alerta: int
    n_alerta_conta: int
    n_alerta_multicedente: int
    # Red flags intrinsecos (chaves em `_SINAIS`): conta_cedente, praca_cedente,
    # fora_praca, fora_padrao, multi_sacado.
    sinais: dict[str, int]
    # Canal por segmento oficial Bacen (`_SEGMENTOS`): banco_digital,
    # cooperativa, ip, scd, financeira.
    segmentos: dict[str, int]
    delta_alerta: int | None
    delta_liq: int | None
    cedente_novo: bool


class PerfilKpis(BaseModel):
    valor_total: float
    n_liq_total: int
    n_cedentes: int
    n_alerta_total: int
    n_alerta_anterior: int | None
    pct_conta_cedente: float
    pct_fora_praca: float
    pct_canal_atencao: float


class PadroesLiquidacaoResponse(BaseModel):
    janela: str
    inicio: str | None
    fim: str
    kpis: PerfilKpis
    cedentes: list[CedentePerfilRow]


@router.get("/padroes-liquidacao", response_model=PadroesLiquidacaoResponse)
async def get_padroes_liquidacao(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    janela: Annotated[str, Query(pattern="^(7d|15d|30d|90d|12m|tudo)$")] = "30d",
    _: None = _GuardRead,
) -> PadroesLiquidacaoResponse:
    if janela not in JANELAS:
        janela = "30d"
    data = await perfil(db, principal.tenant_id, janela=janela)
    return PadroesLiquidacaoResponse(**data)
