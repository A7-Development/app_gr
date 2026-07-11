"""Rating deterministico de integridade de liquidacao (leitura).

GET /risco/rating-liquidacao           -> rollup por cedente (grade + score +
                                          cobertura + sinais)
GET /risco/rating-liquidacao/pares     -> pares cedente x sacado de um cedente
                                          (drill da tela)

Read puro sobre `rating_liquidacao` (snapshot recalculado no scheduler apos o
scoring). Tenant-scoped; RISCO/READ.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.risco.models.rating import RatingLiquidacao
from app.modules.risco.services.raio_x_cedente import raio_x

router = APIRouter(tags=["risco:rating-liquidacao"])

_GuardRead = Depends(require_module(Module.RISCO, Permission.READ))


class RatingRow(BaseModel):
    cedente_documento: str
    cedente_nome: str | None
    sacado_documento: str | None
    sacado_nome: str | None
    score: float | None
    grade: str
    tem_critico: bool
    n_eventos_score: int
    n_desfechos: int
    valor_desfechos: float
    cobertura: float
    componentes: dict[str, Any]
    formula_version: str
    calculado_em: datetime


class RatingResponse(BaseModel):
    total: int
    rows: list[RatingRow]


def _to_row(r: RatingLiquidacao) -> RatingRow:
    return RatingRow(
        cedente_documento=r.cedente_documento,
        cedente_nome=r.cedente_nome,
        sacado_documento=r.sacado_documento,
        sacado_nome=r.sacado_nome,
        score=float(r.score) if r.score is not None else None,
        grade=r.grade,
        tem_critico=r.tem_critico,
        n_eventos_score=r.n_eventos_score,
        n_desfechos=r.n_desfechos,
        valor_desfechos=float(r.valor_desfechos),
        cobertura=float(r.cobertura),
        componentes=r.componentes,
        formula_version=r.formula_version,
        calculado_em=r.calculado_em,
    )


@router.get("/rating-liquidacao", response_model=RatingResponse, dependencies=[_GuardRead])
async def listar_cedentes(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RatingResponse:
    """Rollup por cedente (sacado_documento NULL), pior nota primeiro."""
    rows = (
        (
            await db.execute(
                select(RatingLiquidacao)
                .where(
                    RatingLiquidacao.tenant_id == principal.tenant_id,
                    RatingLiquidacao.sacado_documento.is_(None),
                )
                # pior primeiro: critico > score asc (NULL/NC por ultimo)
                .order_by(
                    RatingLiquidacao.tem_critico.desc(),
                    RatingLiquidacao.score.asc().nulls_last(),
                )
            )
        )
        .scalars()
        .all()
    )
    return RatingResponse(total=len(rows), rows=[_to_row(r) for r in rows])


@router.get(
    "/rating-liquidacao/pares", response_model=RatingResponse, dependencies=[_GuardRead]
)
async def listar_pares(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cedente_documento: Annotated[str, Query(min_length=8, max_length=20)],
) -> RatingResponse:
    """Pares cedente x sacado do cedente (drill), pior nota primeiro."""
    rows = (
        (
            await db.execute(
                select(RatingLiquidacao)
                .where(
                    RatingLiquidacao.tenant_id == principal.tenant_id,
                    RatingLiquidacao.cedente_documento == cedente_documento,
                    RatingLiquidacao.sacado_documento.is_not(None),
                )
                .order_by(
                    RatingLiquidacao.tem_critico.desc(),
                    RatingLiquidacao.score.asc().nulls_last(),
                )
            )
        )
        .scalars()
        .all()
    )
    return RatingResponse(total=len(rows), rows=[_to_row(r) for r in rows])


@router.get("/rating-liquidacao/cedente/{cedente_documento}", dependencies=[_GuardRead])
async def raio_x_cedente(
    cedente_documento: str,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Raio-X do cedente: header + filme mensal + sinais + agencias. 404 se
    o cedente nao tem rating calculado."""
    dossie = await raio_x(db, principal.tenant_id, cedente_documento)
    if dossie is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Cedente sem rating calculado.")
    return dossie
