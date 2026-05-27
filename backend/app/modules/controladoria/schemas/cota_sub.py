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
from typing import Annotated, Literal

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


class DriverResultOut(BaseModel):
    """Driver canonico da Cota Sub (Fase 3b do refactor de proveniencia, 2026-05-18).

    Espelha `cota_sub_drivers.compute.DriverResult`. Cada driver e uma
    decomposicao parcial do ΔPL Sub no metodo do gestor REALINVEST.

    Σ drivers (excluindo indeterminados) ≈ ΔPL_Sub_MEC.
    Residuo = ΔPL_Sub_MEC − Σ drivers (exposto sempre, sem threshold).
    """

    metric_global_id:    str         = Field(description="ex.: controladoria.cota_sub.driver.pdd")
    label:               str
    formula_description: str
    valor_brl:           Decimal     = Field(description="Impacto liquido no PL Sub")
    valor_d_prev:        Decimal | None = None
    valor_d0:            Decimal | None = None
    endpoints_required:  list[str]   = Field(default_factory=list)
    indeterminado_por_dado: bool     = False
    motivo_indeterminado: str | None = None
    endpoints_unavailable: list[str] = Field(default_factory=list)

    # Evidencias especializadas por tipo de heuristica (Fase 4b, 2026-05-18).
    # Cada driver popula 0-1 campo. Frontend renderiza condicional ao tipo
    # de evidencia presente. Quando o numero crescer, refactor pra
    # discriminated union (kind="pdd"|"mtm"|...).
    pdd_evidencias: list[PddEvidencia] = Field(
        default_factory=list,
        description="Papel-a-papel onde |Δvalor_pdd| > R$ 100, top 20. So preenchido para driver PDD.",
    )
    mtm_evidencias: list[MtmEvidencia] = Field(
        default_factory=list,
        description="Papel-a-papel agregado por codigo_lastro (qtd estavel, MtM puro). So preenchido para driver Titulos Publicos.",
    )
    cpr_evidencias: list[EvidenciaCprLinha] = Field(
        default_factory=list,
        description="Linhas do CPR (apropriacao + diferimento) com |Δvalor| > R$ 100. So preenchido para driver Apropriacao Despesas.",
    )
    remuneracao_evidencias: list[RemuneracaoSrMezEvidencia] = Field(
        default_factory=list,
        description="Valorizacao da classe (PL d-1/d0, valor_cota, impacto_pl_sub). So preenchido para drivers Senior / Mezanino.",
    )
    movimento_carteira_evidencias: list[MovimentoCarteiraEvidencia] = Field(
        default_factory=list,
        description=(
            "Papeis adquiridos/liquidados entre D-1 e D0 com valor > R$ 100. "
            "Driver Apropriacao DC: INFORMACIONAL (não compõe valor_brl). "
            "Frontend renderiza como sub-secao 'Atividade do dia'."
        ),
    )
    saldo_tesouraria_evidencias: list[SaldoTesourariaEvidencia] = Field(
        default_factory=list,
        description=(
            "1 linha por conta que compoe o saldo de tesouraria do fundo "
            "(D-1 → D0). So preenchido para driver Tesouraria. "
            "Σ deltas = valor_brl do driver."
        ),
    )
    apropriacao_dc_evidencias: list[ApropriacaoDcEvidencia] = Field(
        default_factory=list,
        description=(
            "4 inputs da fórmula Apropriação = ΔEstoque - Aq + Liq. "
            "So preenchido para driver Apropriacao DC. "
            "Σ valor_brl = valor_brl do driver."
        ),
    )
    evidencias_indisponiveis_motivo: str | None = Field(
        default=None,
        description=(
            "Quando o granular (papel-a-papel) nao pode ser computado por dado "
            "upstream ausente (ex.: wh_estoque_recebivel vazio em D-1 ou D0), "
            "este campo carrega uma explicacao curta. Driver continua valido "
            "(vem do consolidado MEC); evidencias_*[] ficam vazias. Frontend "
            "renderiza este texto no lugar da lista."
        ),
    )


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

    # Novo (Fase 3b, 2026-05-18): catalog-backed drivers + residuo expostos
    # paralelos a `decomposicao` legacy. Frontend pode migrar incrementalmente.
    # Ver `app/modules/controladoria/services/cota_sub_drivers/` e memos
    # `project_cota_sub_metodo_gestor` + `project_cota_sub_drivers_canonicos`.
    drivers:            list[DriverResultOut] = Field(
        default_factory=list,
        description="11 drivers canonicos do metodo do gestor. Vazio em respostas legacy.",
    )
    soma_drivers:       Decimal = Field(
        default=Decimal("0"),
        description="Σ drivers (excluindo indeterminados)",
    )
    residuo_modelo:     Decimal = Field(
        default=Decimal("0"),
        description="pl_delta − soma_drivers. Sem threshold; valor exato exposto.",
    )


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


