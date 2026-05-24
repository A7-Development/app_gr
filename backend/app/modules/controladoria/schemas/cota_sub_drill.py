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


class DrillDcMutacaoPapel(BaseModel):
    """Papel da populacao constante com MUDANCA DE PARAMETRO entre D-1 e D0.

    Mutacao silenciosa = title presente nos 2 dias (nao-WOP nos 2 dias) cujo
    `valor_nominal`, `taxa_recebivel` ou `data_vencimento_ajustada` mudou
    sem evento de liquidacao/aquisicao correspondente. Eh o sintoma que a
    F5 (project_detector_mutacao_silenciosa) deveria detectar como
    monitoria paralela — aqui passa a ser RESULTADO NATURAL da decomposicao.

    Caso canonico: DID99746 (SYSTEMPACK->BPM) entre 10/04 e 13/04 teve
    valor_nominal cair R$ 22.795 (-17,5%) sem evento.
    """

    cedente_doc:                str
    cedente_nome:               str
    sacado_doc:                 str
    sacado_nome:                str
    seu_numero:                 str
    numero_documento:           str
    tipo_recebivel:             str
    vp_d1:                      Decimal
    vp_d0:                      Decimal
    delta_vp:                   Decimal = Field(description="vp_d0 - vp_d1")
    vn_d1:                      Decimal
    vn_d0:                      Decimal
    taxa_d1:                    Decimal
    taxa_d0:                    Decimal
    venc_d1:                    date | None = None
    venc_d0:                    date | None = None
    mudou_vn:                   bool = Field(description="valor_nominal diferente entre D-1 e D0")
    mudou_taxa:                 bool = Field(description="taxa_recebivel diferente")
    mudou_venc:                 bool = Field(description="data_vencimento_ajustada diferente")


class DrillDcMigracaoWopPapel(BaseModel):
    """Papel que MIGROU PARA WOP entre D-1 e D0.

    Em D-1 estava em faixa != 'WOP' (parte do estoque normal); em D0 esta
    em 'WOP'. Saiu da DC consolidada porque WOP eh segregado (mas o papel
    permanece no granular com PDD em 100% do VP). Efeito liquido no PL Sub
    Jr eh zero (sai de DC + sai de PDD = neutralizam).
    """

    cedente_doc:        str
    cedente_nome:       str
    sacado_doc:         str
    sacado_nome:        str
    seu_numero:         str
    numero_documento:   str
    tipo_recebivel:     str
    faixa_pdd_d1:       str = Field(description="Faixa de origem (A-H, exceto WOP)")
    vp_d1:              Decimal = Field(description="VP em D-1 (sai do estoque)")
    valor_pdd_d1:       Decimal = Field(description="PDD em D-1 (sai junto)")


