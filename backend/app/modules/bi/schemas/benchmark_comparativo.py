"""Schemas da L3 Comparativo (BI / Benchmark).

Consome dados publicos CVM FIDC (mesma fonte que o restante do Benchmark).
Confronta ate 5 fundos na competencia selecionada + evolucao dos ultimos N
meses + composicao snapshot (ativo, setor, SCR devedor).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FundoHeader(BaseModel):
    """Cabecalho de um fundo no comparativo.

    `cor_index` alimenta a paleta A7 (slots 0..4 -> slate/sky/teal/emerald/amber)
    no frontend — estavel por ordem de entrada nos `cnpjs` da request.
    """

    cnpj: str = Field(description="CNPJ digits-only (14 caracteres)")
    denom_social: str | None
    classe_anbima: str | None
    cor_index: int = Field(ge=0, le=4)


class RankingValor(BaseModel):
    """Valor de um indicador para um fundo (NULL quando dado ausente)."""

    cnpj: str
    valor: float | None


class RankingLinha(BaseModel):
    """Uma linha da tabela de ranking: um indicador × todos os fundos.

    `direction` indica a semantica do "melhor":
      - "desc": maior e melhor (PL, cobertura, qtd cedentes)
      - "asc":  menor e melhor (inadimplencia, concentracao top-1)

    `mediana_mercado` e a mediana na mesma competencia considerando TODOS os
    fundos do mercado — alimenta a coluna/linha "Mediana de mercado" que da
    referencia pro analista.
    """

    key: str = Field(description="Chave estavel do indicador (ex.: 'pl', 'pct_inad_total')")
    label: str = Field(description="Label em pt-BR pro header da linha")
    unidade: str = Field(description="'BRL' | '%' | 'un' | 'dias'")
    direction: str = Field(description="'asc' | 'desc'")
    mediana_mercado: float | None
    valores: list[RankingValor]


class PontoSerieValor(BaseModel):
    """Valor de um fundo num ponto da serie."""

    cnpj: str
    valor: float | None


class PontoSerie(BaseModel):
    """Um ponto mensal da serie evolutiva.

    `competencia` e 'YYYY-MM' (string, nao date — alinhado com o frontend que
    renderiza rotulos "mar/26").
    """

    competencia: str
    mediana: float | None
    valores: list[PontoSerieValor]


class ComposicaoFatia(BaseModel):
    """Fatia de composicao (ativo, setor, SCR)."""

    categoria: str
    valor: float
    percentual: float | None = None


class ComposicaoFundo(BaseModel):
    """Snapshot de composicao de 1 fundo na competencia.

    - `ativo` — 6 fatias fixas (DC com/sem risco, TPF, CDB, VM, Outros).
    - `setores_top` — top 5 setores do II (BarList).
    - `scr_devedor` — distribuicao AA..H (tab_x) quando reportada.
    """

    cnpj: str
    ativo_total: float | None
    ativo: list[ComposicaoFatia]
    setores_top: list[ComposicaoFatia]
    scr_devedor: list[ComposicaoFatia]


class ComparativoResponse(BaseModel):
    """Resposta completa do L3 Comparativo."""

    competencia: str = Field(description="'YYYY-MM' da competencia de referencia")
    fundos: list[FundoHeader]
    ranking: list[RankingLinha]
    series: dict[str, list[PontoSerie]] = Field(
        description="indicador_key -> lista de pontos mensais (N meses)"
    )
    composicoes: list[ComposicaoFundo]
