"""Catalogo dos 11 drivers da Cota Sub — metodo do gestor REALINVEST.

Cada driver e um `MetricSpec` que decompoe parcialmente o ΔPL da cota Sub
num conceito patrimonial (PDD, apropriacao DC, fluxo de cotistas Sr/Mez,
posicoes de tesouraria, etc). Σ drivers ≈ ΔPL contabil — residuo
("indeterminado") aparece como alerta na UI, sem threshold.

Vocabulario do gestor (planilha `VariacaoDeCota_Preenchida.xlsx`):

| Driver                  | Formula                                                                   |
|-------------------------|---------------------------------------------------------------------------|
| PDD                     | -Δ valor_pdd no estoque                                                   |
| Apropriacao de DC       | dEstoque - Aquisicoes + Liquidacoes (so a parcela de juros capitalizados) |
| Apropriacao de despesas | dCPR liquido (receber - pagar)                                            |
| Fundos DI               | dPosicao - movimento de caixa                                             |
| Compromissada           | dPosicao - movimento overnight                                            |
| Titulos Publicos        | dPosicao TPF - aquisicao + liquidacao                                     |
| Senior                  | -ΔPL Senior (Sub paga subordinacao)                                       |
| Mezanino                | -ΔPL Mezanino (Sub paga subordinacao)                                     |
| Tesouraria              | dPosicao                                                                  |
| Op Estruturadas         | dPosicao                                                                  |
| Outros Ativos           | dPosicao                                                                  |

Conceito chave: movimento de caixa do dia e NEUTRO no PL Sub — apenas troca
ativos entre si. Apenas o RENDIMENTO (juros, MtM, ganho de mercado) afeta o
PL. Compute_fns devem subtrair os movimentos de caixa quando aplicavel.

Versoes: bump quando formula mudar semanticamente. Hoje todos em 1.0.0.
"""

from __future__ import annotations

from app.shared.metric_catalog import MetricCategory, MetricSpec

# ─────────────────────────────────────────────────────────────────────────────
# Constantes auxiliares
# ─────────────────────────────────────────────────────────────────────────────

_MODULE = "controladoria"
_OWNER = "controladoria-team"
_VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# 11 drivers da Cota Sub
# ─────────────────────────────────────────────────────────────────────────────

