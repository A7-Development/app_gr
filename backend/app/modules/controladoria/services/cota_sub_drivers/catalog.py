"""Catalogo dos 11 drivers da Cota Sub — metodo do gestor REALINVEST.

Modelo ΔSaldo patrimonial: cada driver e ΔSaldo da fonte canonica (silver).
Σ drivers ≡ ΔPL Sub POR CONSTRUCAO — movimento interno entre categorias
se cancela (aplicacao em Fundo DI sai do caixa → cota cresce; ΔTes + ΔFundos_DI
= 0 no liquido). Σ residual = 0 quando todas as categorias patrimoniais
do PL Sub estao mapeadas.

Vocabulario do gestor (planilha `VariacaoDeCota_Preenchida.xlsx`):

| Driver                  | Fonte canonica                                       |
|-------------------------|------------------------------------------------------|
| PDD                     | wh_posicao_outros_ativos WHERE codigo='PDD'          |
| Apropriacao de DC       | wh_posicao_cota_fundo (internos REALINVEST)          |
| Apropriacao de despesas | wh_cpr_movimento Σ valor                             |
| Fundos DI               | wh_posicao_cota_fundo (externos)                     |
| Compromissada           | wh_posicao_compromissada.valor_bruto                 |
| Titulos Publicos        | wh_posicao_renda_fixa via COSIF (TPF)                |
| Senior                  | -ΔPL Senior em wh_mec_evolucao_cotas.patrimonio      |
| Mezanino                | -ΔPL Mezanino em wh_mec_evolucao_cotas.patrimonio    |
| Tesouraria              | wh_saldo_tesouraria (classe Sub)                     |
| Op Estruturadas         | wh_posicao_renda_fixa via COSIF (Nota Comercial)     |
| Outros Ativos           | wh_posicao_outros_ativos (exclui PDD + TPF)          |

Validacao com planilha REALINVEST (28/11→01/12/2025 + 12→13/05/2026):
residuo R$ 0,00 — fechamento exato com a fonte de verdade do gestor.

Versoes: bump quando formula mudar semanticamente. Refactor ΔSaldo simples
em 2026-05-19 manteve 1.0.0 — fontes mudaram mas a abstracao "1 driver =
1 categoria patrimonial" permanece. Bump para 2.0.0 ficaria apropriado
caso a particao em si seja revisada.
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
            "ΔSaldo da provisao de devedores duvidosos consolidada em "
            "wh_posicao_outros_ativos WHERE codigo='PDD'. Provisao subindo "
            "em modulo (mais passivo) → delta negativo → PL Sub cai."
        ),
        category=MetricCategory.DRIVER,
        formula_description="ΔSaldo wh_posicao_outros_ativos (codigo='PDD')",
        silver_tables_required=("wh_posicao_outros_ativos",),
        endpoints_required=("qitech.market.outros_ativos",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.apropriacao_dc",
        label="DC",
        description=(
            "ΔSaldo dos Direitos Creditorios representados como cotas internas "
            "do proprio FIDC (REALINVEST A VENCER + VENCIDOS) em "
            "wh_posicao_cota_fundo. Fonte de verdade do gestor (publicada em "
            "market.outros_fundos)."
        ),
        category=MetricCategory.DRIVER,
        formula_description="ΔSaldo wh_posicao_cota_fundo (cotas internas REALINVEST)",
        silver_tables_required=("wh_posicao_cota_fundo",),
        endpoints_required=("qitech.market.outros_fundos",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.apropriacao_despesas",
        label="CPR",
        description=(
            "ΔSaldo total de Contas a Pagar/Receber em wh_cpr_movimento "
            "(Σ valor, sem filtro). Cobre apropriacao de despesas, "
            "diferimento, provisoes — toda categoria CPR vira ΔSaldo "
            "patrimonial."
        ),
        category=MetricCategory.DRIVER,
        formula_description="ΔSaldo Σ wh_cpr_movimento.valor",
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
            "ΔSaldo de cotas em fundos EXTERNOS (DI, soberano, selic, etc.) "
            "em wh_posicao_cota_fundo. Exclui fundos internos REALINVEST "
            "(esses caem no driver DC)."
        ),
        category=MetricCategory.DRIVER,
        formula_description="ΔSaldo wh_posicao_cota_fundo (fundos externos)",
        silver_tables_required=("wh_posicao_cota_fundo",),
        endpoints_required=("qitech.market.outros_fundos",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.compromissada",
        label="Compromissada",
        description=(
            "ΔSaldo de operacoes compromissadas (compra com compromisso de "
            "revenda) em wh_posicao_compromissada.valor_bruto."
        ),
        category=MetricCategory.DRIVER,
        formula_description="ΔSaldo wh_posicao_compromissada.valor_bruto",
        silver_tables_required=("wh_posicao_compromissada",),
        endpoints_required=("qitech.market.rf_compromissadas",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.titulos_publicos",
        label="Titulos Publicos",
        description=(
            "ΔSaldo de Titulos Publicos (LTN, NTN-B/F/C) em wh_posicao_renda_fixa. "
            "Classificacao agnostica via COSIF (1.3.1.10.07 NTN + 1.2.1.10.05 LTN) "
            "— sem hardcode de siglas."
        ),
        category=MetricCategory.DRIVER,
        formula_description="ΔSaldo wh_posicao_renda_fixa via COSIF (TPF)",
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
            "-ΔPL da classe Senior em wh_mec_evolucao_cotas.patrimonio. "
            "Sub absorve a subordinacao bruta — quando PL_Sr sobe (aporte, "
            "rendimento), Sub residual cai por construcao."
        ),
        category=MetricCategory.DRIVER,
        formula_description="-ΔSaldo wh_mec_evolucao_cotas (classe Senior)",
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
            "-ΔPL da classe Mezanino em wh_mec_evolucao_cotas.patrimonio "
            "(analogo ao Senior — Sub absorve a subordinacao bruta)."
        ),
        category=MetricCategory.DRIVER,
        formula_description="-ΔSaldo wh_mec_evolucao_cotas (classe Mezanino)",
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
            "ΔSaldo de tesouraria da classe Sub em wh_saldo_tesouraria. "
            "Exclui MEZANINO/SENIOR (cada classe reporta tesouraria propria) "
            "e ignora wh_saldo_conta_corrente (duplica contagem)."
        ),
        category=MetricCategory.DRIVER,
        formula_description="ΔSaldo wh_saldo_tesouraria (classe Sub)",
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
            "ΔSaldo de Notas Comerciais (NCPX, NC*) em wh_posicao_renda_fixa. "
            "Classificacao via COSIF 1.3.1.10.16 — sem hardcode de siglas. "
            "Vocabulario gestor REALINVEST: 'Op Estruturadas' = NCs."
        ),
        category=MetricCategory.DRIVER,
        formula_description="ΔSaldo wh_posicao_renda_fixa via COSIF (Nota Comercial)",
        silver_tables_required=("wh_posicao_renda_fixa",),
        endpoints_required=("qitech.market.rf",),
        version=_VERSION,
        owner=_OWNER,
    ),
    MetricSpec(
        module_code=_MODULE,
        name="cota_sub.driver.outros_ativos",
        label="Outros Ativos",
        description=(
            "ΔSaldo residual em wh_posicao_outros_ativos. Exclui PDD "
            "(codigo='PDD' tem driver proprio) e TPF (descricao_tipo_de_ativo "
            "casa com Titulos Publicos)."
        ),
        category=MetricCategory.DRIVER,
        formula_description="ΔSaldo wh_posicao_outros_ativos (exclui PDD + TPF)",
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
