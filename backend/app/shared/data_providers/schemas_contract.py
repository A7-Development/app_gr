"""Schemas da API de curadoria de Contratos de Dados (admin/mantenedor)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DatasetFieldRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str
    public_label: str | None = None
    description: str | None = None
    semantic_type: str
    categoria_ui: str | None = None
    sensibilidade: str
    eh_fato: str
    to_silver: bool
    silver_target: str | None = None
    on_screen: bool
    screen_order: int | None = None
    to_tool: bool
    to_agent: bool
    to_check: bool
    status: str
    novo: bool
    valor_exemplo: str | None = None


class DatasetContractListItemRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_id: UUID
    provider: str
    api_endpoint: str
    dataset_code: str
    public_code: str | None = None
    version: int
    status: str
    n_campos: int


class DatasetContractDetailRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_id: UUID
    provider: str
    api_endpoint: str
    dataset_code: str
    public_code: str | None = None
    version: int
    status: str
    campos: list[DatasetFieldRead]
    n_novos: int


class FieldSaveSpec(BaseModel):
    """Estado desejado de UM campo (a UI manda o conjunto completo)."""

    model_config = ConfigDict(extra="forbid")

    field_path: str
    public_label: str | None = None
    description: str | None = None
    semantic_type: str = "text"
    categoria_ui: str | None = None
    sensibilidade: str = "publico"
    eh_fato: str = "contexto"
    to_silver: bool = False
    silver_target: str | None = None
    on_screen: bool = True
    screen_order: int | None = None
    to_tool: bool = False
    to_agent: bool = False
    to_check: bool = False


class NewVersionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[FieldSaveSpec] = Field(default_factory=list)
