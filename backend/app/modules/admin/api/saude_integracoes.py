"""Painel de Saude das Integracoes (visao de mantenedor do sistema).

GET /admin/saude-integracoes -> uma linha por fonte/job/modelo monitorado,
com ultima execucao + status + frescor. System maintainer only.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.modules.admin.services.saude_integracoes import painel_saude

router = APIRouter(prefix="/saude-integracoes", tags=["admin:saude-integracoes"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


class SaudeItem(BaseModel):
    chave: str
    label: str
    categoria: str
    descricao: str
    cadencia_horas: float
    ultima_execucao: str | None
    status: str  # ok | atrasado | erro | nunca_rodou
    detalhe: str | None
    volume: int | None
    disparado_por: str | None


@router.get("", response_model=list[SaudeItem], dependencies=_GUARD)
async def get_saude(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SaudeItem]:
    rows = await painel_saude(db)
    return [SaudeItem(**r) for r in rows]
