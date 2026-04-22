"""Schemas da Ficha do Fundo -- L3 Benchmark > Ficha individual.

Snapshot + series ~24m de um fundo FIDC a partir dos Informes Mensais CVM
(dados publicos, federados via postgres_fdw sob `cvm_remote.*`). Detalhes da
ponte e tabelas em `docs/integracao-cvm-fidc.md` (CLAUDE.md 13.1).

Sem `tenant_id` (dado publico). Proveniencia da resposta traz
`source_type='public:cvm_fidc'` (CLAUDE.md 14).

Cada secao do schema mapeia uma abertura da ficha na UI:
- identificacao       -> cabecalho (razao social, admin, prazos)
- pl_serie            -> PL historico
- carteira_serie      -> composicao do ativo ao longo do tempo
- atraso_serie        -> buckets de inadimplencia (0-30..>1080)
- prazo_medio_serie   -> duration aproximado da carteira a vencer
- cedentes            -> top-9 cedentes (limite da CVM)
- setores             -> composicao setorial (tab_ii)
- subclasses          -> series/subclasses ativas (sr/sub)
- cotistas_serie      -> evolucao de cotistas por subclasse
- cotistas_tipo_serie -> cotistas por tipo de investidor (Senior/Sub)
- pl_subclasses_serie -> evolucao de PL por subclasse (qt * vl)
- rent_serie          -> rentabilidade mensal por subclasse
- rent_acumulada      -> acumulada (derivada do rent_serie)
- desempenho_vs_meta  -> esperado vs real por subclasse
- liquidez_serie      -> caixa + recebiveis escalonados
- fluxo_cotas         -> captacao/resgate/amortizacao
- recompra_serie      -> recompras de DC (VII.d) + %PL
- scr_distribuicao    -> rating SCR (AA..H)
- garantias           -> valor e % de garantia em DC
- limitacoes          -> lista PT-BR do que NAO e reproduzivel por CVM
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Identificacao(BaseModel):
    cnpj: str
    denom_social: str | None
    tp_fundo_classe: str | None
    condom: str | None
    classe: str | None
    admin: str | None
    cnpj_admin: str | None
    prazo_conversao_cota: int | None
    prazo_pagto_resgate: int | None
    competencia_atual: str
    competencia_primeira: str


class PLPonto(BaseModel):
    competencia: date
    pl: float
    pl_medio: float | None = None  # tab_iv_b_vl_pl_medio (media 3m)


class CarteiraPonto(BaseModel):
    """Ativo (Tabela I) do Informe Mensal FIDC -- R$.

    Hierarquia oficial CVM:
        (I)   Ativo                       = disp + carteira + deriv + outro_ativo
        (I.1) Disponibilidades            -> disp
        (I.2) Carteira                    -> carteira_sub (soma de I.2.a..I.2.j)
            (I.2.a) DC com risco          -> dc_risco   (inclui PDD negativa dentro)
            (I.2.b) DC sem risco          -> dc_sem_risco
            (I.2.c) Valores Mobiliarios   -> vlmob
            (I.2.d) Titulos Publicos      -> tit_pub
            (I.2.e) CDB                   -> cdb
            (I.2.f) Op. Compromissadas    -> oper_comprom
            (I.2.g) Outros RF             -> outros_rf
            (I.2.h) Cotas FIDC            -> cotas_fidc
            (I.2.i) Cotas FIDC NP         -> cotas_fidc_np
            (I.2.j) Warrants/Futuros      -> contrato_futuro
        (I.3) Posicao Deriv.              -> deriv
        (I.4) Outros Ativos               -> outro_ativo
        (memo) PDD (aprox.)               -> pdd_aprox (redutor ja contido em dc_risco)
    """

    competencia: date
    disp: float
    dc_risco: float
    dc_sem_risco: float
    vlmob: float
    tit_pub: float
    cdb: float
    oper_comprom: float
    outros_rf: float
    cotas_fidc: float
    cotas_fidc_np: float
    contrato_futuro: float
    carteira_sub: float
    deriv: float
    outro_ativo: float
    pdd_aprox: float
    ativo_total: float


class AtrasoBuckets(BaseModel):
    b0_30: float
    b30_60: float
    b60_90: float
    b90_120: float
    b120_150: float
    b150_180: float
    b180_360: float
    b360_720: float
    b720_1080: float
    b1080_plus: float


class AtrasoPonto(BaseModel):
    competencia: date
    buckets: AtrasoBuckets
    pct_pl_total: float


class PrazoMedioPonto(BaseModel):
    competencia: date
    dias_aprox: float


class CedenteLinha(BaseModel):
    cpf_cnpj: str | None
    rank: int
    pct: float


class SetorLinha(BaseModel):
    setor: str
    valor: float
    pct: float


class SubclasseLinha(BaseModel):
    classe_serie: str
    id_subclasse: str | None
    qt_cota: float
    vl_cota: float
    pl: float
    pct_pl: float
    nr_cotst: int


class CotistasPonto(BaseModel):
    competencia: date
    por_serie: dict[str, int]


class PLSubclassesPonto(BaseModel):
    competencia: date
    por_subclasse: dict[str, float]


class RentPonto(BaseModel):
    competencia: date
    por_subclasse: dict[str, float]


class RentAcumuladaPonto(BaseModel):
    competencia: date
    por_subclasse: dict[str, float]
    cdi_acum: float | None


class DesempenhoGap(BaseModel):
    esperado: float
    realizado: float
    gap: float


class DesempenhoPonto(BaseModel):
    competencia: date
    por_subclasse: dict[str, DesempenhoGap]


class LiquidezFaixas(BaseModel):
    d0: float
    d30: float
    d60: float
    d90: float
    d180: float
    d360: float
    mais_360: float


class LiquidezPonto(BaseModel):
    competencia: date
    faixas: LiquidezFaixas


class FluxoCotasPonto(BaseModel):
    competencia: date
    tp_oper: str
    classe_serie: str
    vl_total: float
    qt_cota: float


class CotistasTipoPonto(BaseModel):
    """Cotistas por TIPO de investidor (tab_x_1_1).

    Quebra oficial CVM: Senior vs Subordinada (NAO por serie). Dentro de
    cada uma, 16 tipos de investidor: pf, pj_nao_financ, pj_financ, banco,
    invnr, rpps, eapc, efpc, fii, cota_fidc, outro_fi, clube, segur,
    corretora_distrib, capitaliz, outro.
    """

    competencia: date
    senior: dict[str, int]
    subord: dict[str, int]


class RecompraPonto(BaseModel):
    """Recompras de DC no mes (Tabela VII.d do Informe Mensal FIDC)."""

    competencia: date
    qt_recompra: float        # tab_vii_d_1_qt_recompra
    vl_recompra: float        # tab_vii_d_2_vl_recompra
    vl_contab_recompra: float # tab_vii_d_3_vl_contab_recompra
    pct_pl: float | None      # vl_recompra / tab_iv_a_vl_pl * 100


class SCRLinha(BaseModel):
    rating: str
    valor: float
    pct: float


class Garantias(BaseModel):
    vl_garantia: float
    pct_garantia: float


class FichaFundo(BaseModel):
    identificacao: Identificacao
    pl_serie: list[PLPonto]
    carteira_serie: list[CarteiraPonto]
    atraso_serie: list[AtrasoPonto]
    prazo_medio_serie: list[PrazoMedioPonto]
    cedentes: list[CedenteLinha]
    setores: list[SetorLinha]
    subclasses: list[SubclasseLinha]
    cotistas_serie: list[CotistasPonto]
    cotistas_tipo_serie: list[CotistasTipoPonto]
    pl_subclasses_serie: list[PLSubclassesPonto]
    rent_serie: list[RentPonto]
    rent_acumulada: list[RentAcumuladaPonto]
    desempenho_vs_meta: list[DesempenhoPonto]
    liquidez_serie: list[LiquidezPonto]
    fluxo_cotas: list[FluxoCotasPonto]
    recompra_serie: list[RecompraPonto]
    scr_distribuicao: list[SCRLinha]
    garantias: Garantias | None
    limitacoes: list[str]
