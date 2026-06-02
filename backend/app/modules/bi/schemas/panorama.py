"""Schemas do BI -> Panorama (Observatorio FIDC, mercado CVM).

Pagina `/bi/panorama` — analise ampla do segmento FIDC a partir do Informe
Mensal CVM (schema federado `cvm_remote.*`). Dado publico, sem tenant.

Fase 1: aba Visao Geral (KPIs macro + evolucao do PL + split por condominio
+ distribuicao de tamanho). Demais abas (Players, Risco & Liquidez, Lastro &
Prazo, Concentracao) ganham schemas proprios em iteracoes seguintes.
"""

from pydantic import BaseModel, Field


class PanoramaFilters(BaseModel):
    """Filtros globais da pagina Panorama (URL-persisted no frontend).

    Todos opcionais. `None` = filtro nao aplicado. Aplicados a 100% dos
    agregados via `_filter_where` no service (§7.2). Apenas campos
    ESTRUTURADOS da CVM — sem heuristica de nome. Padronizado x NP e situacao
    cadastral ficam de fora ate o ETL de `cad_fi_classe_fidc` (gated, Fase 2).
    """

    competencia: str | None = Field(default=None, description="'YYYY-MM'. None => ultima disponivel")
    condom: str | None = Field(default=None, description="'aberto' | 'fechado' (campo cvm condom)")
    faixa_pl: str | None = Field(
        default=None,
        description="Faixa de porte: 'lt50'|'50_200'|'200_500'|'500_1000'|'gt1000'",
    )
    tipo_carteira: str | None = Field(
        default=None, description="'propria' | 'cotas' (razao cotas-de-fundos / ativo)"
    )
    admin_cnpj: str | None = Field(default=None, description="CNPJ do administrador (cvm cnpj_admin)")


class PanoramaKpis(BaseModel):
    """KPIs macro do segmento (sob os filtros ativos)."""

    pl_total: float = Field(description="Soma do PL (R$)")
    n_fidc: int = Field(description="Quantidade de entidades reportantes")
    pl_medio: float = Field(description="PL medio por fundo (R$)")
    delta_fundos: int = Field(description="Variacao liquida de fundos vs competencia anterior")
    liquidez_pct: float = Field(description="Indice de liquidez ampla / PL (ponderado, %)")


class PlPonto(BaseModel):
    """Ponto da serie de evolucao do PL."""

    competencia: str  # 'YYYY-MM'
    pl: float
    n_fidc: int


class CondominioItem(BaseModel):
    """Split de PL por tipo de condominio (Aberto/Fechado)."""

    condom: str  # 'Aberto' | 'Fechado'
    n_fidc: int
    pl: float
    pct_pl: float


class TamanhoBucket(BaseModel):
    """Bucket da distribuicao de tamanho (faixa de PL)."""

    faixa: str  # rotulo legivel (ex.: '< R$ 50 mi')
    n_fidc: int
    pl: float


class VisaoGeralData(BaseModel):
    """Payload da aba Visao Geral."""

    competencia: str  # 'YYYY-MM' resolvida
    kpis: PanoramaKpis
    evolucao_pl: list[PlPonto]
    por_condominio: list[CondominioItem]
    distribuicao_tamanho: list[TamanhoBucket]
