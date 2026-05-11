"""Controladoria · Estoque Carteira — endpoint do bundle.

Slug `qitech-estoque-carteira` tem detail page rica (DashboardBiPadrao com
KPIs + charts). Este router serve so o BUNDLE de agregados; a tabela
paginada de recebiveis continua via `GET /relatorios/{slug}` generico.

Multi-tenant + RBAC: `require_module(CONTROLADORIA, READ)` + visibilidade
do slug (admin QiTech tem que estar habilitada para o tenant).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.controladoria.schemas.qitech_estoque_carteira import (
    CarteiraBundleResponse,
)
from app.modules.controladoria.services import reports as reports_service
from app.modules.controladoria.services import qitech_estoque_carteira as service

_SLUG = "qitech-estoque-carteira"

router = APIRouter(
    prefix="/relatorios/padronizados/qitech-estoque-carteira",
    tags=["controladoria:relatorios"],
)

_Guard = Depends(require_module(Module.CONTROLADORIA, Permission.READ))


@router.get("/bundle", response_model=CarteiraBundleResponse)
async def bundle(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[
        UUID | None,
        Query(description="UUID da Unidade Administrativa (FIDC) para escopar."),
    ] = None,
    data_referencia: Annotated[
        date | None,
        Query(
            description=(
                "Data do snapshot da carteira. Quando omitida, retorna a "
                "ultima data sincronizada no escopo."
            )
        ),
    ] = None,
    _: None = _Guard,
) -> CarteiraBundleResponse:
    """Bundle agregado da carteira (KPIs + breakdowns + proveniencia).

    Use junto com `GET /relatorios/{slug}` (que retorna a tabela paginada de
    recebiveis individuais).
    """
    spec = reports_service.resolve_spec_or_404(_SLUG)
    visible = await reports_service.get_visible_reports(
        db, tenant_id=principal.tenant_id
    )
    if spec not in visible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Relatorio {_SLUG!r} nao disponivel para este tenant — "
                f"administradora {spec.administradora.value} nao esta conectada."
            ),
        )

    data = await service.get_carteira_bundle(
        db,
        tenant_id=principal.tenant_id,
        fundo_id=fundo_id,
        data_referencia=data_referencia,
    )
    return CarteiraBundleResponse(**data)


@router.get("/export.csv")
async def export_csv(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID | None, Query()] = None,
    data_referencia: Annotated[date | None, Query()] = None,
    _: None = _Guard,
) -> StreamingResponse:
    """Exporta a carteira em CSV (semicolon BR + UTF-8 BOM) respeitando os
    filtros globais. Streaming linha-a-linha — sem materializar 100k titulos
    em memoria. Excel pt-BR abre direto (delimitador ; + BOM = sem wizard).

    Mantido para callers legacy / integracao com ferramentas que preferem
    CSV (PowerBI Get Data, scripts). UI usa `/export.xlsx`.
    """
    spec = reports_service.resolve_spec_or_404(_SLUG)
    visible = await reports_service.get_visible_reports(
        db, tenant_id=principal.tenant_id
    )
    if spec not in visible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Relatorio {_SLUG!r} nao disponivel para este tenant — "
                f"administradora {spec.administradora.value} nao esta conectada."
            ),
        )

    # Nome do arquivo inclui a data_referencia (resolvida pelo service quando
    # vier None) — operador entende sem abrir o arquivo qual snapshot e.
    date_part = data_referencia.isoformat() if data_referencia else "ultimo"
    filename = f"carteira-{date_part}.csv"

    return StreamingResponse(
        service.stream_carteira_csv(
            db,
            tenant_id=principal.tenant_id,
            fundo_id=fundo_id,
            data_referencia=data_referencia,
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export.xlsx")
async def export_xlsx(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fundo_id: Annotated[UUID | None, Query()] = None,
    data_referencia: Annotated[date | None, Query()] = None,
    _: None = _Guard,
):
    """Exporta a carteira em XLSX (native types) respeitando os filtros globais.

    Diferenca para `/export.csv`:
        - Numeros (valor_nominal, valor_presente, ...) ficam como tipo Numero
          no Excel (sort/filter/sum nativo).
        - Datas (data_referencia, vencimentos, ...) ficam como tipo Data.
        - Locale display fica a cargo do Excel do usuario.

    write_only mode mantem footprint de memoria ~constante mesmo pra 100k
    titulos. Excel arquivo materializado em ~3-5 MB.
    """
    from fastapi.responses import Response

    spec = reports_service.resolve_spec_or_404(_SLUG)
    visible = await reports_service.get_visible_reports(
        db, tenant_id=principal.tenant_id
    )
    if spec not in visible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Relatorio {_SLUG!r} nao disponivel para este tenant — "
                f"administradora {spec.administradora.value} nao esta conectada."
            ),
        )

    date_part = data_referencia.isoformat() if data_referencia else "ultimo"
    filename = f"carteira-{date_part}.xlsx"

    content = await service.build_carteira_xlsx(
        db,
        tenant_id=principal.tenant_id,
        fundo_id=fundo_id,
        data_referencia=data_referencia,
    )

    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
