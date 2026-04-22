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
    BenchmarkAdmins,
    BenchmarkCondom,
    BenchmarkEvolucao,
    BenchmarkResumo,
    FundosLista,
    PDDDistribuicao,
)
from app.modules.bi.schemas.benchmark_comparativo import ComparativoResponse
from app.modules.bi.schemas.common import BIResponse
from app.modules.bi.schemas.fundo import FichaFundo
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


def _parse_periodo_yyyymm(
    value: str | None, field_name: str
) -> date | None:
    if value is None:
        return None
    year, month = value.split("-")
    return date(int(year), int(month), 1)


class BenchmarkRangeFilter:
    """Dependency que encapsula filtros de range + tipo_fundo + exclusivos.

    Ausencia de `periodo_inicio`/`periodo_fim` deixa o service decidir o
    fallback (ultimos 12m da ultima competencia disponivel).
    """

    def __init__(
        self,
        periodo_inicio: Annotated[
            str | None,
            Query(
                alias="periodo_inicio",
                description="Inicio do range (YYYY-MM). Primeiro dia do mes.",
                pattern=r"^\d{4}-\d{2}$",
            ),
        ] = None,
        periodo_fim: Annotated[
            str | None,
            Query(
                alias="periodo_fim",
                description="Fim do range (YYYY-MM). Primeiro dia do mes.",
                pattern=r"^\d{4}-\d{2}$",
            ),
        ] = None,
        tipo_fundo: Annotated[
            list[str] | None,
            Query(
                alias="tipo_fundo",
                description=(
                    "Filtro opcional por `tab_i.tp_fundo_classe` — ex.: "
                    "'Fundo', 'Classe'. Repita o parametro para incluir "
                    "mais de um valor."
                ),
            ),
        ] = None,
        incluir_exclusivos: Annotated[
            bool,
            Query(
                alias="incluir_exclusivos",
                description=(
                    "Quando false (default), exclui fundos exclusivos "
                    "(`fundo_exclusivo='S'`) do universo agregado."
                ),
            ),
        ] = False,
    ) -> None:
        self.periodo_inicio = _parse_periodo_yyyymm(periodo_inicio, "periodo_inicio")
        self.periodo_fim = _parse_periodo_yyyymm(periodo_fim, "periodo_fim")
        self.tipo_fundo = tipo_fundo or None
        self.incluir_exclusivos = incluir_exclusivos


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
    flt: Annotated[BenchmarkRangeFilter, Depends(BenchmarkRangeFilter)],
    _: None = _Guard,
) -> BIResponse[BenchmarkEvolucao]:
    """L3 Evolucao - series temporais agregadas do mercado.

    Aceita `periodo_inicio`/`periodo_fim` (YYYY-MM). Default: ultimos 12m da
    ultima competencia disponivel. Filtros `tipo_fundo` e `incluir_exclusivos`
    sao aplicados na agregacao.
    """
    data, prov = await svc.get_evolucao(
        db,
        periodo_inicio=flt.periodo_inicio,
        periodo_fim=flt.periodo_fim,
        tipo_fundo=flt.tipo_fundo,
        incluir_exclusivos=flt.incluir_exclusivos,
    )
    return BIResponse(data=data, provenance=prov)


@router.get("/admins", response_model=BIResponse[BenchmarkAdmins])
async def admins(
    db: Annotated[AsyncSession, Depends(get_db)],
    flt: Annotated[BenchmarkRangeFilter, Depends(BenchmarkRangeFilter)],
    _: None = _Guard,
) -> BIResponse[BenchmarkAdmins]:
    """Top 10 administradoras por quantidade de fundos e por PL sob administracao.

    Ranking e sempre snapshot na competencia-fim do range (ou ultima
    disponivel). `periodo_inicio` e ignorado — mantem o range apenas por
    consistencia de UI.
    """
    data, prov = await svc.get_admins(
        db,
        periodo_fim=flt.periodo_fim,
        tipo_fundo=flt.tipo_fundo,
        incluir_exclusivos=flt.incluir_exclusivos,
    )
    return BIResponse(data=data, provenance=prov)


@router.get("/condom", response_model=BIResponse[BenchmarkCondom])
async def condom(
    db: Annotated[AsyncSession, Depends(get_db)],
    flt: Annotated[BenchmarkRangeFilter, Depends(BenchmarkRangeFilter)],
    _: None = _Guard,
) -> BIResponse[BenchmarkCondom]:
    """Distribuicao Aberto/Fechado do mercado — snapshot + serie mensal.

    Fundos com `condom` fora de ('ABERTO','FECHADO') sao ignorados. O
    snapshot e tirado da `periodo_fim` (ultima competencia do range).
    """
    data, prov = await svc.get_condom(
        db,
        periodo_inicio=flt.periodo_inicio,
        periodo_fim=flt.periodo_fim,
        tipo_fundo=flt.tipo_fundo,
        incluir_exclusivos=flt.incluir_exclusivos,
    )
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


@router.get("/fundo/{cnpj}", response_model=BIResponse[FichaFundo])
async def fundo(
    db: Annotated[AsyncSession, Depends(get_db)],
    cnpj: str,
    meses: Annotated[
        int,
        Query(ge=3, le=120, description="Meses das series (default 24)"),
    ] = 24,
    _: None = _Guard,
) -> BIResponse[FichaFundo]:
    """Ficha do fundo -- snapshot + series ~24m. Dados publicos CVM FIDC."""
    digits = re.sub(r"\D", "", cnpj)
    if not _CNPJ_DIGITS_RE.match(digits):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"CNPJ invalido (14 digitos obrigatorios): {cnpj!r}",
        )
    try:
        data, prov = await svc.get_fundo(db, digits, meses=meses)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
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