class DrillDcDecomposicao(BaseModel):
    """Decomposicao do ΔDC entre D-1 e D0, calculada do granular ex-WOP.

    Identidade contabil (deve sempre fechar, residuo ~0):

        saldo_d0 = saldo_d1
                 + aquisicoes_total      (entradas: papeis novos em D0)
                 - liquidacoes_total     (saidas: papeis ausentes em D0, pelo VP_d1)
                 - migracao_wop_total    (papeis que viraram WOP, saem do estoque)
                 + apropriacao_total     (juros do dia, populacao constante sem mudanca)
                 + mutacao_total         (delta VP de papeis com mudanca de parametro)
                 + residuo               (deve ser ~0; se != 0 alerta de pipeline)

    Cross-check informativo com `wh_aquisicao_recebivel` e
    `wh_liquidacao_recebivel`: a diferenca entre o granular (calculado
    aqui) e os eventos publicados pela QiTech em endpoints proprios deve
    ser ~0. Quando diverge, sinaliza desalinhamento entre o snapshot
    estoque e os eventos do dia.
    """

    saldo_d1:                       Decimal = Field(description="Σ VP granular ex-WOP em D-1")
    saldo_d0:                       Decimal = Field(description="Σ VP granular ex-WOP em D0")
    delta_saldo:                    Decimal = Field(description="saldo_d0 - saldo_d1")

    aquisicoes_n:                   int
    aquisicoes_total:               Decimal = Field(description="Σ VP_d0 dos papeis em D0 \\ D-1")

    liquidacoes_n:                  int
    liquidacoes_total:              Decimal = Field(description="Σ VP_d1 dos papeis em D-1 \\ D0")

    migracao_wop_n:                 int
    migracao_wop_total:             Decimal = Field(description="Σ VP_d1 dos papeis que viraram WOP")

    apropriacao_n:                  int
    apropriacao_total:              Decimal = Field(description="Σ ΔVP da populacao constante sem mudanca de parametro (= juros + valorizacao MtM)")

    mutacao_n:                      int
    mutacao_total:                  Decimal = Field(description="Σ ΔVP da populacao constante COM mudanca de parametro (valor_nominal/taxa/venc) — F5 implicito")

    residuo:                        Decimal = Field(description="Esperado ~0; > R$ 1 indica desalinhamento")

    # Cross-check informativo
    cross_check_aquisicoes_evento:  Decimal | None = Field(
        default=None,
        description="Σ valor_compra de wh_aquisicao_recebivel (publicado pela QiTech)",
    )
    cross_check_liquidacoes_evento: Decimal | None = Field(
        default=None,
        description="Σ valor_aquisicao de wh_liquidacao_recebivel (publicado pela QiTech)",
    )
    cross_check_diff_aquisicoes:    Decimal | None = Field(
        default=None,
        description="granular - evento; ~0 esperado",
    )
    cross_check_diff_liquidacoes:   Decimal | None = Field(
        default=None,
        description="granular - evento; ~0 esperado",
    )


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

    # Apropriacao residual (legacy) — mantida para compat com UI antiga.
    # UI nova consome `decomposicao` abaixo (calculo direto pelo granular).
    apropriacao:         DrillDcApropriacao

    # F2 redesign 2026-05-24: decomposicao em 5 buckets a partir do granular.
    decomposicao:        DrillDcDecomposicao
    mutacao_papeis:      list[DrillDcMutacaoPapel] = Field(
        default_factory=list,
        description="Detalhe do bucket Mutacao (top N por |delta_vp|)",
    )
    migracao_wop_papeis: list[DrillDcMigracaoWopPapel] = Field(
        default_factory=list,
        description="Detalhe do bucket Migracao WOP",
    )


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

    # PDD consolidado (do _sum_pdd refatorado em F1 2026-05-24) — agora
    # granular ex-WOP, alinhado com a fonte do balanco. Mantido com este nome
    # por retrocompat com o frontend ate F4 do redesign.
    pdd_consolidado_d1:          Decimal
    pdd_consolidado_d0:          Decimal
    pdd_consolidado_delta:       Decimal

    # Σ valor_pdd da granular -- 3 dimensoes:
    #   pdd_granular_*       = TOTAL (inclui WOP, mantido por retrocompat)
    #   pdd_granular_ex_wop_* = Σ apenas faixas A-H (= contribuicao real ao PL)
    #   pdd_granular_wop_*   = Σ apenas WOP (= ja fora do PL, informativo)
    pdd_granular_d1:             Decimal
    pdd_granular_d0:             Decimal
    pdd_granular_ex_wop_d1:      Decimal = Field(
        default=Decimal("0"),
        description="Σ valor_pdd dos papeis em faixas A-H (exclui WOP) em D-1",
    )
    pdd_granular_ex_wop_d0:      Decimal = Field(
        default=Decimal("0"),
        description="Σ valor_pdd dos papeis em faixas A-H (exclui WOP) em D0",
    )
    pdd_granular_wop_d1:         Decimal = Field(
        default=Decimal("0"),
        description="Σ valor_pdd dos papeis em WOP em D-1 (informativo — ja fora do PL)",
    )
    pdd_granular_wop_d0:         Decimal = Field(
        default=Decimal("0"),
        description="Σ valor_pdd dos papeis em WOP em D0 (informativo — ja fora do PL)",
    )

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
    "provisao_liquidacao",
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
    """Aporte engaiolado no CPR - rubrica `Aporte` com saldo nao-zero.

    Validacao empirica (2026-05-23, F2): NAO existe rubrica
    `Provisao Devolucao Aporte` parando no mesmo dia no CPR. A memoria do
    projeto descrevia esse pareamento mas o dado nao confirma. O que de
    fato acontece em REALINVEST:

      1. Rubrica `Aporte` aparece num dia com valor negativo (-R$ X)
      2. Persiste no CPR por N dias uteis
      3. Some quando aporte e devolvido OU integralizado em alguma classe

    O detector rastreia 3 estados (transicoes entre D-1 e D0):

      - `entrou`     -> apareceu em D0 sem existir em D-1 (saiu de zero)
      - `devolvido`  -> existia em D-1 e sumiu em D0 (foi resolvido)
      - `persiste`   -> esta em D-1 e D0 (continua engaiolado, informativo)

    Impacto no PL Sub: neutro enquanto persiste (CPR ja entra como passivo
    no balanco). Caso REALINVEST 07-14/05 e canonico: -R$ 124.500 persistiu
    por 5 dias uteis e sumiu em 15/05.
    """

    descricao:    str
    estado:       Literal["entrou", "devolvido", "persiste"]
    valor_d1:     Decimal = Field(description="Saldo no CPR em D-1")
    valor_d0:     Decimal = Field(description="Saldo no CPR em D0")
    delta_valor:  Decimal = Field(description="valor_d0 - valor_d1")


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
