"""BI - endpoints da L2 Benchmark (CVM FIDC - dados publicos via postgres_fdw).

Todos os endpoints:
  - exigem `require_module(Module.BI, Permission.READ)` (CLAUDE.md 12.3)
  - NAO escopam por tenant_id (dado publico, CLAUDE.md 13.1)
  - aceitam `competencia` opcional; quando ausente, usam a ultima disponivel
  - retornam `BIResponse[<Data>]` com proveniencia `source_type='public:cvm_fidc'`

Pre-requisito: ponte FDW configurada no gr_db (schema `cvm_remote.*`).
Ver `docs/integracao-cvm-fidc.md` Parte 4.
"""

import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.modules.bi.schemas.benchmark import (
    BenchmarkEvolucao,
    BenchmarkResumo,
    FundosLista,
    PDDDistribuicao,
)
from app.modules.bi.schemas.benchmark_comparativo import ComparativoResponse
from app.modules.bi.schemas.common import BIResponse
from app.modules.bi.services import benchmark as svc

router = APIRouter(prefix="/benchmark", tags=["bi:benchmark"])

# Dependency composta: autoriza o modulo BI em leitura.
_Guard = Depends(require_module(Module.BI, Permission.READ))


def _parse_competencia(
    competencia: Annotated[
        str | None,
        Query(
            description=(
                "Competencia no formato YYYY-MM (ex.: '2026-03'). "
                "Quando omitida, usa a ultima competencia disponivel."
            ),
            pattern=r"^\d{4}-\d{2}$",
        ),
    ] = None,
) -> date | None:
    """Dependency que converte '2026-03' -> date(2026, 3, 1).

    Retorna None quando o query param nao foi passado - o service
    decide o fallback (ultima competencia).
    """
    if competencia is None:
        return None
    year, month = competencia.split("-")
    return date(int(year), int(month), 1)


@router.get("/resumo", response_model=BIResponse[BenchmarkResumo])
async def resumo(
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia: Annotated[date | None, Depends(_parse_competencia)],
    _: None = _Guard,
) -> BIResponse[BenchmarkResumo]:
    """KPIs agregados do mercado FIDC na competencia selecionada (ou ultima)."""
    data, prov = await svc.get_resumo(db, competencia)
    return BIResponse(data=data, provenance=prov)


@router.get("/pdd", response_model=BIResponse[PDDDistribuicao])
async def pdd(
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia: Annotated[date | None, Depends(_parse_competencia)],
    _: None = _Guard,
) -> BIResponse[PDDDistribuicao]:
    """L3 PDD - histograma de %PDD + top fundos por PDD na competencia."""
    data, prov = await svc.get_pdd(db, competencia)
    return BIResponse(data=data, provenance=prov)


@router.get("/evolucao", response_model=BIResponse[BenchmarkEvolucao])
async def evolucao(
    db: Annotated[AsyncSession, Depends(get_db)],
    meses: Annotated[
        int,
        Query(ge=3, le=120, description="Quantidade de competencias mais recentes"),
    ] = 24,
    _: None = _Guard,
) -> BIResponse[BenchmarkEvolucao]:
    """L3 Evolucao - series temporais agregadas do mercado."""
    data, prov = await svc.get_evolucao(db, meses=meses)
    return BIResponse(data=data, provenance=prov)


_CNPJ_DIGITS_RE = re.compile(r"^\d{14}$")


@router.get("/comparativo", response_model=BIResponse[ComparativoResponse])
async def comparativo(
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia: Annotated[date | None, Depends(_parse_competencia)],
    cnpjs: Annotated[
        list[str],
        Query(
            min_length=2,
            max_length=5,
            description=(
                "CNPJs digits-only (14 digitos) -- repita o parametro para cada "
                "fundo. Entre 2 e 5 fundos."
            ),
        ),
    ],
    meses: Annotated[
        int,
        Query(ge=3, le=120, description="Meses das series evolutivas"),
    ] = 24,
    _: None = _Guard,
) -> BIResponse[ComparativoResponse]:
    """L3 Comparativo -- confronta 2..5 fundos em indicadores, series e composicao."""
    # Pydantic/FastAPI nao aplica `pattern` num `list[str]` -- validacao item-a-item aqui.
    for c in cnpjs:
        if not _CNPJ_DIGITS_RE.match(c):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"CNPJ invalido (precisa ter 14 digitos): {c!r}",
            )
    data, prov = await svc.get_comparativo(db, cnpjs, competencia, meses=meses)
    return BIResponse(data=data, provenance=prov)


@router.get("/fundos", response_model=BIResponse[FundosLista])
async def fundos(
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia: Annotated[date | None, Depends(_parse_competencia)],
    busca: Annotated[
        str | None,
        Query(
            max_length=100,
            description=(
                "Filtro por nome (denominacao social) ou CNPJ. ILIKE "
                "parcial em ambos os campos."
            ),
        ),
    ] = None,
    _: None = _Guard,
) -> BIResponse[FundosLista]:
    """L3 Fundos - top N fundos por PL na competencia (sem paginacao no MVP)."""
    data, prov = await svc.get_fundos(db, competencia, busca=busca)
    return BIResponse(data=data, provenance=prov)
