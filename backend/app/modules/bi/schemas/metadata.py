"""Schemas de metadados auxiliares do modulo BI.

Coisas como listas de dimensoes (UAs, produtos, etc.) que alimentam
dropdowns/filtros no frontend. Separado de `operacoes.py` porque nao e
serie/KPI — e taxonomia.
"""

from datetime import date

from pydantic import BaseModel, Field


class UAOption(BaseModel):
    """Uma UA disponivel no tenant, para popular filtros de UI."""

    id: int = Field(description="ID da UA (correspondente ao UnidadeAdministrativaId do Bitfin)")
    nome: str = Field(description="Nome amigavel da UA (Alias no Bitfin)")
    ativa: bool = Field(description="Se a UA esta marcada como ativa na fonte")


class ProdutoOption(BaseModel):
    """Um produto disponivel no tenant, para popular filtros de UI.

    Retornado por `/bi/metadata/produtos`. Mesmo shape que o frontend ja
    usa internamente (sigla + nome completo). A sigla e a chave usada em
    `BIFilters.produtoSigla` ao filtrar queries de BI.
    """

    sigla: str = Field(description="Sigla curta do produto (ex.: 'FAT')")
    nome: str = Field(description="Nome completo amigavel (ex.: 'Faturização')")
    tipo_de_contrato: str | None = Field(
        default=None, description="Categoria do contrato (quando aplicavel)"
    )
    produto_de_risco: bool = Field(
        default=False, description="Se o produto envolve risco de credito"
    )


class DataMinimaResponse(BaseModel):
    """Resposta do endpoint de data minima — primeira operacao efetivada.

    Frontend usa para computar o range do preset 'ALL' no seletor de
    periodo da pagina de BI.
    """

    data_minima: date | None = Field(
        description=(
            "Data da operacao efetivada mais antiga do tenant. "
            "None quando nao ha operacoes (tenant novo/vazio)."
        ),
    )
