"""Catalogo de silvers (modelo canonico) — QiTech-alimentados.

Fase 3a do refactor de proveniencia transversal (2026-05-18). Cada silver
(`wh_*`) declarado aqui como `SilverSpec`. Permite:

1. Reverse lookup: "esse silver alimenta quais metricas?"
2. UI `/admin/proveniencia` aba Silvers — lista tudo + freshness por tenant.
3. Validacao cruzada com `endpoint_catalog`: cada `EndpointSpec.canonical_table`
   tem `SilverSpec` correspondente.

## Convencoes

- Todos os 17 silvers QiTech-alimentados usam UQ `(tenant_id, source_id)`,
  onde `source_id` e string composta deterministica construida no mapper.
  `primary_key` aqui registra essa UQ literal — o que e UNICO no DB. A
  composicao logica de `source_id` (ex.: `docFundo|docCedente|seuNumero|...`)
  esta documentada no `.md` de payload shape correspondente.

- `date_column` aponta pra coluna principal de data temporal — usada por
  servicos de cobertura/freshness pra particionar por janela. Quando o
  silver tem multiplas colunas de data (`data_referencia`, `data_vencimento`,
  etc), escolhemos a que representa "quando o dado refere-se" semanticamente.

## Quando adicionar entrada

Toda vez que um novo endpoint QiTech tiver seu `canonical_table` setado no
catalog, criar aqui o `SilverSpec` correspondente. Quando outros adapters
(BTG, Kanastra) virarem, criar arquivo paralelo OU adicionar aqui (decisao
revisada quando volume justificar split).
"""

from __future__ import annotations

from app.shared.silver_catalog import SilverSpec

# ─────────────────────────────────────────────────────────────────────────────
# Silvers populados por market.* (10 endpoints sincronos JSON + 1 async CSV)
# ─────────────────────────────────────────────────────────────────────────────

