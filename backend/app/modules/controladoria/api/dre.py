"""Controladoria · DRE -- endpoints.

Pipeline upstream (CLAUDE.md §13.2):
  Bitfin UNLTD_<X> -> bronze wh_bitfin_raw_dre (3 tipo_origem)
                  -> classifier (wh_dre_classification_rule)
                  -> silver wh_dre_mensal
                  -> este service le aqui (silver-only, §13.2.1)

Auth: require_module(CONTROLADORIA, READ). Tenant scope sempre via
`principal.tenant_id`. Filtros globais aplicados via `_apply_filters`
em todos endpoints (CLAUDE.md §7.2).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.controladoria.schemas.dre import (
    DreBreakdownResponse,
    DreDimensao,
    DreFonte,
    DreFornecedoresResponse,
    DrePivotResponse,
    DreReceitaNaturezaResponse,
)
from app.modules.controladoria.services.dre import (
    compute_breakdown,
    compute_drill_fornecedores,
    compute_pivot,
    compute_receita_por_natureza,
    listar_competencias,
)

router = APIRouter(prefix="/dre", tags=["controladoria:dre"])

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))


@router.get("/competencias-disponiveis", response_model=list[date])
async def competencias_disponiveis(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[
        int | None,
        Query(description="UnidadeAdministrativa.Id do Bitfin (opcional)"),
    ] = None,
    produto_id: Annotated[int | None, Query(description="Produto Bitfin (opcional)")] = None,
    fonte: Annotated[
        DreFonte | None,
        Query(description="DRE_OPERACIONAL | CONTAS_A_PAGAR | COMISSAO"),
    ] = None,
    _: None = _Guard,
) -> list[date]:
    """Lista as competencias (1o dia do mes) com dado em wh_dre_mensal.

    Usado pelo seletor de periodo no frontend pra restringir o range
    selecionavel ao que ja foi ingerido.
    """
    return await listar_competencias(
        db,
        tenant_id=principal.tenant_id,
        fundo_id=fundo_id,
        produto_id=produto_id,
        fonte=fonte,
    )


@router.get("/pivot", response_model=DrePivotResponse)
async def pivot(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia_de: Annotated[
        date,
        Query(description="Primeira competencia (1o dia do mes) inclusive."),
    ],
    competencia_ate: Annotated[
        date,
        Query(description="Ultima competencia (1o dia do mes) inclusive."),
    ],
    fundo_id: Annotated[
        int | None,
        Query(description="UnidadeAdministrativa.Id do Bitfin (opcional)"),
    ] = None,
    produto_id: Annotated[int | None, Query(description="Produto Bitfin (opcional)")] = None,
    fonte: Annotated[
        DreFonte | None,
        Query(description="DRE_OPERACIONAL | CONTAS_A_PAGAR | COMISSAO"),
    ] = None,
    _: None = _Guard,
) -> DrePivotResponse:
    """DRE hierarquica (grupo > subgrupo > descricao) pivotada por competencia.

    Cada no carrega `valores[]` por competencia (zero quando vazio, todos os
    meses do periodo estao presentes) + `totais` agregado no periodo inteiro.

    Frontend renderiza como DataTable expandivel com `getSubRows`.
    """
    if competencia_ate < competencia_de:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="competencia_ate deve ser maior ou igual a competencia_de",
        )
    return await compute_pivot(
        db,
        tenant_id=principal.tenant_id,
        competencia_de=competencia_de,
        competencia_ate=competencia_ate,
        fundo_id=fundo_id,
        produto_id=produto_id,
        fonte=fonte,
    )


@router.get("/receita-por-natureza", response_model=DreReceitaNaturezaResponse)
async def receita_por_natureza(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia_de: Annotated[
        date, Query(description="Primeira competencia (1o dia do mes) inclusive.")
    ],
    competencia_ate: Annotated[
        date, Query(description="Ultima competencia (1o dia do mes) inclusive.")
    ],
    fundo_id: Annotated[
        int | None,
        Query(description="UnidadeAdministrativa.Id do Bitfin (opcional)"),
    ] = None,
    produto_id: Annotated[int | None, Query(description="Produto Bitfin (opcional)")] = None,
    _: None = _Guard,
) -> DreReceitaNaturezaResponse:
    """Receita operacional por NATUREZA (Desagio/Tarifa/Multa/Juros/Ad
    Valorem/Imposto) x competencia, com drill ate o tipo (descricao).

    Receita = SO `receita` (total_apurado) de RECEITA_OPERACIONAL. Naturezas
    ancoradas no catalogo Bitfin (wh_bitfin_dre_natureza_rule).
    """
    if competencia_ate < competencia_de:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="competencia_ate deve ser maior ou igual a competencia_de",
        )
    return await compute_receita_por_natureza(
        db,
        tenant_id=principal.tenant_id,
        competencia_de=competencia_de,
        competencia_ate=competencia_ate,
        fundo_id=fundo_id,
        produto_id=produto_id,
    )


@router.get("/breakdown", response_model=DreBreakdownResponse)
async def breakdown(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    competencia: Annotated[date, Query(description="Competencia (1o dia do mes).")],
    dim: Annotated[
        DreDimensao, Query(description="natureza | cedente | produto | subgrupo")
    ],
    fundo_id: Annotated[int | None, Query(description="UnidadeAdministrativa.Id Bitfin")] = None,
    produto_id: Annotated[int | None, Query()] = None,
    entidade_id: Annotated[int | None, Query(description="Drill: filtra um cedente")] = None,
    natureza: Annotated[str | None, Query(description="Drill: filtra uma natureza")] = None,
    subgrupo: Annotated[str | None, Query(description="Drill: filtra um subgrupo")] = None,
    _: None = _Guard,
) -> DreBreakdownResponse:
    """Receita operacional de UM mes agregada por `dim` (natureza/cedente/
    produto/subgrupo), com receita/custo/resultado. Filtros `entidade_id`/
    `natureza`/`subgrupo` permitem DRILL (cruzar dimensoes)."""
    return await compute_breakdown(
        db,
        tenant_id=principal.tenant_id,
        competencia=competencia,
        dim=dim,
        fundo_id=fundo_id,
        produto_id=produto_id,
        entidade_id=entidade_id,
        natureza=natureza,
        subgrupo=subgrupo,
    )


@router.get("/drill/fornecedores", response_model=DreFornecedoresResponse)
async def drill_fornecedores(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    grupo_dre: Annotated[str, Query(description="Nome do grupo DRE (obrigatorio)")],
    competencia_de: Annotated[date, Query()],
    competencia_ate: Annotated[date, Query()],
    subgrupo: Annotated[str | None, Query(description="Refina o corte (opcional)")] = None,
    descricao: Annotated[str | None, Query(description="Refina o corte (opcional)")] = None,
    fundo_id: Annotated[int | None, Query()] = None,
    produto_id: Annotated[int | None, Query()] = None,
    fonte: Annotated[
        DreFonte | None,
        Query(description="DRE_OPERACIONAL | CONTAS_A_PAGAR | COMISSAO"),
    ] = None,
    top: Annotated[
        int,
        Query(ge=1, le=200, description="Limite de fornecedores retornados"),
    ] = 20,
    _: None = _Guard,
) -> DreFornecedoresResponse:
    """Top N fornecedores em um corte da DRE.

    Ordenado por `abs(resultado)` desc -- captura fornecedores grandes
    independente do sinal. Resposta inclui `total_fornecedores` (count antes
    do limit) pra UI sinalizar truncagem.
    """
    if competencia_ate < competencia_de:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="competencia_ate deve ser maior ou igual a competencia_de",
        )
    return await compute_drill_fornecedores(
        db,
        tenant_id=principal.tenant_id,
        grupo_dre=grupo_dre,
        subgrupo=subgrupo,
        descricao=descricao,
        competencia_de=competencia_de,
        competencia_ate=competencia_ate,
        fundo_id=fundo_id,
        produto_id=produto_id,
        fonte=fonte,
        top=top,
    )