# ── Explainers da variacao da Cota Sub ───────────────────────────────────────
#
# Refactor 2026-05-17: cada categoria PARTICIONA contas COSIF do balancete.
# `delta_brl` de cada Explanation = Σ Δ folhas COSIF mapeadas pro bucket
# (matematica, nao heuristica). Σ buckets ≡ ΔPL contabil POR CONSTRUCAO.
#
# Heuristicas (PDD/CPR diff, MtM por codigo_lastro, Fluxo MEC) param de
# calcular delta_brl e viram ENRIQUECEDORAS de `evidencias[]` — puxam
# cedente/sacado/papel/historico pra dar narrativa rica. Onde nao cobrir,
# o `cosif_origin[]` mostra as folhas COSIF cruas pra auditoria.


ExplainerCategoria = Literal[
    "pdd",
    "mtm",
    "aporte",
    "movimento_cotas",
    "diferimento",
    "apropriacao",
    "liquidacao",
    "aquisicao",
    "remuneracao_sr_mez",
    "outros",
]


class CosifOrigem(BaseModel):
    """1 conta COSIF folha mapeada pro bucket — fonte contabil do delta_brl.

    Toda categoria tem `cosif_origin: list[CosifOrigem]`. O `delta_brl` do
    bucket = Σ delta dessas linhas. Permite auditar exatamente DE ONDE
    contabilmente vem o impacto, antes mesmo de qualquer heuristica de
    enriquecimento.
    """

    codigo:    str       = Field(description="Codigo COSIF da conta folha")
    nome:      str       = Field(description="Nome da conta no plano COSIF")
    d_minus_1: Decimal
    d_zero:    Decimal
    delta:     Decimal   = Field(description="d_zero - d_minus_1 (com sinal contabil natural)")


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
    valor_nominal:            Decimal = Field(
        description="Valor nominal do recebivel (D0; fallback D-1). Permite estimar quanto falta de PDD constituir."
    )
    valor_pdd_d1:             Decimal
    valor_pdd_d0:             Decimal
    delta_valor_pdd:          Decimal = Field(description="valor_pdd_d0 - valor_pdd_d1")
    faixa_pdd_d1:             str | None
    faixa_pdd_d0:             str | None


class PddExplanation(BaseModel):
    """Categoria 3.2 — variacao de PDD por papel.

    `delta_brl` (refactor 2026-05-17) = Σ Δ folhas COSIF `1.6.9.97.*`
    (provisao para devedores duvidosos). Heuristica de diff de
    `wh_estoque_recebivel` continua viva mas APENAS pra enriquecer
    `evidencias[]` (cedente/sacado/papel/faixa).
    """

    categoria:           Literal["pdd"] = "pdd"
    narrative:           str       = Field(description="Texto pronto pra UI (pt-BR)")
    delta_brl:           Decimal   = Field(description="Σ Δ folhas COSIF do bucket (fonte: balancete)")
    evidencias_total:    int       = Field(description="Total de papeis com Δ acima do threshold")
    evidencias_mostradas: int      = Field(description="Quantos vieram em `evidencias` (top_n)")
    outros_delta_brl:    Decimal   = Field(description="Σ dos papeis nao mostrados (fora do top_n)")
    evidencias:          list[PddEvidencia]
    cosif_origin:        list[CosifOrigem] = Field(
        default_factory=list,
        description="Folhas COSIF do bucket — fonte contabil do delta_brl",
    )


class EvidenciaCprLinha(BaseModel):
    """1 rubrica do CPR cujo valor mexeu entre D-1 e D0.

    Generica — usada por Diferimento e Apropriacao. Sem cedente/papel
    (rubrica de CPR e estrutural do fundo, nao tem entidade associada).
    """

    descricao:           str       = Field(description="`descricao` original do CPR (longa, com data de venc/pagto)")
    historico_traduzido: str       = Field(description="`historico_traduzido` (label curta apresentavel)")
    valor_d1:            Decimal   = Field(description="Saldo CPR em D-1 (R$)")
    valor_d0:            Decimal   = Field(description="Saldo CPR em D0 (R$)")
    delta_valor:         Decimal   = Field(description="valor_d0 - valor_d1 (em R$)")


