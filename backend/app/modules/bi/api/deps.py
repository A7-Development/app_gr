"""BI module — FastAPI dependencies."""

from datetime import date
from typing import Annotated

from fastapi import Query

from app.modules.bi.schemas.common import BIFilters


def bi_filters(
    periodo_inicio: Annotated[date | None, Query(description="Data inicial (inclusive)")] = None,
    periodo_fim: Annotated[date | None, Query(description="Data final (inclusive)")] = None,
    # Multi-valor: FastAPI aceita `?produto_sigla=FAT&produto_sigla=CMS` quando o
    # tipo e list[str]. Ver template-dashboard do Tremor — filtro visual e multi.
    produto_sigla: Annotated[
        list[str] | None,
        Query(description="Siglas de produto (ex.: FAT, CMS). Repita o param para multi."),
    ] = None,
    ua_id: Annotated[
        list[int] | None,
        Query(description="IDs de UnidadeAdministrativa. Repita o param para multi."),
    ] = None,
    cedente_id: Annotated[int | None, Query(description="Id do cedente (Bitfin)")] = None,
    sacado_id: Annotated[int | None, Query(description="Id do sacado (Bitfin)")] = None,
    gerente_documento: Annotated[str | None, Query(description="CPF do gerente")] = None,
) -> BIFilters:
    """Filtros globais do modulo BI — injetados em todo endpoint /bi/*."""
    return BIFilters(
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        produto_sigla=produto_sigla or None,
        ua_id=ua_id or None,
        cedente_id=cedente_id,
        sacado_id=sacado_id,
        gerente_documento=gerente_documento,
    )
