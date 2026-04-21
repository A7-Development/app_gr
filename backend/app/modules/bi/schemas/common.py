"""Schemas comuns ao modulo BI.

Filtros globais (barra superior do modulo BI) + bloco de proveniencia padrao
para toda resposta analitica do BI (CLAUDE.md 14.1 / 14.6).
"""

from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BIFilters(BaseModel):
    """Filtros globais do modulo BI (URL-persisted no frontend).

    Todos os campos sao opcionais. Quando `None` (ou lista vazia), o filtro
    nao e aplicado.
    - `periodo_inicio` / `periodo_fim`: intervalo fechado.
    - `produto_sigla`: lista de siglas (FAT, CMS, DMS, ...) — WHERE IN.
    - `ua_id`: lista de unidades administrativas — WHERE IN.
    - `cedente_id` / `sacado_id`: filtra entidades.
    - `gerente_documento`: filtra por gerente (CPF normalizado).
    """

    periodo_inicio: date | None = Field(default=None, description="Data inicial (inclusive)")
    periodo_fim: date | None = Field(default=None, description="Data final (inclusive)")
    produto_sigla: list[str] | None = Field(
        default=None, description="Siglas de produto (multi). Ex.: ['FAT', 'CMS']"
    )
    ua_id: list[int] | None = Field(
        default=None, description="IDs de UnidadeAdministrativa (multi)"
    )
    cedente_id: int | None = Field(default=None, description="Id do cedente (Bitfin Empresa.Id)")
    sacado_id: int | None = Field(default=None, description="Id do sacado (Bitfin Empresa.Id)")
    gerente_documento: str | None = Field(default=None, description="CPF do gerente")


class Provenance(BaseModel):
    """Metadata de proveniencia — anexada a toda resposta analitica do BI.

    Segue o mesmo padrao do `/audit/ping` (CLAUDE.md 14.1).
    """

    source_type: str = Field(description="Origem do dado (ex.: 'erp:bitfin', 'derived')")
    source_ids: list[str] = Field(
        default_factory=list, description="IDs/fontes consultadas nesta agregacao"
    )
    last_ingested_at: datetime | None = Field(
        default=None, description="Timestamp do ETL mais recente que contribuiu"
    )
    last_source_updated_at: datetime | None = Field(
        default=None, description="Timestamp max de source_updated_at dos registros agregados"
    )
    trust_level: str = Field(default="high", description="'high' | 'medium' | 'low'")
    ingested_by_version: str = Field(description="Versao do(s) adapter(s) de origem")
    row_count: int = Field(description="Quantidade de linhas do warehouse consideradas")


class BIResponse(BaseModel, Generic[T]):
    """Envelope padrao de resposta BI: `data + provenance`."""

    data: T
    provenance: Provenance


class Point(BaseModel):
    """Ponto de serie temporal."""

    periodo: date
    valor: float


class CategoryValue(BaseModel):
    """Agregacao por categoria (produto, cedente, etc)."""

    categoria: str
    valor: float
    quantidade: int | None = None


class KPI(BaseModel):
    """KPI agregado — label + valor + unidade."""

    label: str
    valor: float
    unidade: str = Field(description="'BRL' | '%' | 'un' | 'dias'")
    detalhe: str | None = None