class DiferimentoExplanation(BaseModel):
    """Categoria 3.3.a — apropriacao mensal de despesas diferidas (CVM, Rating, ANBIMA).

    Detecta linhas com `descricao` iniciando em 'Diferimento de despesa'
    no CPR. Sub absorve a amortizacao: linha diferida diminui em modulo
    a cada dia (rubrica positiva caindo) -> PL Sub cai.
    """

    categoria:           Literal["diferimento"] = "diferimento"
    narrative:           str
    delta_brl:           Decimal   = Field(description="Σ Δ folhas COSIF do bucket Ajustes contabeis (parcela diferimento)")
    evidencias_total:    int
    evidencias_mostradas: int
    outros_delta_brl:    Decimal
    evidencias:          list[EvidenciaCprLinha]
    cosif_origin:        list[CosifOrigem] = Field(default_factory=list)


class ApropriacaoExplanation(BaseModel):
    """Categoria 3.3.b — apropriacao de despesas/taxas operacionais do dia.

    Cobre Taxa de Adm/Custodia/Gestao Apropriada, Despesa de %,
    'a Pagar em %', IOF/IR a Recolher, REGISTRADORA, Despesas com %.
    Sub absorve sempre (despesa do fundo cai no resultado).
    """

    categoria:           Literal["apropriacao"] = "apropriacao"
    narrative:           str
    delta_brl:           Decimal   = Field(description="Σ Δ folhas COSIF do bucket Ajustes contabeis (parcela apropriacao)")
    evidencias_total:    int
    evidencias_mostradas: int
    outros_delta_brl:    Decimal
    evidencias:          list[EvidenciaCprLinha]
    cosif_origin:        list[CosifOrigem] = Field(default_factory=list)


# ── Fluxo de caixa do cotista (categoria 1.1 + 1.2) ──────────────────────────


ClasseCotaKey = Literal["sub_jr", "mezanino", "senior"]


class FluxoCaixaEvidencia(BaseModel):
    """1 movimento de aporte ou resgate em uma classe de cota.

    Sinal de `impacto_pl_sub` segue a equacao:
      Sub = Ativo - Passivo Contabil - Equity (Mez + Sr)

    - Aporte Sub      -> +impacto (Sub absorve direto, PL Sub cresce)
    - Resgate Sub     -> -impacto
    - Aporte Mez/Sr   -> -impacto (cresce equity, Sub residual cai)
    - Resgate Mez/Sr  -> +impacto (equity reduz, Sub residual sobe)
    """

    tipo:           Literal["aporte", "resgate"]
    classe:         ClasseCotaKey
    classe_label:   str       = Field(description="Label amigavel da classe (ex.: 'Subordinada Jr', 'Mezanino', 'Senior')")
    valor_brl:      Decimal   = Field(description="Valor do MEC (aporte ou retirada) - sempre positivo")
    delta_qtd:      Decimal   = Field(description="Δ quantidade de cotas D0 - D-1 da classe")
    valor_cota_d0:  Decimal   = Field(description="Valor da cota em D0")
    impacto_pl_sub: Decimal   = Field(description="Impacto liquido no PL Sub (com sinal coerente)")


class EventoOperacionalEvidencia(BaseModel):
    """Evento operacional de caixa sem impacto no PL Sub.

    Caso canonico: aporte engaiolado (CPR `Aporte` com linha de provisao
    de devolucao criada no mesmo dia, sem integralizacao em nenhuma classe).
    Provisao neutraliza o caixa → impacto liquido = 0. Veja caso REALINVEST
    07-13/05/2026 documentado no memory.
    """

    tipo:        Literal["aporte_engaiolado", "devolucao_engaiolado"]
    descricao:   str       = Field(description="`descricao` original do CPR")
    valor_brl:   Decimal   = Field(description="Valor absoluto em R$ envolvido")
    detalhe:     str | None = Field(default=None, description="Texto explicativo curto")


