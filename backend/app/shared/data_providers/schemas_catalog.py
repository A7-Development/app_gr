"""Schemas da API do Catálogo de datasets (admin/mantenedor) — Fase F."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CatalogContractRefRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str  # "active" | "none"
    version: int | None = None
    provider: str | None = None
    api_endpoint: str | None = None
    dataset_code: str | None = None
    n_campos: int | None = None
    n_novos: int | None = None


class CatalogDatasetRowRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: UUID
    provider_slug: str
    provider_api: str
    provider_dataset_code: str
    provider_query_name: str | None = None
    public_code: str | None = None
    display_name_pt_br: str | None = None
    categoria_ui: str | None = None
    enabled_for_sale: bool
    current_cost_brl: float | None = None
    cost_editable: bool = False
    markup_pct: float | None = None
    mode: str
    suggested_public_code: str
    suggested_name: str
    contract: CatalogContractRefRead


class CatalogApiGroupRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api: str
    total: int
    datasets: list[CatalogDatasetRowRead]


class CatalogProviderGroupRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_slug: str
    provider_name: str
    total: int
    enabled_count: int
    with_contract_count: int
    apis: list[CatalogApiGroupRead]


class DatasetCurationPayload(BaseModel):
    """Patch da camada A7 do dataset. Campo ausente/None = não mexer."""

    model_config = ConfigDict(extra="forbid")

    public_code: str | None = None
    display_name_pt_br: str | None = None
    categoria_ui: str | None = None
    enabled_for_sale: bool | None = None
    markup_pct: float | None = None
    # Custo manual — aceito apenas em datasets SEM sync de preços do vendor.
    current_cost_brl: float | None = None


class CreatedContractRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    api_endpoint: str
    dataset_code: str
    public_code: str
    version: int
    n_campos: int
    already_existed: bool
