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
    """Top-10 + '10 maiores' (subtotal) + 'Outros' (cauda) — reconcilia §14.6.

    top-10 + outros = carteira inteira (nenhum titulo escondido)."""

    itens: list[ConcentracaoItem]
    total_financeiro: float
    total_pct_pl: float
    # Cauda: tudo que nao esta no top-10.
    outros_qtd: int
    outros_financeiro: float
    outros_pct_pl: float


class HistoricoPonto(BaseModel):
    """Ponto diario da serie de concentracao."""

    data: date
    maior_pct: float = Field(description="% do PL do maior (1o) cedente/sacado")
    top5_pct: float = Field(description="% do PL dos 5 maiores")
    top10_pct: float = Field(description="% do PL dos 10 maiores")


class ConcentracaoUA(BaseModel):
    """Unidade administrativa (fundo) — para o filtro UA."""

    id: str
    nome: str


class ConcentracaoData(BaseModel):
    """Payload da pagina /bi/concentracao."""

    # UA atual (selecionada/default) + todas as UAs do tenant (filtro UA).
    ua: ConcentracaoUA | None
    uas: list[ConcentracaoUA]
    # False = UA sem logica de concentracao ainda (so Realinvest por enquanto).
    suportado: bool
    data_posicao: date
    pl_total: float
    # Proveniencia do PL usado como denominador: data efetiva (MEC pode usar
    # fallback <= data_posicao) + origem.
    pl_data: date | None
    pl_origem: str
    # Datas de carteira disponiveis (recentes, desc) — popula o filtro Posicao.
    datas_disponiveis: list[date]
    cedentes: ConcentracaoTabela
    sacados: ConcentracaoTabela
    historico_cedentes: list[HistoricoPonto]
    historico_sacados: list[HistoricoPonto]