class FluxoCaixaExplanation(BaseModel):
    """Categoria 1.1 + 1.2 — fluxo de caixa do cotista.

    Detecta aporte/resgate em qualquer classe (Sub Jr, Mezanino, Senior)
    a partir do MEC. Sub absorve direto (aporte Sub = +PL Sub); Mez/Sr
    afetam Sub via equity (aporte Mez = -PL Sub por exclusao).

    Eventos operacionais (aporte engaiolado, devolucao) entram em
    `eventos_operacionais` SEM somar em `delta_brl` - sao informativos
    mas neutros pra equacao de PL.
    """

    categoria:            Literal["fluxo_caixa"] = "fluxo_caixa"
    narrative:            str
    delta_brl:            Decimal   = Field(description="Σ Δ classe Sub em 6.1.1.70.* (aporte/resgate da Cota Sub propria)")
    evidencias:           list[FluxoCaixaEvidencia] = Field(
        description="Aporte/Resgate com impacto no PL Sub"
    )
    eventos_operacionais: list[EventoOperacionalEvidencia] = Field(
        default_factory=list,
        description="Eventos sem impacto no PL Sub (aporte engaiolado, devolucao)",
    )
    cosif_origin:         list[CosifOrigem] = Field(default_factory=list)


# ── Movimento de carteira (categoria 2.1 + 2.2) ──────────────────────────────


class MovimentoCarteiraEvidencia(BaseModel):
    """1 papel que entrou ou saiu da carteira entre D-1 e D0.

    `tipo="liquidado"`: papel existia em D-1 e nao existe em D0 (sacado
    pagou ou foi baixado). `valor_brl` = valor_presente do papel em D-1.

    `tipo="adquirido"`: papel novo em D0, nao existia em D-1. `valor_brl`
    = valor_presente do papel em D0.
    """

    tipo:                     Literal["liquidado", "adquirido"]
    cedente_doc:              str
    cedente_nome:             str
    sacado_doc:               str
    sacado_nome:              str
    seu_numero:               str
    numero_documento:         str
    tipo_recebivel:           str
    valor_brl:                Decimal   = Field(description="valor_presente do papel (do dia em que existia)")
    valor_nominal:            Decimal
    data_vencimento_ajustada: date | None = None


class MovimentoCarteiraExplanation(BaseModel):
    """Categoria 2.1 + 2.2 — giro da carteira de direitos creditorios.

    Detecta papeis que entraram (adquiridos) e sairam (liquidados) entre
    D-1 e D0 cruzando `wh_estoque_recebivel` por (seu_numero,
    numero_documento) com FULL OUTER JOIN.

    Bucket INFORMACIONAL: `delta_brl = 0` por construcao. Movimento
    patrimonial neutro no PL Sub (papel liquidado: caixa +X, DC -X →
    net 0). Diferencas residuais (sacado pagou menos que valor presente,
    ganho/perda de liquidacao) caem em PDD ou Apropriacao — buckets
    proprios. Aqui mostramos APENAS a atividade (volume girado, papeis
    movidos) para o controller auditar.

    Quando `delta_brl` do `indeterminado_brl` da resposta global ficar
    grande em dias com so-movimento-de-carteira, e sinal pra migrar pra
    explainer com impacto residual (caixa recebido - valor presente).
    """

    categoria:             Literal["movimento_carteira"] = "movimento_carteira"
    narrative:             str
    delta_brl:             Decimal   = Field(
        default=Decimal("0"),
        description="Σ Δ folhas COSIF: bancos (1.1.2.*) + recebiveis (1.6.1.30.*) + transito + conciliacao",
    )
    total_liquidado_brl:   Decimal   = Field(description="Σ valor_presente dos papeis liquidados (em D-1)")
    total_adquirido_brl:   Decimal   = Field(description="Σ valor_presente dos papeis adquiridos (em D0)")
    papeis_liquidados:     int
    papeis_adquiridos:     int
    evidencias_mostradas:  int       = Field(description="Quantos vieram em `evidencias` (top_n total)")
    evidencias:            list[MovimentoCarteiraEvidencia] = Field(
        description="Top N papeis movidos no dia, ordenados por |valor_brl| DESC"
    )
    cosif_origin:          list[CosifOrigem] = Field(default_factory=list)


# ── Saldo Tesouraria (driver Tesouraria, 2026-05-19) ────────────────────────


class SaldoTesourariaEvidencia(BaseModel):
    """1 conta que compõe o saldo de tesouraria do fundo (D-1 → D0).

    Reflete o "estoque" no fim do dia, não o fluxo. Cada evidência é uma
    fonte: `wh_saldo_tesouraria` (cash residual da QiTech por classe) ou
    `wh_saldo_conta_corrente` (contas bancárias reais).

    Σ deltas dessas evidências = valor_brl do driver Tesouraria.

    Exclusões aplicadas (em sintonia com `_sum_tesouraria`):
      - `wh_saldo_tesouraria` MEZANINO/SENIOR (só Sub entra no driver Sub)
      - `wh_saldo_conta_corrente` codigo='CONCILIA' (conta transitória)
    """

    fonte:        str       = Field(description="wh_saldo_tesouraria | wh_saldo_conta_corrente")
    descricao:    str       = Field(description="Nome da conta (ex.: 'Saldo em Tesouraria', 'CC - BRADESCO')")
    codigo:       str | None = Field(default=None, description="Codigo da conta corrente (BRADESCO, SOCOPA, etc) quando aplicavel")
    valor_d_prev: Decimal   = Field(description="Saldo em D-1")
    valor_d0:     Decimal   = Field(description="Saldo em D0")
    delta:        Decimal   = Field(description="valor_d0 - valor_d_prev")


