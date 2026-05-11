"""Controladoria · Relatorios — endpoints.

Catalogo unico de relatorios mostrado em `/controladoria/relatorios`. Fonte
de verdade do catalogo: `app.modules.integracoes.report_catalog` (declarativo,
sem tabela DB — ver docstring naquela module).

A pagina catalogo no frontend tem 2 tabs L3 (Padronizados / Espelho da
Administradora). Ambas leem o MESMO catalogo; a diferenca e visual
(Opcao A — lente operacional). Esta API nao distingue tabs.

Multi-tenant: todo endpoint exige `require_module(CONTROLADORIA, READ)`. Toda
query e escopada por `tenant_id` via `RequestPrincipal`. Catalogo e filtrado
por `tenant_source_config.enabled` da admin de cada relatorio.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.controladoria.schemas.reports import (
    CatalogResponse,
    ProvenanceMetadata,
    ReportCardResponse,
    RowsResponse,
)
from app.modules.controladoria.services import reports as reports_service
from app.modules.integracoes.report_catalog import ReportCategory, ReportSpec

router = APIRouter(prefix="/relatorios", tags=["controladoria:relatorios"])

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))


def _to_card(spec: ReportSpec) -> ReportCardResponse:
    return ReportCardResponse(
        slug=spec.slug,
        name=spec.name,
        description=spec.description,
        category=spec.category,
        administradora=spec.administradora,
        endpoint_name=spec.endpoint_name,
        canonical_table=spec.canonical_table,
        refresh_kind=spec.refresh_kind,
        has_date_filter=spec.date_column is not None,
        has_fund_filter=spec.fund_column is not None,
        default_permission=spec.default_permission,
    )


@router.get("/catalog", response_model=CatalogResponse)
async def catalog(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Annotated[
        ReportCategory | None,
        Query(description="Filtra por categoria semantica (Cota, Posicao, ...)."),
    ] = None,
    _: None = _Guard,
) -> CatalogResponse:
    """Lista relatorios visiveis ao tenant.

    Visibilidade = a administradora do relatorio tem
    `tenant_source_config.enabled=true` para o tenant atual (ambiente
    production). Tenant sem QiTech conectada nao ve relatorios QiTech.
    """
    visible = await reports_service.get_visible_reports(
        db, tenant_id=principal.tenant_id, category=category
    )
    cards = [_to_card(spec) for spec in visible]
    return CatalogResponse(reports=cards, total=len(cards))


@router.get("/{slug}", response_model=RowsResponse)
async def rows(
    slug: str,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[
        UUID | None,
        Query(description="UUID da Unidade Administrativa (FIDC) para escopar o relatorio."),
    ] = None,
    periodo_inicio: Annotated[
        date | None,
        Query(description="Inicio do periodo (inclusivo). Aplicavel quando o relatorio tem coluna de data."),
    ] = None,
    periodo_fim: Annotated[
        date | None,
        Query(description="Fim do periodo (inclusivo)."),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Pagina (1-based).")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=10_000, description="Tamanho da pagina (max 10.000).")
    ] = 50,
    _: None = _Guard,
) -> RowsResponse:
    """Linhas de UM relatorio do catalogo.

    Schema das colunas e definido por slug em
    `frontend/src/lib/reports/<slug>.ts`. Backend devolve linhas como dicts;
    frontend tipa via aquele arquivo.

    Resposta inclui `provenance` com origem (administradora, adapter version,
    last_ingested_at) — consumido por `<DataOriginBadge>` no header da pagina
    (CLAUDE.md §14.5).
    """
    try:
        spec = reports_service.resolve_spec_or_404(slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    # Defesa adicional: usuario pode tentar acessar slug cujo administradora
    # nao esta habilitado para o tenant. `get_visible_reports` ja filtra,
    # mas confirmamos antes de bater nos dados.
    visible = await reports_service.get_visible_reports(
        db, tenant_id=principal.tenant_id
    )
    if spec not in visible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Relatorio {slug!r} nao disponivel para este tenant — "
                f"administradora {spec.administradora.value} nao esta conectada."
            ),
        )

    rows_data, total = await reports_service.query_report_rows(
        db,
        spec=spec,
        tenant_id=principal.tenant_id,
        fundo_id=fundo_id,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        page=page,
        page_size=page_size,
    )
    proveniencia = await reports_service.get_report_provenance(
        db, spec=spec, tenant_id=principal.tenant_id
    )

    return RowsResponse(
        rows=rows_data,
        total=total,
        page=page,
        page_size=page_size,
        provenance=ProvenanceMetadata(**proveniencia),
    )
