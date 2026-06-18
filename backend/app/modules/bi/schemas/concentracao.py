"""BI -> L2 Concentracao — schemas.

Concentracao da carteira FIDC: Top-10 cedentes e Top-10 sacados por
**valor presente** (carteira QiTech, `wh_estoque_recebivel`) sobre o
**PL total do fundo** (MEC, soma do patrimonio das classes em
`wh_mec_evolucao_cotas`). Granularidade diaria.

Escopo: so Realinvest por enquanto (A7 Credit tera logica propria depois).
"""

from datetime import date

from pydantic import BaseModel, Field


class ConcentracaoItem(BaseModel):
    """Uma linha do ranking (1 cedente ou 1 sacado)."""

    rank: int
    nome: str
    documento: str
    financeiro: float = Field(description="Valor presente dos titulos (R$)")
    pct_pl: float = Field(description="financeiro / PL total do fundo * 100")


class ConcentracaoTabela(BaseModel):
    """Top-10 + linha '10 maiores' (total que reconcilia §14.6)."""

    itens: list[ConcentracaoItem]
    total_financeiro: float
    total_pct_pl: float


class HistoricoPonto(BaseModel):
    """Ponto diario da serie de concentracao."""

    data: date
    maior_pct: float = Field(description="% do PL do maior (1o) cedente/sacado")
    top10_pct: float = Field(description="% do PL dos 10 maiores")


class ConcentracaoData(BaseModel):
    """Payload da pagina /bi/concentracao."""

    data_posicao: date
    pl_total: float
    cedentes: ConcentracaoTabela
    sacados: ConcentracaoTabela
    historico_cedentes: list[HistoricoPonto]
    historico_sacados: list[HistoricoPonto]
