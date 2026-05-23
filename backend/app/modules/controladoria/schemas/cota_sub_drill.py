"""Pydantic schemas — Controladoria · Cota Sub · drills F2 (2026-05-23).

Schemas dos drills ricos do Balance hero: DC, PDD, CPR. Cada drill abre
o `DrillDownSheet` lateral direito quando o usuario clica na categoria
correspondente do `BalancoPatrimonialHero`.

Decoupled de `schemas/cota_sub.py` — aquele cobre o endpoint /variacao-diaria
(driver-centric, sinais invertidos por compatibilidade) + os explainers
heuristicos (bucket COSIF). Aqui o shape e narrativa-centrica:

  - DC:  Apropriacao = ΔEstoque - Aquisicoes + Liquidacoes (formula explicita)
  - PDD: Matriz de migracao A/B/C/D/E/F/G/H ↔ WOP/NOVO + top papeis
  - CPR: Classificacao por natureza (diferimento, despesa apropriada,
         IOF/IR, aporte engaiolado, outros) + top lines por categoria

Convencoes:
  - Sinais ABSOLUTOS (positivos), exceto delta_* que carregam sinal natural.
  - Threshold + top_n configuraveis via query param do endpoint.
  - `estoque_disponivel_*` flags no PDD avisam quando o granular do estoque
    nao esta publicado pra alguma das datas (guard de cota_sub_explainers).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# ── DRILL DC ────────────────────────────────────────────────────────────────


class DrillDcAquisicao(BaseModel):
    """1 aquisicao do dia (linha de `wh_aquisicao_recebivel` com data_aquisicao = D0)."""

    cedente_doc:        str
    cedente_nome:       str
    sacado_doc:         str
    sacado_nome:        str
    seu_numero:         str
    numero_documento:   str
    tipo_recebivel:     str
    data_vencimento:    date | None = None
    valor_compra:       Decimal
    valor_vencimento:   Decimal
    taxa_aquisicao:     Decimal
    prazo_recebivel:    int


class DrillDcLiquidacaoPorTipo(BaseModel):
    """Liquidacoes do dia agregadas por `tipo_movimento`.

    Tipos canonicos observados em REALINVEST:
      - LIQUIDAÇÃO NORMAL          (sacado pagou no vencimento — caso comum)
      - BAIXA POR DEPOSITO SACADO  (sacado pagou em conta)
      - BAIXA POR DEPOSITO CEDENTE (cedente honrou a coobrigacao)
      - RECOMPRA                   (cedente recomprou o titulo)
      - BAIXA                      (write-off operacional)
    """

    tipo_movimento:         str
    qtd_papeis:             int
    sum_valor_pago:         Decimal = Field(description="Σ valor recebido em caixa")
    sum_valor_aquisicao:    Decimal = Field(description="Σ valor pelo qual o FIDC adquiriu (custo)")
    sum_valor_vencimento:   Decimal = Field(description="Σ valor de face no vencimento")
    sum_ajuste:             Decimal = Field(description="Σ ajustes contabeis aplicados")
    ganho_liquido:          Decimal = Field(description="Σ (valor_pago - valor_aquisicao - ajuste)")


class DrillDcLiquidacaoLinha(BaseModel):
    """1 liquidacao individual (top N por |valor_pago|)."""

    cedente_doc:        str
    cedente_nome:       str
    sacado_doc:         str
    sacado_nome:        str
    seu_numero:         str
    documento:          str
    tipo_recebivel:     str
    tipo_movimento:     str
    valor_pago:         Decimal
    valor_aquisicao:    Decimal
    valor_vencimento:   Decimal
    ajuste:             Decimal
    ganho_liquido:      Decimal = Field(description="valor_pago - valor_aquisicao - ajuste")


class DrillDcApropriacao(BaseModel):
    """Formula da apropriacao derivada da DC entre D-1 e D0.

        Apropriacao = ΔEstoque + Liquidacoes - Aquisicoes

    Onde:
      - ΔEstoque = estoque_d0 - estoque_d1 (sinal natural)
      - Aquisicoes = Σ valor_compra das aquisicoes em D0 (entrada no estoque)
      - Liquidacoes = Σ valor_aquisicao dos papeis liquidados em D0 (saida do
                      estoque ao preco de aquisicao — o ganho de liquidacao
                      sobre o preco de aquisicao vai pra Tesouraria, nao
                      apropriacao).

    Esperado: Apropriacao > 0 em dia tipico (juros + valorizacao MtM dos
    papeis ainda em estoque). Negativo quando ha mutacao silenciosa em
    valor_nominal/taxa (ver F5 do redesign).
    """

    estoque_d1:          Decimal = Field(description="Σ valor_presente em D-1")
    estoque_d0:          Decimal = Field(description="Σ valor_presente em D0")
    delta_estoque:       Decimal = Field(description="estoque_d0 - estoque_d1")
    aquisicoes_total:    Decimal = Field(description="Σ valor_compra (aquisicoes em D0)")
    liquidacoes_total:   Decimal = Field(description="Σ valor_aquisicao (papeis liquidados em D0)")
    apropriacao:         Decimal = Field(description="delta_estoque + liquidacoes_total - aquisicoes_total")


class DrillDcResponse(BaseModel):
    """Drill da categoria DC (Direitos Creditorios)."""

    fundo_id:            str
    fundo_nome:          str
    data:                date
    data_anterior:       date

    aquisicoes_qtd:      int
    aquisicoes_total:    Decimal
    aquisicoes:          list[DrillDcAquisicao]

    liquidacoes_qtd:     int
    liquidacoes_total:   Decimal
    liquidacoes_por_tipo:  list[DrillDcLiquidacaoPorTipo]
    liquidacoes_top:     list[DrillDcLiquidacaoLinha]

    apropriacao:         DrillDcApropriacao


# ── DRILL PDD ───────────────────────────────────────────────────────────────


# Faixas BACEN Resolucao 2682. WOP = write-off (papel sumiu entre D-1 e D0).
# NOVO = papel apareceu em D0 sem existir em D-1.
PddFaixaKey = Literal["A", "B", "C", "D", "E", "F", "G", "H", "WOP", "NOVO"]


class DrillPddMigracaoCelula(BaseModel):
    """1 celula da matriz: papeis que migraram de `faixa_de` -> `faixa_para`.

    - `faixa_de = NOVO` quando o papel nao existia em D-1.
    - `faixa_para = WOP` quando o papel existia em D-1 e nao existe em D0
      (write-off — saiu do estoque sem passar por liquidacao registrada).
    - Diagonal (`faixa_de == faixa_para`): papeis que ficaram na mesma
      faixa entre D-1 e D0. Maior parte do volume em dia tipico.
    """

    faixa_de:               PddFaixaKey
    faixa_para:             PddFaixaKey
    qtd_papeis:             int
    sum_valor_nominal:      Decimal
    sum_valor_presente_d1:  Decimal
    sum_valor_presente_d0:  Decimal
    sum_valor_pdd_d1:       Decimal
    sum_valor_pdd_d0:       Decimal
    sum_delta_pdd:          Decimal = Field(description="Σ (valor_pdd_d0 - valor_pdd_d1)")


class DrillPddPapel(BaseModel):
    """1 papel — top N por |delta_valor_pdd|, ou listagem WOP."""

    cedente_doc:                str
    cedente_nome:               str
    sacado_doc:                 str
    sacado_nome:                str
    seu_numero:                 str
    numero_documento:           str
    tipo_recebivel:             str
    valor_nominal:              Decimal = Field(description="Valor nominal (D0; fallback D-1)")
    data_vencimento_ajustada:   date | None = None
    faixa_pdd_d1:               PddFaixaKey | None = None
    faixa_pdd_d0:               PddFaixaKey | None = None
    valor_pdd_d1:               Decimal
    valor_pdd_d0:               Decimal
    delta_valor_pdd:            Decimal
    situacao_recebivel_d0:      str | None = None


class DrillPddResponse(BaseModel):
    """Drill da categoria PDD (Provisao para Devedores Duvidosos)."""

    fundo_id:                    str
    fundo_nome:                  str
    data:                        date
    data_anterior:               date

    # PDD consolidado (do _sum_pdd) — fonte de verdade para o delta da
    # categoria no balanco. Pode divergir do Σ granular abaixo quando a
    # QiTech publica PDD consolidado sem que o estoque granular reflita
    # ainda (defasagem de publicacao).
    pdd_consolidado_d1:          Decimal
    pdd_consolidado_d0:          Decimal
    pdd_consolidado_delta:       Decimal

    # Σ valor_pdd da granular (wh_estoque_recebivel). Para diff vs consolidado.
    pdd_granular_d1:             Decimal
    pdd_granular_d0:             Decimal

    estoque_disponivel_d1:       bool
    estoque_disponivel_d0:       bool
    motivo_indisponivel:         str | None = None

    matriz:                      list[DrillPddMigracaoCelula]

    # Papeis que sumiram (write-off) — destaque separado pelo impacto material.
    papeis_wop:                  list[DrillPddPapel]
    papeis_wop_total_pdd_d1:     Decimal = Field(description="Σ valor_pdd_d1 dos papeis WOP")

    # Top N papeis por |delta_valor_pdd| (excluindo WOP, ja listados acima).
    top_papeis:                  list[DrillPddPapel]
    top_papeis_threshold_brl:    Decimal
    top_papeis_n_solicitado:     int = Field(description="Cap solicitado via query param")
    top_papeis_total_acima_threshold: int = Field(
        description="Quantos papeis passaram o filtro |delta| > threshold (pode ser > top_n)"
    )


# ── DRILL CPR ───────────────────────────────────────────────────────────────


CprNaturezaKey = Literal[
    "diferimento",
    "apropriacao_taxa",
    "apropriacao_despesa",
    "iof_ir",
    "aporte_engaiolado",
    "outros",
]


class DrillCprLinha(BaseModel):
    """1 linha do CPR (D-1 e/ou D0) com classificacao de natureza."""

    descricao:           str
    historico_traduzido: str
    valor_d1:            Decimal
    valor_d0:            Decimal
    delta_valor:         Decimal = Field(description="valor_d0 - valor_d1")
    natureza:            CprNaturezaKey


class DrillCprNaturezaGroup(BaseModel):
    """Agrupamento por natureza com top lines do grupo."""

    natureza:        CprNaturezaKey
    label:           str = Field(description="Label pt-BR amigavel (ex.: 'Diferimento de despesa')")
    qtd_linhas:      int
    sum_valor_d1:    Decimal
    sum_valor_d0:    Decimal
    sum_delta:       Decimal
    top_linhas:      list[DrillCprLinha] = Field(
        description="Top N linhas do grupo ordenadas por |delta_valor| DESC"
    )


class DrillCprAporteEngaiolado(BaseModel):
    """Evento de aporte engaiolado detectado.

    Caracteristica: linha de aporte (descricao iniciando em 'Aporte') aparece
    em D0 + linha de provisao de devolucao no mesmo dia com valor de mesma
    magnitude oposta — neutraliza o caixa. Caso REALINVEST 07-13/05/2026 e
    o exemplo canonico.
    """

    descricao_aporte:               str
    valor_aporte:                   Decimal
    descricao_provisao_devolucao:   str | None = None
    valor_provisao:                 Decimal | None = None
    impacto_liquido:                Decimal = Field(
        description="valor_aporte + valor_provisao (esperado ~0)"
    )


class DrillCprResponse(BaseModel):
    """Drill da categoria CPR (Contas a Pagar e Receber)."""

    fundo_id:               str
    fundo_nome:             str
    data:                   date
    data_anterior:          date

    # Totais (sinal natural — despesas vem negativas, receitas positivas)
    cpr_total_d1:           Decimal
    cpr_total_d0:           Decimal
    cpr_total_delta:        Decimal

    qtd_linhas_d1:          int
    qtd_linhas_d0:          int

    naturezas:              list[DrillCprNaturezaGroup]

    aportes_engaiolados:    list[DrillCprAporteEngaiolado]
