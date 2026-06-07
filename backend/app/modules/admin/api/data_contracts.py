"""Curadoria de Contratos de Dados (system maintainer only) — Fase 5.

CRUD do governance de campos de fontes externas. Versionamento IMUTÁVEL:
salvar = nova versão + ativa (rollback = reativar versão anterior).

Nível MANTENEDOR: a hierarquia provedor/API/dataset_code é identidade interna
de vendor (white-label esconde do tenant) — só maintainer cura.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.system_maintainer_guard import require_system_maintainer
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.shared.data_providers import contract_admin
from app.shared.data_providers.schemas_contract import (
    DatasetContractDetailRead,
    DatasetContractListItemRead,
    DatasetFieldRead,
    NewVersionPayload,
)

router = APIRouter(prefix="/data-contracts", tags=["admin:data-contracts"])

_GUARD = [
    Depends(require_system_maintainer),
    Depends(require_module(Module.ADMIN, Permission.ADMIN)),
]


def _detail_to_read(d: contract_admin.ContractDetail) -> DatasetContractDetailRead:
    return DatasetContractDetailRead(
        contract_id=d.contract_id,
        provider=d.provider,
        api_endpoint=d.api_endpoint,
        dataset_code=d.dataset_code,
        public_code=d.public_code,
        version=d.version,
        status=d.status,
        n_novos=d.n_novos,
        campos=[
            DatasetFieldRead(
                field_path=f.field_path,
                public_label=f.public_label,
                description=f.description,
                semantic_type=f.semantic_type,
                categoria_ui=f.categoria_ui,
                sensibilidade=f.sensibilidade,
                eh_fato=f.eh_fato,
                to_silver=f.to_silver,
                silver_target=f.silver_target,
                on_screen=f.on_screen,
                screen_order=f.screen_order,
                to_tool=f.to_tool,
                to_agent=f.to_agent,
                to_check=f.to_check,
                status=f.status,
                novo=f.novo,
                valor_exemplo=f.valor_exemplo,
            )
            for f in d.campos
        ],
    )


@router.get("", response_model=list[DatasetContractListItemRead], dependencies=_GUARD)
async def list_data_contracts(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DatasetContractListItemRead]:
    items = await contract_admin.list_contracts(db)
    return [
        DatasetContractListItemRead(
            contract_id=i.contract_id,
            provider=i.provider,
            api_endpoint=i.api_endpoint,
            dataset_code=i.dataset_code,
            public_code=i.public_code,
            version=i.version,
            status=i.status,
            n_campos=i.n_campos,
        )
        for i in items
    ]


@router.get(
    "/{provider}/{api_endpoint}/{dataset_code}",
    response_model=DatasetContractDetailRead,
    dependencies=_GUARD,
)
async def get_data_contract(
    provider: str,
    api_endpoint: str,
    dataset_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DatasetContractDetailRead:
    detail = await contract_admin.get_contract_detail(
        db, provider=provider, api_endpoint=api_endpoint, dataset_code=dataset_code
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Contrato não encontrado.")
    return _detail_to_read(detail)


@router.post(
    "/{provider}/{api_endpoint}/{dataset_code}/new-version",
    response_model=DatasetContractDetailRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_GUARD,
)
async def save_new_version(
    provider: str,
    api_endpoint: str,
    dataset_code: str,
    payload: NewVersionPayload,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DatasetContractDetailRead:
    # Regra dura do contrato: campo em check ⇒ tem que estar no silver.
    fields: list[dict] = []
    for f in payload.fields:
        d = f.model_dump()
        if d.get("to_check"):
            d["to_silver"] = True
        fields.append(d)

    owner = str(principal.user_id) if principal.user_id else None
    try:
        await contract_admin.save_new_version(
            db,
            provider=provider,
            api_endpoint=api_endpoint,
            dataset_code=dataset_code,
            fields=fields,
            owner=owner,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await db.commit()

    detail = await contract_admin.get_contract_detail(
        db, provider=provider, api_endpoint=api_endpoint, dataset_code=dataset_code
    )
    if detail is None:
        raise HTTPException(status_code=500, detail="Falha ao reabrir o contrato.")
    return _detail_to_read(detail)