# ── Apropriação DC (driver Apropriação de DC, 2026-05-19) ───────────────────


class ApropriacaoDcEvidencia(BaseModel):
    """1 input da fórmula `Apropriação = ΔEstoque - Aquisições + Liquidações`.

    São 4 evidências por bloco (a_vencer + vencidos, sem duplicar inputs
    quando coincidem). Σ valor_brl dessas evidências = valor_brl do driver
    Apropriação DC.

    Sinais coerentes com a fórmula:
      - bloco='a_vencer' / 'vencidos': valor_brl = ΔEstoque (pode ser + ou -)
      - bloco='aquisicoes': valor_brl = -Aquisições (negativo, sai do caixa)
      - bloco='liquidados': valor_brl = +Liquidações (positivo, retorna ao caixa)
    """

    label:        str   = Field(description="Ex.: 'Estoque a vencer', 'Aquisições do dia'")
    fonte:        str   = Field(description="wh_estoque_recebivel | wh_aquisicao_recebivel | wh_liquidacao_recebivel")
    bloco:        Literal["a_vencer", "vencidos", "aquisicoes", "liquidados"]
    valor_d_prev: Decimal | None = Field(default=None, description="Estoque em D-1 (só para 'a_vencer'/'vencidos')")
    valor_d0:     Decimal | None = Field(default=None, description="Estoque em D0 (só para 'a_vencer'/'vencidos')")
    valor_brl:    Decimal = Field(description="Valor que entra na soma da fórmula (com sinal coerente)")


# ── Marcacao a mercado (categoria 4.1) ───────────────────────────────────────


class MtmEvidencia(BaseModel):
    """1 papel de renda fixa cujo valor mexeu sem variar quantidade.

    `valor_d1`/`valor_d0` sao `valor_bruto` do papel nos dois dias.
    `delta_valor` = valor_d0 - valor_d1 (positivo = papel subiu = Sub sobe).
    `pu_d1`/`pu_d0` sao `pu_mercado` (preco unitario) — auxiliam auditoria
    contra a curva do dia.
    """

    codigo:           str
    nome_do_papel:    str
    emitente:         str
    indexador:        str
    data_vencimento:  date | None
    quantidade:       Decimal   = Field(description="Qtd estavel D-1 e D0 (Δqtd=0 por construcao)")
    valor_d1:         Decimal
    valor_d0:         Decimal
    delta_valor:      Decimal   = Field(description="valor_d0 - valor_d1")
    pu_d1:            Decimal
    pu_d0:            Decimal


class MtmExplanation(BaseModel):
    """Categoria 4.1 — marcacao a mercado de papeis de renda fixa.

    Detecta papeis em `wh_posicao_renda_fixa` com `Δqtd = 0` E `Δvalor_bruto`
    fora de tolerancia entre D-1 e D0. Sub absorve direto: papel subiu →
    Ativo sobe → PL Sub sobe.

    `delta_brl` = Σ Δvalor_bruto dos papeis no top_n + outros. Sinal coerente
    com impacto (positivo = Sub ganhou via mercado).
    """

    categoria:           Literal["mtm"] = "mtm"
    narrative:           str
    delta_brl:           Decimal   = Field(description="Σ Δ folhas COSIF de Renda Fixa (1.2.x TPF + 1.3.1.10/15.* RF + fundos)")
    evidencias_total:    int
    evidencias_mostradas: int
    outros_delta_brl:    Decimal
    evidencias:          list[MtmEvidencia]
    cosif_origin:        list[CosifOrigem] = Field(default_factory=list)


# ── Remuneracao Sr/Mez (categoria 5.1) ───────────────────────────────────────


