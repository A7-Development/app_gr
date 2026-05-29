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
    Residuo = ΔPL_Sub_MEC - Σ drivers (exposto sempre, sem threshold).
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


NaoReconhecidoModo = Literal["vaza_residuo", "entra_indevido", "vigia"]


class ItemNaoReconhecidoOut(BaseModel):
    """Item que uma fonte da pagina Cota Sub nao soube classificar.

    Espelha `cota_sub_completude.ItemNaoReconhecido`. Detector generico
    (2026-05-27, pos-caso VCNC): cada driver classifica/filtra por heuristica;
    um valor novo num campo de classificacao vaza pro residuo (`vaza_residuo`),
    entra num driver indevidamente (`entra_indevido`) ou e exposto pra
    auditoria (`vigia`). Σ `vaza_residuo` deve explicar parte do residuo_modelo.
    """

    fonte:          str = Field(description="Tabela silver origem")
    endpoint:       str = Field(description="Endpoint QiTech de origem")
    campo:          str = Field(description="Campo de classificacao que falhou")
    identificador:  str = Field(description="Valor cru nao reconhecido")
    label:          str = Field(description="Rotulo humano pra UI (pt-BR)")
    valor_d0:       Decimal = Field(description="Peso R$ em D0")
    valor_d_prev:   Decimal = Field(description="Peso R$ em D-1")
    modo:           NaoReconhecidoModo
    driver_afetado: str = Field(description="Driver/alvo impactado")
    motivo:         str = Field(description="Explicacao curta (pt-BR)")


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


# ── Evidencias granulares dos drivers da Cota Sub ────────────────────────────
#
# Estruturas papel-a-papel / linha-a-linha que populam os campos `*_evidencias`
# de `DriverResultOut`. Cada driver popula 0-1 lista.


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


# ── Movimento de carteira (evidencia do driver Apropriacao DC) ───────────────


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
    "cpr_receber",
    "tesouraria",
    "saldo_conta_corrente",
    # Passivos / redutores
    "cpr_pagar",
    "mezanino",
    "senior",
    "pdd",
]


# ─────────────────────────────────────────────────────────────────────────────
# Balanco ESTRUTURAL (redesign 2026-05-27) — coerencia por natureza + sinal
# ─────────────────────────────────────────────────────────────────────────────
# Unico balanco da pagina (o antigo BalancoPatrimonialResponse foi removido em
# 2026-05-27). Coerente por natureza + sinal: PDD e CONTRA-ATIVO (abate DC, nao
# e passivo), CPR DIVIDIDO por sinal (a receber=ativo / a pagar=passivo),
# Senior+Mezanino agrupados como "Cotas Prioritarias" no passivo, e o residuo
# MEC sai do corpo do balanco pra um bloco de reconciliacao.

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

    # Detector de nao-reconhecidos (2026-05-27, pos-VCNC). Itens vaza_residuo
    # explicam parte do reconciliacao.residuo_delta. Vazio = tudo classificado.
    nao_reconhecidos: list[ItemNaoReconhecidoOut] = Field(
        default_factory=list,
        description=(
            "Valores que alguma fonte da pagina nao soube classificar. "
            "Modo vaza_residuo/entra_indevido = bug; vigia = informacional."
        ),
    )
