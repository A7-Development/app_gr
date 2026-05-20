"""Critical fields por silver QiTech -- audit trail de orfaos removidos.

Define quais colunas de cada silver QiTech vao no snapshot do
`decision_log` quando uma linha vira orfa via `_replace_canonical_partition`
(Fase 1.3 do refactor "espelho fiel QiTech", 2026-05-20).

Snapshot sempre inclui `id + business keys` automaticamente (montado em
`_replace_canonical_partition`). Esta lista acrescenta os campos de
VALOR / STATUS / TAXA que importam pra reconstrucao forense — "quanto
valia o titulo que sumiu" / "qual era a taxa" / "qual era o status".

Indexado por `__tablename__` -- callsite faz lookup via
`get_critical_fields(Model.__tablename__)`.

Manutencao: ao adicionar coluna nova em silver QiTech, considere se ela
deve entrar no audit. Regra de bolso:
  - SIM: campos monetarios (valor_*, saldo, patrimonio), quantidades,
         taxas, percentuais, status/situacao, datas de evento
         (vencimento, liquidacao, emissao).
  - NAO: nomes/labels (carteira_cliente_nome, ativo_nome), IDs externos
         (source_id, hash_origem), metadados de proveniencia
         (ingested_at, ingested_by_version, trust_level), tipos
         enumerados estaveis (tipo_recebivel quando o universo eh fixo).
"""

CRITICAL_FIELDS_BY_TABLE: dict[str, list[str]] = {
    # ─── Market (raw_relatorio) ────────────────────────────────────────
    "wh_posicao_cota_fundo": [
        "quantidade",
        "quantidade_bloqueada",
        "valor_cota",
        "valor_atual",
        "valor_liquido",
        "valor_aplicacao_resgate",
    ],
    "wh_saldo_conta_corrente": [
        "valor_total",
        "percentual_sobre_conta_corrente",
    ],
    "wh_saldo_tesouraria": [
        "valor",
        "percentual_sobre_cpr",
    ],
    "wh_posicao_outros_ativos": [
        "valor_total",
        "percentual_sobre_outros_ativos",
    ],
    "wh_cpr_movimento": [
        "valor",
        "percentual_sobre_cpr",
    ],
    "wh_mec_evolucao_cotas": [
        "patrimonio",
        "quantidade",
        "valor_da_cota",
        "variacao_diaria",
    ],
    "wh_rentabilidade_fundo": [
        "rentabilidade_real",
        "rentabilidade_diaria",
        "rentabilidade_anual",
    ],
    "wh_posicao_renda_fixa": [
        "valor_aplicado",
        "valor_bruto",
        "valor_liquido",
        "quantidade",
    ],
    "wh_posicao_compromissada": [
        "valor_aplicado",
        "valor_bruto",
        "quantidade",
        "taxa_over",
    ],

    # ─── Custodia (raw_relatorio) ──────────────────────────────────────
    # Esses 5 ainda usam UPSERT legado (custodia.py). Quando o refactor
    # do _persist_raw_split_by_window propagar raw_id ao caller, eles
    # passam a usar _replace_canonical_partition e esta lista entra em
    # acao.
    "wh_aquisicao_recebivel": [
        "valor_compra",
        "valor_vencimento",
        "taxa_aquisicao",
    ],
    "wh_liquidacao_recebivel": [
        "valor_aquisicao",
        "valor_vencimento",
        "valor_pago",
        "taxa_aquisicao",
        "ajuste",  # campo crucial — picos de ajuste retroativo aparecem aqui
    ],
    "wh_estoque_recebivel": [
        "valor_nominal",
        "valor_aquisicao",
        "valor_pdd",
        "taxa_cessao",
        "faixa_pdd",  # mudancas de classificacao Bacen 2682 importam
        "situacao_recebivel",  # Em Aberto / Vencido / Liquidado
    ],
    "wh_movimento_aberto": [
        "valor_aquisicao",
        "valor_nominal",
        "valor_movimentacao",
    ],
    "wh_operacao_remessa": [
        "remessa",
        "reembolso",
        "recompra",
        "valor_total",
        "coobrigacao",  # boolean — mudanca de coobrigacao tem impacto patrimonial
    ],

    # ─── Bank account ──────────────────────────────────────────────────
    "wh_saldo_bancario_diario": [
        "saldo",
        "moeda",
    ],
    "wh_extrato_bancario": [
        # valor/tipo/descricao ja fazem parte da business key; basta o que sobra
        "data_lancamento",
        "contrapartida_doc",
    ],

    # ─── Excluso: wh_movimento_caixa ────────────────────────────────────
    # Tech debt registrada em [[project_qitech_business_key_uq]]: usa
    # (tenant_id, source_id) como UQ (sha16 do item), nao business key
    # explicita. Fica fora de replace-by-partition ate refactor com
    # `seq_no`. Nao adicionar aqui.
}


def get_critical_fields(table_name: str) -> list[str]:
    """Lookup defensivo -- retorna [] pra tabela sem entry registrada.

    Quando a tabela nao tem critical_fields configurados, audit ainda
    funciona mas snapshot fica reduzido a `id + business keys` (ainda
    permite identificar o que sumiu, so nao guarda os valores).
    """
    return CRITICAL_FIELDS_BY_TABLE.get(table_name, [])
