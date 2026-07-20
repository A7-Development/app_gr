"""BI -> Benchmark: endpoints da cesta de indicadores (Comparador).

GET /bi/benchmark/indicadores?cnpjs=...&cnpjs=...&competencia=YYYY-MM-DD
GET /bi/benchmark/indicadores/competencias

Fonte publica federada cvm_remote (CLAUDE.md sec 13.1) — sem tenant scope,
mas endpoint autenticado + require_module(BI, READ) como todo o modulo.
Aceita CNPJ com ou sem mascara (normaliza p/ formato CVM XX.XXX.XXX/XXXX-XX).
"""

from __future__ import annotations

import asyncio
import logging
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
    variacao_pl,
)

router = APIRouter(prefix="/benchmark/indicadores", tags=["bi:benchmark"])

logger = logging.getLogger(__name__)

_Guard = Depends(require_module(Module.BI, Permission.READ))

# Teto de fundos no Comparador. Subiu de 3 -> 10 em 2026-07-20 (pedido do
# Ricardo). O custo por fundo extra e marginal: o caro e montar o universo da
# competencia (~4k fundos via FDW), que ja e cacheado e independe de quantos
# fundos vieram na request. O par no frontend e `MAX_FUNDOS` em
# `(app)/bi/comparador/page.tsx` — os dois tem que andar juntos.
_MAX_FUNDOS = 10

# Warm-up do cache do universo (referencia forte p/ evitar GC da task).
_WARMING: set[asyncio.Task] = set()


def _warm_universo(competencia: date) -> None:
    """Aquece o cache do universo em background (sessao DB propria).

    Disparado pelo GET /competencias — que a pagina chama ANTES de o usuario
    escolher fundos. Assim a 1a comparacao da competencia corrente nao paga o
    calculo do universo (~4k fundos via FDW) na frente do usuario.
    """

    async def _run() -> None:
        from app.core.database import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                await carregar_universo(db, competencia)
        except Exception:
            logger.warning("warm-up do universo de indicadores falhou", exc_info=True)

    task = asyncio.create_task(_run())
    _WARMING.add(task)
    task.add_done_callback(_WARMING.discard)


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
    """Competencias com informe disponivel (desc). Aquece o cache da ultima."""
    competencias = await competencias_disponiveis(db)
    if competencias:
        _warm_universo(competencias[0])
    return CompetenciasDisponiveisResponse(competencias=competencias)


@router.get("", response_model=ComparadorIndicadoresResponse)
async def comparador_indicadores(
    db: Annotated[AsyncSession, Depends(get_db)],
    cnpjs: Annotated[list[str], Query(min_length=1, max_length=_MAX_FUNDOS)],
    competencia: date | None = None,
    _: None = _Guard,
) -> ComparadorIndicadoresResponse:
    """Cesta de 17 indicadores de ate 10 fundos + percentis + mediana do universo."""
    if competencia is None:
        disponiveis = await competencias_disponiveis(db, limit=1)
        if not disponiveis:
            raise HTTPException(status_code=404, detail="Sem competencias na base CVM")
        competencia = disponiveis[0]

    universo = await carregar_universo(db, competencia)

    chaves = [_cnpj_cvm(raw) for raw in cnpjs]
    # Variacao do PL: consulta o PL da competencia anterior SO destes fundos
    # (<= 10) — barato. Nao monta universo de 2 competencias porque esta linha
    # nao tem percentil.
    comp_anterior, variacoes = await variacao_pl(db, competencia, chaves, universo)

    fundos: list[IndicadoresFundo] = []
    nao_encontrados: list[str] = []
    for chave in chaves:
        row = universo.fundos.get(chave)
        if row is None:
            nao_encontrados.append(chave)
            continue
        var = variacoes.get(chave)
        fundos.append(
            IndicadoresFundo(
                **row,
                pl_anterior=var.pl_anterior if var else None,
                var_pl_pct=var.var_pl_pct if var else None,
            )
        )

    return ComparadorIndicadoresResponse(
        competencia=universo.competencia,
        competencia_anterior=comp_anterior,
        total_fundos_universo=universo.total_fundos,
        fundos=fundos,
        nao_encontrados=nao_encontrados,
        mediana=universo.medianas,
        composicao_mediana=universo.composicao_mediana,
        direcao=INDICADOR_DIRECAO,
    )