COTA_SUB_DRIVERS: tuple[MetricSpec, ...] = (
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.pdd",
        label="PDD",
        description=(
            "Variacao da provisao de devedores duvidosos no dia. PDD subindo "
            "diminui o PL da cota Sub (provisao consome o subordinado)."
        ),
        category=MetricCategory.DRIVER,
        formula_description="-Δ valor_pdd agregado no estoque",
        silver_tables_required=("wh_estoque_recebivel",),
        endpoints_required=("qitech.market.fidc_estoque",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.apropriacao_dc",
        label="Apropriacao de DC",
        description=(
            "Juros capitalizados nos recebiveis de DC (duplicata/cheque/CCB) "
            "no dia. Isola o rendimento do estoque (movimento de caixa e "
            "neutro): apropriacao = dEstoque - Aquisicoes + Liquidacoes."
        ),
        category=MetricCategory.DRIVER,
        formula_description="dEstoque − Aquisicoes + |Liquidacoes|",
        silver_tables_required=(
            "wh_estoque_recebivel",
            "wh_aquisicao_recebivel",
            "wh_liquidacao_recebivel",
        ),
        endpoints_required=(
            "qitech.market.fidc_estoque",
            "qitech.custodia.aquisicao_consolidada",
            "qitech.custodia.liquidados_baixados",
        ),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.apropriacao_despesas",
        label="Apropriacao de despesas",
        description=(
            "Despesas apropriadas pela competencia no dia (taxa de adm, "
            "custodia, gestao, auditoria, IOF/IR a pagar, etc). Captura o "
            "diferimento de despesas pagas antes (regime competencia)."
        ),
        category=MetricCategory.DRIVER,
        formula_description="dCPR_a_receber − dCPR_a_pagar",
        silver_tables_required=("wh_cpr_movimento",),
        endpoints_required=("qitech.market.cpr",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.fundos_di",
        label="Fundos DI",
        description=(
            "Rendimento das aplicacoes em fundos de RF/DI usadas como "
            "tesouraria. Movimentos de caixa (aplicacao/resgate) sao neutros "
            "— apenas a variacao de cota agrega ao PL."
        ),
        category=MetricCategory.DRIVER,
        formula_description="dPosicao − movimento_de_caixa (so DI)",
        silver_tables_required=(
            "wh_posicao_cota_fundo",
            "wh_movimento_caixa",
        ),
        endpoints_required=(
            "qitech.market.outros_fundos",
            "qitech.market.demonstrativo_caixa",
        ),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.compromissada",
        label="Compromissada",
        description=(
            "Rendimento de operacoes compromissadas (compra com compromisso "
            "de revenda). Movimentos overnight sao neutros — apenas o juro "
            "agrega ao PL."
        ),
        category=MetricCategory.DRIVER,
        formula_description="dPosicao − movimento_overnight",
        silver_tables_required=(
            "wh_posicao_compromissada",
            "wh_movimento_caixa",
        ),
        endpoints_required=(
            "qitech.market.rf_compromissadas",
            "qitech.market.demonstrativo_caixa",
        ),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.titulos_publicos",
        label="Titulos Publicos",
        description=(
            "Rendimento de TPF (LTN, NTN-B/F/C) + NCs. Inclui marcacao a "
            "mercado (curva) + ganho/perda de liquidacao. Aquisicao e "
            "liquidacao sao movimento de caixa, descontados."
        ),
        category=MetricCategory.DRIVER,
        formula_description="dPosicao_TPF − aquisicao + liquidacao",
        silver_tables_required=("wh_posicao_renda_fixa",),
        endpoints_required=("qitech.market.rf",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.senior",
        label="Senior",
        description=(
            "Subordinacao paga a classe Senior no dia. Sempre negativo do "
            "ponto de vista da Sub — a valorizacao da Senior e descontada "
            "do subordinado."
        ),
        category=MetricCategory.DRIVER,
        formula_description="-ΔPL_Senior (apurado pela administradora)",
        silver_tables_required=("wh_mec_evolucao_cotas",),
        endpoints_required=("qitech.market.mec",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.mezanino",
        label="Mezanino",
        description=(
            "Subordinacao paga a classe Mezanino no dia. Sempre negativo do "
            "ponto de vista da Sub — analogo ao Senior."
        ),
        category=MetricCategory.DRIVER,
        formula_description="-ΔPL_Mezanino (apurado pela administradora)",
        silver_tables_required=("wh_mec_evolucao_cotas",),
        endpoints_required=("qitech.market.mec",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.tesouraria",
        label="Tesouraria",
        description=(
            "Variacao do saldo de tesouraria QiTech. Reflete movimento "
            "operacional de caixa interno ao fundo."
        ),
        category=MetricCategory.DRIVER,
        formula_description="dPosicao_tesouraria",
        silver_tables_required=("wh_saldo_tesouraria",),
        endpoints_required=("qitech.market.tesouraria",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.op_estruturadas",
        label="Op Estruturadas",
        description=(
            "Variacao de posicoes em operacoes estruturadas (derivativos, "
            "swaps, NDFs). Pode nao se aplicar a todos os fundos — driver "
            "vira zero quando nao ha posicao."
        ),
        category=MetricCategory.DRIVER,
        formula_description="dPosicao_op_estruturadas (filtrado em outros_ativos)",
        silver_tables_required=("wh_posicao_outros_ativos",),
        endpoints_required=("qitech.market.outros_ativos",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.outros_ativos",
        label="Outros Ativos",
        description=(
            "Variacao de ativos nao classificados nos demais drivers. "
            "Captura tudo que sobra no `wh_posicao_outros_ativos` apos "
            "filtragem de Op Estruturadas."
        ),
        category=MetricCategory.DRIVER,
        formula_description="dPosicao_outros_ativos (residual)",
        silver_tables_required=("wh_posicao_outros_ativos",),
        endpoints_required=("qitech.market.outros_ativos",),
        version=_VERSION,
        owner=_OWNER,
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Index O(1) por name (curto, sem prefixo de modulo)
# ─────────────────────────────────────────────────────────────────────────────

COTA_SUB_DRIVERS_BY_NAME: dict[str, MetricSpec] = {
    spec.name: spec for spec in COTA_SUB_DRIVERS
}


def get_driver_spec(name: str) -> MetricSpec | None:
    """O(1) lookup por nome dentro do modulo controladoria.

    Aceita o nome curto (`cota_sub.driver.pdd`) ou o global_id
    (`controladoria.cota_sub.driver.pdd`).
    """
    if name.startswith("controladoria."):
        name = name[len("controladoria."):]
    return COTA_SUB_DRIVERS_BY_NAME.get(name)