class RemuneracaoSrMezEvidencia(BaseModel):
    """1 classe de cota nao-Sub cujo PL valorizou (ou desvalorizou) no dia.

    Sub absorve com sinal invertido: PL_Sub = Ativo - Passivo - Equity_Sr -
    Equity_Mez. ΔEquity_Sr/Mez positivo -> impacto -ΔEquity_Sr/Mez no Sub.
    """

    classe:         Literal["senior", "mezanino"]
    classe_label:   str       = Field(description="Label amigavel (ex.: 'Senior', 'Mezanino')")
    pl_d1:          Decimal   = Field(description="Patrimonio da classe em D-1")
    pl_d0:          Decimal   = Field(description="Patrimonio da classe em D0")
    delta_pl:       Decimal   = Field(description="pl_d0 - pl_d1 (positivo = classe valorizou)")
    delta_pct:      Decimal   = Field(description="delta_pl / pl_d1 em pp (fracao decimal)")
    valor_cota_d1:  Decimal
    valor_cota_d0:  Decimal
    impacto_pl_sub: Decimal   = Field(description="-delta_pl (Sub paga a remuneracao)")


class RemuneracaoSrMezExplanation(BaseModel):
    """Categoria 5.1 — remuneracao das cotas Senior e Mezanino.

    Cota Sub absorve o rendimento diario das tranches mais protegidas como
    subordinacao. Fonte: `wh_mec_evolucao_cotas` (campo `patrimonio` por
    classe, D-1 vs D0).

    `delta_brl = -(ΔPL_Sr + ΔPL_Mez)`. Movimento ja descontado de aportes/
    resgates (esses entram em `fluxo_caixa`), entao reflete apenas a
    valorizacao da cota. Operacionalmente: PL_classe_d0 - PL_classe_d1 ja
    captura o aporte/resgate diluido, mas o `fluxo_caixa` capturou o
    `entradas/saidas` em separado — preferir filtrar so dias sem aporte/
    resgate na classe pra evitar dupla contagem, ou subtrair `entradas-saidas`
    do delta_pl. Implementacao escolhida: subtrair entradas-saidas do delta_pl
    da classe (delta_pl_remuneracao = delta_pl - (entradas - saidas)).
    """

    categoria:           Literal["remuneracao_sr_mez"] = "remuneracao_sr_mez"
    narrative:           str
    delta_brl:           Decimal   = Field(description="Σ Δ classe Sr+Mez em 6.1.1.70.* (custo de subordinacao)")
    evidencias:          list[RemuneracaoSrMezEvidencia]
    cosif_origin:        list[CosifOrigem] = Field(default_factory=list)


# ── Outros — folhas COSIF sem mapping definido ───────────────────────────────


class OutrosExplanation(BaseModel):
    """Bucket residual — folhas COSIF que nao casaram com nenhum mapping.

    Em regime estavel deve ser zero (todo COSIF tem bucket). Quando nao for,
    indica COSIF novo no balancete que precisa entrar na tabela de mapping
    em `services/cota_sub/cosif_to_bucket.py`. UI mostra a lista de folhas
    explicitas pra revisao manual.
    """

    categoria:    Literal["outros"] = "outros"
    narrative:    str
    delta_brl:    Decimal           = Field(description="Σ Δ folhas COSIF sem mapping")
    cosif_origin: list[CosifOrigem] = Field(
        description="Folhas COSIF sem mapping definido — adicionar em cosif_to_bucket.py"
    )


# Discriminated union — Pydantic v2 escolhe o tipo via campo `categoria`.
Explanation = Annotated[
    PddExplanation
    | DiferimentoExplanation
    | ApropriacaoExplanation
    | FluxoCaixaExplanation
    | MovimentoCarteiraExplanation
    | MtmExplanation
    | RemuneracaoSrMezExplanation
    | OutrosExplanation,
    Field(discriminator="categoria"),
]


class ExplicacaoVariacaoResponse(BaseModel):
    """Resposta do endpoint GET /controladoria/cota-sub/explicacao.

    Refactor 2026-05-17: `delta_brl` de cada explanation vem da soma das
    folhas COSIF mapeadas pro bucket (matematica, fonte = balancete).
    Σ explanations.delta_brl ≡ `delta_pl_sub_contabil`. Heuristicas continuam
    enriquecendo `evidencias[]` mas nao mais calculam delta_brl.
    """

    fundo_id:                  str
    data:                      date
    data_anterior:             date
    delta_pl_sub:              Decimal   = Field(description="ΔPL Sub apurado pelo MEC (administrador)")
    delta_pl_sub_contabil:     Decimal   = Field(description="ΔPL Sub calculado pelo balancete COSIF")
    divergencia_mec_contabil:  Decimal   = Field(description="delta_pl_sub - delta_pl_sub_contabil. Residuo MEC vs Contabil — quando != 0, ha lancamento sem espelho entre as fontes")
    threshold_brl:             Decimal   = Field(description="Threshold usado pra filtrar evidencias")
    top_n:                     int       = Field(description="Cap de evidencias mostradas por categoria")
    explanations:              list[Explanation] = Field(
        description="Buckets COSIF particionados. Σ delta_brl ≡ delta_pl_sub_contabil."
    )
    indeterminado_brl:         Decimal   = Field(description="Σ Δ folhas COSIF sem mapping (esperado: zero)")


