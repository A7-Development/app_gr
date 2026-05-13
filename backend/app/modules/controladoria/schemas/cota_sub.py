"""Pydantic schemas — Controladoria · Cota Sub.

Espelho do contrato TypeScript em
`frontend/src/app/(app)/controladoria/cota-sub/page.tsx::VariacaoDiariaResponse`.

A planilha origem (VariacaoDeCota_Preenchida.xlsx, aba Analise) decompoe a
variacao do PL Sub Jr entre D-1 e D0 por categoria de ativo + atribui as
parcelas a "causas" (apropriacao vs movimento).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

PlCategoriaKey = Literal[
    "compromissada",
    "mezanino",
    "senior",
    "titulos_publicos",
    "fundos_di",
    "dc",
    "op_estruturadas",
    "outros_ativos",
    "pdd",
    "cpr",
    "tesouraria",
]


class PlCategoria(BaseModel):
    """Linha 16/20 da planilha — uma categoria de ativo no PL."""

    key:    PlCategoriaKey
    label:  str
    d1:     Decimal = Field(description="Valor em D-1 (R$)")
    d0:     Decimal = Field(description="Valor em D0 (R$)")
    delta:  Decimal = Field(description="d0 - d1")
    source: str     = Field(description="Tabela canonica origem")


DecomposicaoSinal = Literal["ganho", "prejuizo", "neutro"]


class DecomposicaoItem(BaseModel):
    """Painel C27:D35 da planilha — atribuicao da variacao a uma causa."""

    key:   str
    label: str
    valor: Decimal
    sinal: DecomposicaoSinal


class ApropriacaoDcLinha(BaseModel):
    """Bloco 'a vencer' OU 'vencidos' da aba APROPRIACAO DC."""

    estoque_d1:  Decimal = Field(description="Estoque D-1 (valor presente)")
    aquisicoes:  Decimal = Field(description="Aquisicoes consolidadas no periodo")
    liquidados:  Decimal = Field(description="Liquidados no periodo (negativo = saida)")
    estoque_d0:  Decimal = Field(description="Estoque D0 (valor presente)")
    apropriacao: Decimal = Field(
        description="estoque_d0 - (estoque_d1 + aquisicoes + liquidados)",
    )


class ApropriacaoDc(BaseModel):
    """Aba APROPRIACAO DC inteira (a vencer + vencidos + total)."""

    a_vencer: ApropriacaoDcLinha
    vencidos: ApropriacaoDcLinha
    total:    Decimal = Field(description="a_vencer.apropriacao + vencidos.apropriacao")


class CprMovimentoItem(BaseModel):
    """Linha individual da aba CPR (descricao + valor)."""

    descricao: str
    valor:     Decimal


class CprDetalhado(BaseModel):
    """Aba CPR completa — listas de receber/pagar D-1 e D0 + variacao."""

    receber_d1: list[CprMovimentoItem]
    receber_d0: list[CprMovimentoItem]
    pagar_d1:   list[CprMovimentoItem]
    pagar_d0:   list[CprMovimentoItem]
    total_d1:   Decimal = Field(description="receber - pagar em D-1")
    total_d0:   Decimal = Field(description="receber - pagar em D0")
    variacao:   Decimal = Field(description="total_d0 - total_d1 (entra como D30 da Analise)")


class VariacaoDiariaResponse(BaseModel):
    """Resposta do endpoint GET /controladoria/cota-sub/variacao-diaria."""

    fundo_id:           str       = Field(description="UUID da Unidade Administrativa")
    fundo_nome:         str
    data:               date      = Field(description="D0 (dia analisado)")
    data_anterior:      date      = Field(description="D-1 (dia util anterior)")
    pl_d1:              Decimal
    pl_d0:              Decimal
    pl_delta:           Decimal   = Field(description="pl_d0 - pl_d1")
    pl_delta_pct:       Decimal   = Field(description="pl_delta / pl_d1 (fracao decimal)")
    categorias:         list[PlCategoria]
    decomposicao:       list[DecomposicaoItem]
    decomposicao_total: Decimal
    divergencia:        Decimal   = Field(description="decomposicao_total - pl_delta (deve ser ~0)")
    apropriacao_dc:     ApropriacaoDc
    cpr_detalhado:      CprDetalhado


# ── Balanco · otica Sub Jr ──────────────────────────────────────────────────

BalanceRowType = Literal["section", "line", "subtotal", "total"]


class BalanceRow(BaseModel):
    """Linha do balanco.

    - `type='line'` tem cosif/source e pode ter `sub_rows` populadas (1 nivel de
      detalhamento por dimensao util da fonte: papel, codigo, emitente, etc.)
    - `type='section'`/'subtotal'/'total' nao tem cosif nem subRows
    - Sub-rows sao filhas de uma `line` e seguem o mesmo schema (recursivo).
    """

    id:        str
    type:      BalanceRowType
    label:     str
    cosif:     str | None = None
    descricao: str | None = Field(
        default=None,
        description="Descricao da origem na silver (ex.: 'CC - BRADESCO', 'Saldo em Tesouraria').",
    )
    source:    str | None = Field(default=None, description="Tabela(s) silver origem + filtro")
    d1:        Decimal | None = None
    d0:        Decimal | None = None
    delta:     Decimal | None = Field(default=None, description="d0 - d1")
    sub_rows:  list[BalanceRow] | None = Field(
        default=None,
        alias="subRows",
        description="Detalhamento da linha por dimensao util (papel, banco, emitente, etc.)",
    )

    model_config = {"populate_by_name": True}


BalanceRow.model_rebuild()


class BalancoResponse(BaseModel):
    """Resposta do endpoint GET /controladoria/cota-sub/balanco.

    Balanco patrimonial diario na otica do cotista subordinado:
      ATIVO (8 linhas) + Subtotal Ativo
      PASSIVO (3 linhas: CPR, Cota Mez, Cota Sr) + Subtotal Passivo
      = Cota Subordinada (residual)

    Todas as fontes vem de silver canonico (CLAUDE.md §13.2.1).
    """

    fundo_id:      str  = Field(description="UUID da Unidade Administrativa")
    fundo_nome:    str
    data:          date = Field(description="D0 (dia analisado)")
    data_anterior: date = Field(description="D-1 (dia util anterior)")
    rows:          list[BalanceRow]


# ── Variacoes do Dia · auditoria de movimentos do PL ────────────────────────


class VariacaoItem(BaseModel):
    """Item individual em apropriacao / pagamento / anomalia."""

    cosif:     str | None = Field(default=None, description="COSIF analitico (quando aplicavel)")
    label:     str = Field(description="Categoria (Cobranca, Consultoria, etc.)")
    historico: str | None = Field(default=None, description="historico_traduzido da silver")
    descricao: str | None = Field(default=None, description="descricao textual da silver")
    valor:     Decimal


class ConferenciaVariacao(BaseModel):
    """Sanity-check do regime de competencia."""

    delta_passivo_contabil: Decimal = Field(description="ΔSubtotal Passivo Contabil entre D-1 e D0")
    soma_apropriacoes:      Decimal = Field(description="Σ apropriacoes do dia")
    divergencia:            Decimal = Field(description="delta - soma. Deve ser ~0 se regime de competencia esta consistente")
    ok:                     bool = Field(description="True se |divergencia| < 0,01")


class VariacoesDiaResponse(BaseModel):
    """Resposta do endpoint GET /controladoria/cota-sub/variacoes-dia.

    Decompoe o Δ do PL Sub Jr entre D-1 e D0 em 3 movimentos:
      1. Apropriacoes (provisoes diarias do CPR — regime competencia)
      2. Pagamentos efetivados (saidas em wh_movimento_caixa)
      3. Anomalias (pagamentos sem provisao previa — possivel fraude/erro)

    Cruza wh_cpr_movimento (D-1 vs D0) com wh_movimento_caixa (D0) por
    similaridade de descricao para identificar pagamentos sem provisao.
    """

    fundo_id:      str
    data:          date
    data_anterior: date

    apropriacoes:        list[VariacaoItem]
    apropriacoes_total:  Decimal

    pagamentos:          list[VariacaoItem]
    pagamentos_total:    Decimal

    anomalias:           list[VariacaoItem]

    conferencia:         ConferenciaVariacao


# ── Explainers heuristicos da variacao ──────────────────────────────────────
#
# Cada categoria que se materializa vira uma `Explanation` na lista
# `explanations` da resposta. Por ora so PDD esta implementada; demais
# categorias (MTM, Aporte, Resgate, Diferimento, Liquidacao, Aquisicao)
# entrarao em PRs incrementais reusando o contrato. Ver
# `backend/docs/cota-sub-explainers-heuristicos.md`.


ExplainerCategoria = Literal[
    "pdd",
    "mtm",
    "aporte",
    "movimento_cotas",
    "diferimento",
    "liquidacao",
    "aquisicao",
]


class PddEvidencia(BaseModel):
    """1 papel cujo `valor_pdd` mexeu entre D-1 e D0."""

    cedente_doc:              str
    cedente_nome:             str
    sacado_doc:               str
    sacado_nome:              str
    seu_numero:               str
    numero_documento:         str
    tipo_recebivel:           str
    data_vencimento_ajustada: date | None
    valor_pdd_d1:             Decimal
    valor_pdd_d0:             Decimal
    delta_valor_pdd:          Decimal = Field(description="valor_pdd_d0 - valor_pdd_d1")
    faixa_pdd_d1:             str | None
    faixa_pdd_d0:             str | None


class PddExplanation(BaseModel):
    """Categoria 3.2 — variacao de PDD por papel."""

    categoria:           ExplainerCategoria = "pdd"
    narrative:           str       = Field(description="Texto pronto pra UI (pt-BR)")
    delta_brl:           Decimal   = Field(description="-Σ Δ valor_pdd (PDD sobe → PL Sub cai)")
    evidencias_total:    int       = Field(description="Total de papeis com Δ acima do threshold")
    evidencias_mostradas: int      = Field(description="Quantos vieram em `evidencias` (top_n)")
    outros_delta_brl:    Decimal   = Field(description="Σ dos papeis nao mostrados (fora do top_n)")
    evidencias:          list[PddEvidencia]


class ExplicacaoVariacaoResponse(BaseModel):
    """Resposta do endpoint GET /controladoria/cota-sub/explicacao.

    Lista de explainers que materializaram. Por ora so PDD; demais entram
    em PRs incrementais sem quebrar o contrato.
    """

    fundo_id:           str
    data:               date
    data_anterior:      date
    delta_pl_sub:       Decimal
    threshold_brl:      Decimal   = Field(description="Threshold usado pra filtrar evidencias")
    top_n:              int       = Field(description="Cap de evidencias mostradas por categoria")
    explanations:       list[PddExplanation] = Field(
        description="Categorias materializadas. Vazio = nada matchou ou variacoes < threshold."
    )
    indeterminado_brl:  Decimal   = Field(description="Δ PL Sub - Σ delta_brl dos explainers")
