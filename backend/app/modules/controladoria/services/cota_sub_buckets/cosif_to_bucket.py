"""Mapping COSIF -> bucket de explicacao da variacao da Cota Sub.

Refactor 2026-05-17: substitui as heuristicas (MEC/CPR/RF) que calculavam
`delta_brl` em fontes paralelas. Agora cada conta COSIF folha do balancete
e classificada em UM bucket. Σ Δ folhas do bucket = parcela do ΔPL contabil
atribuida ao bucket.

Por construcao, Σ buckets ≡ ΔPL_contabil. Zero "indeterminado" residual.

Decisao do mapping: ver memory `project_cota_sub_cosif_bucket_mapping.md`
e levantamento feito em REALINVEST 13/05/2026.

Heuristicas atuais (PDD/CPR/MtM/Fluxo via MEC) deixam de calcular delta_brl
e viram ENRIQUECEDORAS de `evidencias[]` dentro de cada bucket — puxam
cedente/sacado/papel/historico_traduzido pra dar narrativa rica. Onde nao
cobrirem, a evidencia fica como linha COSIF crua (codigo + nome + delta).
"""
from __future__ import annotations

from typing import Literal

# ─── Bucket ids ──────────────────────────────────────────────────────────────
# Manter sincronizado com `schemas/cota_sub.py::Explanation` (discriminator
# `categoria`) e com o frontend (`api-client.ts::Explanation` + DriversCard).

BucketId = Literal[
    "pdd",
    "renda_fixa",          # antes "marcacao_mercado" — renomeado 2026-05-17
    "movimento_carteira",
    "ajustes_contabeis",
    "remuneracao_sr_mez",
    "fluxo_caixa",
]


# ─── Tabela de mapping COSIF -> bucket ───────────────────────────────────────
# Lista ordenada de regras (prefix -> bucket). A primeira regra cujo prefix
# casar com o `codigo` da folha COSIF ganha. Mantida em ordem DECRESCENTE de
# especificidade (prefixos mais longos primeiro) pra garantir match correto.

_RULES: tuple[tuple[str, BucketId], ...] = (
    # PDD — provisao para devedores duvidosos
    ("1.6.9.97.", "pdd"),

    # Renda Fixa — TPF (LTN/NTN/LFT), notas comerciais, cotas de fundos RF
    ("1.2.1.",     "renda_fixa"),
    ("1.3.1.10.",  "renda_fixa"),  # NTN + NCs
    ("1.3.1.15.",  "renda_fixa"),  # cotas de fundos de RF (tesouraria)

    # Movimento de carteira — DC + caixa (contrapartida) + transito de liquidacao
    ("1.1.2.",            "movimento_carteira"),  # bancos / caixa
    ("1.6.1.30.",         "movimento_carteira"),  # recebiveis em curso + vencidos
    ("1.8.4.30.00.005",   "movimento_carteira"),  # ajuste de compensacao de cota (transito)
    ("4.9.9.30.90.",      "movimento_carteira"),  # creditos a conciliar

    # Ajustes contabeis — despesas + diferimento + apropriacao DRE
    ("1.9.9.10.",     "ajustes_contabeis"),  # despesas antecipadas (diferimento ativo)
    ("4.9.1.",        "ajustes_contabeis"),  # IOF a recolher
    ("4.9.9.30.50.",  "ajustes_contabeis"),  # provisoes de pagamento
    ("8.1.7.",        "ajustes_contabeis"),  # despesas DRE (custodia/adm/gestao)

    # Cotas (6.1.1.70) — quebra por classe e feita pelo chamador via
    # `classe_breakdown_por_cosif`. A regra abaixo serve como fallback caso
    # o breakdown nao esteja disponivel — neste caso TUDO vai pra Remuneracao.
    ("6.1.1.70.", "remuneracao_sr_mez"),
)


# ─── COSIFs explicitamente ignorados ─────────────────────────────────────────
# Grupo 3 (compensacao) e espelho contabil — somar duplica o efeito que ja
# aparece em 6.x. Decisao Ricardo 2026-05-17: "Nao deve ser usado, e conta
# de compensacao apenas. Usar 6.1.1.70.30.001."

_IGNORED_PREFIXES: tuple[str, ...] = (
    "3.",
)


def classify_cosif(codigo: str | None) -> BucketId | None:
    """Retorna o bucket id ao qual a conta COSIF pertence.

    Retorna:
        - BucketId quando a conta casa com uma regra do mapping
        - None quando a conta deve ser IGNORADA (compensacao) OU quando nao
          ha mapping definido — chamador deve tratar como bucket "outros"
          (lista de COSIFs sem mapping pra revisao manual).
    """
    if not codigo:
        return None
    if any(codigo.startswith(p) for p in _IGNORED_PREFIXES):
        return None
    for prefix, bucket in _RULES:
        if codigo.startswith(prefix):
            return bucket
    return None


def is_ignored_for_pl(codigo: str | None) -> bool:
    """True se o COSIF e contabilmente irrelevante pra ΔPL (compensacao)."""
    if not codigo:
        return False
    return any(codigo.startswith(p) for p in _IGNORED_PREFIXES)


def is_cotas_emitidas(codigo: str | None) -> bool:
    """True se o COSIF e da conta de cotas emitidas (6.1.1.70.*).

    Quando True, o chamador DEVE usar o `classe_breakdown_por_cosif` do
    balancete pra separar parcela Sr+Mez (vai pra `remuneracao_sr_mez`) da
    parcela Sub (vai pra `fluxo_caixa` — aporte/resgate proprio).
    """
    if not codigo:
        return False
    return codigo.startswith("6.1.1.70.")