# ── Balanco patrimonial (F1 do redesign, 2026-05-22) ────────────────────────
#
# Shape dedicado pro Balance hero. Difere de VariacaoDiariaResponse em duas
# dimensoes:
#   1. Apresenta Ativos / Passivos separados (decomposicao patrimonial), nao
#      uma lista monolitica de categorias.
#   2. Sinais ABSOLUTOS: passivos (Mez, Sr, PDD) vem POSITIVOS no payload —
#      a secao do balance comunica o sinal contabil. Endpoint legado
#      /variacao-diaria mantem sinais invertidos por compatibilidade.


CategoriaPatrimonialKey = Literal[
    # Ativos
    "compromissada",
    "titulos_publicos",
    "fundos_di",
    "dc",
    "op_estruturadas",
    "outros_ativos",
    "cpr",
    "tesouraria",
    "saldo_conta_corrente",
    # Passivos / redutores
    "mezanino",
    "senior",
    "pdd",
]


class CategoriaPatrimonial(BaseModel):
    """Uma linha do balanco — categoria patrimonial com saldos D-1 / D0 / Δ."""

    key:    CategoriaPatrimonialKey
    label:  str       = Field(description="Label exibido na UI (pt-BR)")
    tipo:   Literal["ativo", "passivo"]
    d1:     Decimal   = Field(description="Saldo em D-1 (R$, sinal absoluto)")
    d0:     Decimal   = Field(description="Saldo em D0 (R$, sinal absoluto)")
    delta:  Decimal   = Field(description="d0 - d1 (com sinal natural)")
    source: str       = Field(description="Tabela canonica origem + filtro aplicado")


