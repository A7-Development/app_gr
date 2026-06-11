"""Catálogo de datasets (system maintainer only) — Fase F (a fundação).

Navega `provedor_dados_dataset` (Provedor → API/endpoint → Dataset), cura o nível
do dataset (nome/public_code/categoria/habilitar/markup) e cria a 1ª versão do
Contrato de campos. A folha (curadoria de campos) continua em /data-contracts.

Nível MANTENEDOR: a hierarquia de vendor é interna (white-label esconde do
tenant) — só maintainer navega.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.data_providers import catalog_admin
from app.shared.data_providers.schemas_catalog import (
    CatalogApiGroupRead,
    CatalogContractRefRead,
    CatalogDatasetRowRead,
    CatalogProviderGroupRead,
    CreatedContractRead,
    DatasetCurationPayload,
)

router = APIRouter(prefix="/data-catalog", tags=["admin:data-catalog"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


def _row_to_read(r: catalog_admin.CatalogDatasetRow) -> CatalogDatasetRowRead:
    return CatalogDatasetRowRead(
        dataset_id=r.dataset_id,
        provider_slug=r.provider_slug,
        provider_api=r.provider_api,
        provider_dataset_code=r.provider_dataset_code,
        provider_query_name=r.provider_query_name,
        public_code=r.public_code,
        display_name_pt_br=r.display_name_pt_br,
        categoria_ui=r.categoria_ui,
        enabled_for_sale=r.enabled_for_sale,
        current_cost_brl=r.current_cost_brl,
        cost_editable=r.cost_editable,
        markup_pct=r.markup_pct,
        mode=r.mode,
        suggested_public_code=r.suggested_public_code,
        suggested_name=r.suggested_name,
        contract=CatalogContractRefRead(
            status=r.contract.status,
            version=r.contract.version,
            provider=r.contract.provider,
            api_endpoint=r.contract.api_endpoint,
            dataset_code=r.contract.dataset_code,
            n_campos=r.contract.n_campos,
            n_novos=r.contract.n_novos,
        ),
    )


@router.get("", response_model=list[CatalogProviderGroupRead], dependencies=_GUARD)
async def list_catalog(
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: str | None = None,
    search: str | None = None,
    only_enabled: bool = False,
    only_without_contract: bool = False,
) -> list[CatalogProviderGroupRead]:
    groups = await catalog_admin.list_catalog(
        db,
        provider_slug=provider,
        search=search,
        only_enabled=only_enabled,
        only_without_contract=only_without_contract,
    )
    return [
        CatalogProviderGroupRead(
            provider_slug=g.provider_slug,
            provider_name=g.provider_name,
            total=g.total,
            enabled_count=g.enabled_count,
            with_contract_count=g.with_contract_count,
            apis=[
                CatalogApiGroupRead(
                    api=a.api,
                    total=a.total,
                    datasets=[_row_to_read(r) for r in a.datasets],
                )
                for a in g.apis
            ],
        )
        for g in groups
    ]


@router.patch(
    "/datasets/{dataset_id}",
    response_model=CatalogDatasetRowRead,
    dependencies=_GUARD,
)
async def curate_dataset(
    dataset_id: UUID,
    payload: DatasetCurationPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CatalogDatasetRowRead:
    try:
        await catalog_admin.update_dataset_curation(
            db,
            dataset_id=dataset_id,
            public_code=payload.public_code,
            display_name_pt_br=payload.display_name_pt_br,
            categoria_ui=payload.categoria_ui,
            enabled_for_sale=payload.enabled_for_sale,
            markup_pct=payload.markup_pct,
            current_cost_brl=payload.current_cost_brl,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()

    # Reabre só essa linha do catálogo (busca por dataset_id na árvore).
    groups = await catalog_admin.list_catalog(db)
    for g in groups:
        for a in g.apis:
            for r in a.datasets:
                if r.dataset_id == dataset_id:
                    return _row_to_read(r)
    raise HTTPException(status_code=404, detail="Dataset não encontrado.")


@router.post(
    "/datasets/{dataset_id}/create-contract",
    response_model=CreatedContractRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_GUARD,
)
async def create_contract(
    dataset_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreatedContractRead:
    owner = str(principal.user_id) if principal.user_id else None
    try:
        created = await catalog_admin.create_contract_for_dataset(
            db, dataset_id=dataset_id, owner=owner
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return CreatedContractRead(
        provider=created.provider,
        api_endpoint=created.api_endpoint,
        dataset_code=created.dataset_code,
        public_code=created.public_code,
        version=created.version,
        n_campos=created.n_campos,
        already_existed=created.already_existed,
    )