_MARKET_SILVERS: tuple[SilverSpec, ...] = (
    SilverSpec(
        table_name="wh_posicao_cota_fundo",
        label="Posicao em outros fundos",
        description="Posicoes do FIDC em outros fundos (cotas detidas). PL, cota, % posicao por fundo. Inclui Fundos DI usados pra tesouraria.",
        fed_by_endpoints=("qitech.market.outros_fundos",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_saldo_conta_corrente",
        label="Saldo de conta-corrente",
        description="Saldo de conta-corrente do FIDC consolidado D-1.",
        fed_by_endpoints=("qitech.market.conta_corrente",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_saldo_tesouraria",
        label="Posicao de tesouraria",
        description="Saldo de tesouraria do FIDC D-1.",
        fed_by_endpoints=("qitech.market.tesouraria",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_posicao_outros_ativos",
        label="Posicoes em outros ativos",
        description="Posicoes diversas nao classificadas em renda fixa, variavel ou fundos. Inclui operacoes estruturadas, derivativos, etc.",
        fed_by_endpoints=("qitech.market.outros_ativos",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_movimento_caixa",
        label="Movimentacao de caixa",
        description="Entradas e saidas de caixa do FIDC liquidadas no dia.",
        fed_by_endpoints=("qitech.market.demonstrativo_caixa",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_liquidacao",
    ),
    SilverSpec(
        table_name="wh_cpr_movimento",
        label="CPR (contas a pagar e receber)",
        description="Movimentos de contas a pagar e receber do FIDC: provisoes, taxas, despesas, aportes/resgates engaiolados, etc. Granularidade por linha contabil.",
        fed_by_endpoints=("qitech.market.cpr",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_mec_evolucao_cotas",
        label="MEC (mapa evolutivo de cotas)",
        description="Evolucao diaria das classes de cotas do FIDC: PL, quantidade, valor unitario, entradas e saidas por classe (Sub/Sr/Mez).",
        fed_by_endpoints=("qitech.market.mec",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_rentabilidade_fundo",
        label="Rentabilidade calculada do fundo",
        description="Rentabilidade diaria/mensal/12M por classe e por indexador (CDI, IPCA, etc).",
        fed_by_endpoints=("qitech.market.rentabilidade",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_posicao_renda_fixa",
        label="Posicao de renda fixa",
        description="Posicoes em titulos de renda fixa do FIDC: TPF (LTN, NTN), NCs, debentures, CDB, LCI, LCA, etc. Inclui cotas de fundos RF.",
        fed_by_endpoints=("qitech.market.rf",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_posicao_compromissada",
        label="Posicao em operacoes compromissadas",
        description="Operacoes compromissadas (compra com compromisso de revenda) — instrumento de tesouraria.",
        fed_by_endpoints=("qitech.market.rf_compromissadas",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_estoque_recebivel",
        label="Estoque de recebiveis (carteira)",
        description="Posicao consolidada da carteira de recebiveis do FIDC numa data. Granularidade por recebivel (1 linha por titulo). Carrega valor PDD, faixa de risco, taxas, datas.",
        fed_by_endpoints=("qitech.market.fidc_estoque",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_referencia",
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Silvers populados por custodia.* (4 endpoints fidc-custodia/*)
# ─────────────────────────────────────────────────────────────────────────────

_CUSTODIA_SILVERS: tuple[SilverSpec, ...] = (
    SilverSpec(
        table_name="wh_aquisicao_recebivel",
        label="Aquisicoes de recebiveis",
        description="Cessoes adquiridas pelo FIDC. Granularidade por recebivel cedido.",
        fed_by_endpoints=("qitech.custodia.aquisicao_consolidada",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_aquisicao",
    ),
    SilverSpec(
        table_name="wh_liquidacao_recebivel",
        label="Liquidacoes e baixas de recebiveis",
        description="Liquidacoes (recebimento) e baixas (write-off) de recebiveis do FIDC. Granularidade por evento (1 linha por liquidacao/baixa).",
        fed_by_endpoints=("qitech.custodia.liquidados_baixados",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_movimento_aberto",
        label="Cessoes em aberto (snapshot)",
        description="Snapshot diario de cessoes pendentes de liquidacao. Foto da fila operacional.",
        fed_by_endpoints=("qitech.custodia.movimento_aberto",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_referencia",
    ),
    SilverSpec(
        table_name="wh_operacao_remessa",
        label="Detalhes de operacoes (CNAB)",
        description="Lotes CNAB processados — uma linha por arquivo de remessa. Metadados da importacao.",
        fed_by_endpoints=("qitech.custodia.detalhes_operacoes",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_importacao",
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Silvers populados por bank_account.* (2 endpoints conta-corrente Singulare)
# ─────────────────────────────────────────────────────────────────────────────

_BANK_ACCOUNT_SILVERS: tuple[SilverSpec, ...] = (
    SilverSpec(
        table_name="wh_saldo_bancario_diario",
        label="Saldo bancario diario",
        description="Saldo de fechamento das contas-corrente Singulare D+0 (end-of-day).",
        fed_by_endpoints=("qitech.bank_account.balance",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_posicao",
    ),
    SilverSpec(
        table_name="wh_extrato_bancario",
        label="Extrato bancario",
        description="Lancamentos da conta-corrente Singulare — chega ao longo do dia (intraday).",
        fed_by_endpoints=("qitech.bank_account.statement",),
        primary_key=("tenant_id", "source_id"),
        temporal=True,
        date_column="data_lancamento",
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Public catalog
# ─────────────────────────────────────────────────────────────────────────────

SILVER_CATALOG: tuple[SilverSpec, ...] = (
    *_MARKET_SILVERS,
    *_CUSTODIA_SILVERS,
    *_BANK_ACCOUNT_SILVERS,
)


SILVER_CATALOG_BY_TABLE: dict[str, SilverSpec] = {
    spec.table_name: spec for spec in SILVER_CATALOG
}


def silver_catalog() -> tuple[SilverSpec, ...]:
    """Return immutable tuple of all silver specs in the system."""
    return SILVER_CATALOG


def get_silver_spec(table_name: str) -> SilverSpec | None:
    """O(1) lookup by `wh_*` table name. Returns None if not catalogued."""
    return SILVER_CATALOG_BY_TABLE.get(table_name)


def silvers_fed_by_endpoint(endpoint_global_id: str) -> tuple[SilverSpec, ...]:
    """Lista silvers alimentados por um endpoint especifico.

    Util pra UI admin (clicar num endpoint → ver silvers downstream) e pra
    debug (qual silver vai ficar afetado se esse endpoint cair).
    """
    return tuple(
        spec
        for spec in SILVER_CATALOG
        if endpoint_global_id in spec.fed_by_endpoints
    )
