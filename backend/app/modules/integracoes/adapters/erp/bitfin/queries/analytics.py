"""Queries contra o database ANALYTICS (A7-especifico).

ATENCAO: este database NAO faz parte do que o Bitfin entrega por padrao --
e construido pela A7 em cima do banco transacional UNLTD_<cliente>. Cliente
novo do Strata que use Bitfin nao tera um ANALYTICS provisionado.

A partir do adapter v2.0.0 (2026-05-12), o caminho critico do DRE deixou
de usar este arquivo -- nossa regra de classificacao mora em
`wh_dre_classification_rule` (gr_db) e o silver `wh_dre_mensal` agora
nasce do bronze das 3 fontes em UNLTD_<X>.

Resta apenas `elig_snapshot_titulo` aqui -- ainda nao migrado para um
adapter agnostico. Followup separado pra eliminar (envolve recriar a
denormalizacao de titulos/operacoes/cedentes/sacados em codigo nosso).

Todas as queries aceitam um parametro `?` representando o corte temporal
(ex.: `data_ref > ?`). Passe `date(1900, 1, 1)` para full refresh.
"""

SELECT_SNAPSHOT_TITULO = """
SELECT
    snapshot_id, data_ref,
    UnidadeAdministrativaId AS unidade_administrativa_id,
    SacadoId AS sacado_id,
    Coobrigacao AS coobrigacao,
    produto_sigla, produto_descricao,
    recebivel_sigla, recebivel_descricao,
    Status AS status, Situacao AS situacao, situacao_descricao,
    cedente_cliente_id, cedente_entidade_id, cedente_nome, cedente_documento,
    grupo_economico_id_cedente, grupo_economico_nome_cedente, cedente_em_rj,
    cedente_chave_cnae, cnae_secao, cnae_divisao, cnae_grupo, cnae_classe,
    cnae_subclasse, cnae_denominacao,
    sacado_entidade_id, sacado_nome, sacado_documento,
    grupo_economico_id_sacado, grupo_economico_nome_sacado, sacado_em_rj,
    gerente_nome, gerente_documento,
    cedente_grp_key, cedente_grp_nome, cedente_grp_tipo,
    sacado_grp_key, sacado_grp_nome, sacado_grp_tipo,
    saldo_total, vencido, vencido_mais_5_dias, vencido_d0_a_d5,
    vencido_ate_d30, vencido_ate_d60, vencido_60_ate_120, vencido_maior_d120,
    qtd_titulos, qtd_operacoes, qtd_cedentes, qtd_sacados,
    ticket_medio, atraso_max, atraso_medio
FROM dbo.elig_snapshot_titulo
WHERE data_ref > ?
ORDER BY data_ref, snapshot_id
"""
