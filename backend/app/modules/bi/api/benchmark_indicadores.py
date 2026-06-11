"""BI -> Benchmark: endpoints da cesta de indicadores (Comparador).

GET /bi/benchmark/indicadores?cnpjs=...&cnpjs=...&competencia=YYYY-MM-DD
GET /bi/benchmark/indicadores/competencias

Fonte publica federada cvm_remote (CLAUDE.md sec 13.1) — sem tenant scope,
mas endpoint autenticado + require_module(BI, READ) como todo o modulo.
Aceita CNPJ com ou sem mascara (normaliza p/ formato CVM XX.XXX.XXX/XXXX-XX).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.modules.bi.schemas.benchmark_indicadores import (
    ComparadorIndicadoresResponse,
    CompetenciasDisponiveisResponse,
    IndicadoresFundo,
)
from app.modules.bi.services.benchmark_indicadores import (
    INDICADOR_DIRECAO,
    carregar_universo,
    competencias_disponiveis,
)

router = APIRouter(prefix="/benchmark/indicadores", tags=["bi:benchmark"])

_Guard = Depends(require_module(Module.BI, Permission.READ))

_MAX_FUNDOS = 3


def _cnpj_cvm(raw: str) -> str:
    """Normaliza CNPJ para o formato da CVM (XX.XXX.XXX/XXXX-XX)."""
    d = "".join(ch for ch in raw if ch.isdigit())
    if len(d) != 14:
        raise HTTPException(status_code=422, detail=f"CNPJ invalido: {raw}")
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


@router.get("/competencias", response_model=CompetenciasDisponiveisResponse)
async def listar_competencias(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> CompetenciasDisponiveisResponse:
    """Competencias com informe disponivel (desc)."""
    return CompetenciasDisponiveisResponse(
        competencias=await competencias_disponiveis(db)
    )


@router.get("", response_model=ComparadorIndicadoresResponse)
async def comparador_indicadores(
    db: Annotated[AsyncSession, Depends(get_db)],
    cnpjs: Annotated[list[str], Query(min_length=1, max_length=_MAX_FUNDOS)],
    competencia: date | None = None,
    _: None = _Guard,
) -> ComparadorIndicadoresResponse:
    """Cesta de 17 indicadores de ate 3 fundos + percentis + mediana do universo."""
    if competencia is None:
        disponiveis = await competencias_disponiveis(db, limit=1)
        if not disponiveis:
            raise HTTPException(status_code=404, detail="Sem competencias na base CVM")
        competencia = disponiveis[0]

    universo = await carregar_universo(db, competencia)

    fundos: list[IndicadoresFundo] = []
    nao_encontrados: list[str] = []
    for raw in cnpjs:
        chave = _cnpj_cvm(raw)
        row = universo.fundos.get(chave)
        if row is None:
            nao_encontrados.append(chave)
        else:
            fundos.append(IndicadoresFundo(**row))

    return ComparadorIndicadoresResponse(
        competencia=universo.competencia,
        total_fundos_universo=universo.total_fundos,
        fundos=fundos,
        nao_encontrados=nao_encontrados,
        mediana=universo.medianas,
        direcao=INDICADOR_DIRECAO,
    )