class BalancoPatrimonialResponse(BaseModel):
    """Resposta do endpoint GET /controladoria/cota-sub/balanco-patrimonial.

    Balanco patrimonial diario na otica do cotista subordinado, com identidade
    contabil explicita:

        PL Sub Jr (deduzido)    = Σ Ativos - Σ Passivos
        PL Sub Jr (na fonte)    = wh_mec_evolucao_cotas, classe Sub
        Residuo (consistencia)  = PL deduzido - PL na fonte  (esperado ~0)

    Identidade fechando em zero = sistema em ordem. Residuo != 0 indica
    desalinhamento entre o calculo do gestor REALINVEST (consolidado via 11
    categorias) e o publicado pela QiTech no MEC. Frontend renderiza estado
    de saude (✓ / ⚠ / ✗) baseado em `residuo_identidade`.
    """

    fundo_id:           str       = Field(description="UUID da Unidade Administrativa")
    fundo_nome:         str
    data:               date      = Field(description="D0 (dia analisado)")
    data_anterior:      date      = Field(description="D-1 (dia util anterior)")

    ativos:             list[CategoriaPatrimonial]
    passivos:           list[CategoriaPatrimonial]

    soma_ativos_d1:     Decimal
    soma_ativos_d0:     Decimal
    soma_ativos_delta:  Decimal

    soma_passivos_d1:    Decimal
    soma_passivos_d0:    Decimal
    soma_passivos_delta: Decimal

    pl_deduzido_d1:     Decimal   = Field(description="Σ Ativos - Σ Passivos em D-1")
    pl_deduzido_d0:     Decimal   = Field(description="Σ Ativos - Σ Passivos em D0")
    pl_deduzido_delta:  Decimal

    pl_fonte_d1:        Decimal   = Field(description="PL Sub Jr lido de wh_mec (classe Sub) em D-1")
    pl_fonte_d0:        Decimal   = Field(description="PL Sub Jr lido de wh_mec (classe Sub) em D0")
    pl_fonte_delta:     Decimal

    residuo_identidade_d1: Decimal = Field(
        description="pl_deduzido_d1 - pl_fonte_d1 (snapshot acumulado; "
                    "inclui arredondamentos historicos)",
    )
    residuo_identidade_d0: Decimal = Field(
        description="pl_deduzido_d0 - pl_fonte_d0 (snapshot acumulado; "
                    "inclui arredondamentos historicos)",
    )
    residuo_identidade_delta: Decimal = Field(
        default=Decimal("0"),
        description="(pl_deduzido_delta - pl_fonte_delta) -- ERRO DO DIA, "
                    "isolado do acumulado historico. Esperado ~0; valores "
                    "pequenos (<R$1) sao arredondamento da QiTech, valores "
                    "altos (>R$10) sinalizam falha de calculo.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Balanco ESTRUTURAL (redesign 2026-05-27) — coerencia por natureza + sinal
# ─────────────────────────────────────────────────────────────────────────────
# Diferenca vs BalancoPatrimonialResponse (que continua servindo a tool do
# agente, §19): aqui PDD e CONTRA-ATIVO (abate DC, nao e passivo), CPR e
# DIVIDIDO por sinal (a receber=ativo / a pagar=passivo), Senior+Mezanino sao
# agrupados como "Cotas Prioritarias" no passivo, e o residuo MEC sai do corpo
# do balanco pra um bloco de reconciliacao. PL Sub IDENTICO ao pl_deduzido do
# balanco antigo (so muda classificacao/apresentacao).

BalancoNaturezaLinha = Literal["ativo", "contra_ativo", "passivo"]
BalancoGrupoKey = Literal[
    "direitos_creditorios",
    "aplicacoes",
    "disponibilidades",
    "operacional",
    "cotas_prioritarias",
]


class BalancoLinhaEstrutural(BaseModel):
    """Uma linha do balanco estrutural, classificada por natureza + grupo."""

    key:         str
    label:       str
    natureza:    BalancoNaturezaLinha
    grupo:       BalancoGrupoKey
    grupo_label: str
    d1:    Decimal = Field(description="Magnitude em D-1 (contra_ativo/passivo >=0; ativo pode ser <0 p/ caixa a descoberto)")
    d0:    Decimal
    delta: Decimal = Field(description="d0 - d1 (sinal natural)")
    source:    str
    drill_key: CategoriaPatrimonialKey | None = Field(
        default=None,
        description="Chave do drill quando a linha e drilavel (dc/cpr/pdd). None = sem drill.",
    )


class ReconciliacaoMec(BaseModel):
    """Check de qualidade — PL Sub calculado vs fonte MEC. NAO e linha do balanco."""

    pl_fonte_d1:    Decimal
    pl_fonte_d0:    Decimal
    pl_fonte_delta: Decimal
    residuo_d1:    Decimal = Field(description="pl_sub_calculado_d1 - pl_fonte_d1 (acumulado)")
    residuo_d0:    Decimal
    residuo_delta: Decimal = Field(description="erro do dia = pl_sub_delta - pl_fonte_delta")
    dentro_tolerancia: bool = Field(description="|residuo_delta| < R$ 1")


class BalancoEstruturalResponse(BaseModel):
    """GET /controladoria/cota-sub/balanco-estrutural.

    Balanco gerencial otica Sub Jr, coerente por natureza + sinal:
      ATIVO (ativo + contra_ativo) / PASSIVO (operacional + cotas_prioritarias)
      / PL Sub Jr residual. Fecha por construcao: PL Sub = Σ Ativo - Σ Passivo.
    Reconciliacao com a fonte MEC vai em bloco separado (nao e linha do balanco).
    """

    fundo_id:      str
    fundo_nome:    str
    data:          date
    data_anterior: date

    ativos:   list[BalancoLinhaEstrutural] = Field(description="natureza ativo + contra_ativo, em ordem de grupo")
    passivos: list[BalancoLinhaEstrutural] = Field(description="natureza passivo, em ordem de grupo")

    dc_liquido_d1:    Decimal = Field(description="DC bruto - PDD (subtotal do grupo Direitos Creditorios)")
    dc_liquido_d0:    Decimal
    dc_liquido_delta: Decimal

    total_ativo_d1:    Decimal = Field(description="Σ ativo - Σ contra_ativo")
    total_ativo_d0:    Decimal
    total_ativo_delta: Decimal

    total_passivo_d1:    Decimal
    total_passivo_d0:    Decimal
    total_passivo_delta: Decimal

    pl_sub_d1:    Decimal = Field(description="total_ativo - total_passivo (fecha por construcao)")
    pl_sub_d0:    Decimal
    pl_sub_delta: Decimal

    reconciliacao: ReconciliacaoMec
