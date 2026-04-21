"""Queries contra o database ANALYTICS.

Todas as queries aceitam um parametro `?` representando o corte temporal
(ex.: `data_ref > ?` ou `Competencia > ?`). Passe `date(1900,1,1)` para
full refresh.
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

SELECT_DRE = """
SELECT
    Ano AS ano, Mes AS mes, Competencia AS competencia,
    OrdemGrupo AS ordem_grupo, GrupoDRE AS grupo_dre, SubGrupo AS subgrupo, Descricao AS descricao,
    Receita AS receita, Custo AS custo, Resultado AS resultado, Quantidade AS quantidade,
    Fornecedor AS fornecedor, FornecedorDocumento AS fornecedor_documento,
    EntidadeId AS entidade_id, ProdutoId AS produto_id,
    UnidadeAdministrativaId AS unidade_administrativa_id,
    Fonte AS fonte
FROM dbo.vw_DRE
WHERE Competencia > ?
"""

SELECT_DIM_MES = """
SELECT
    MesAno AS mes_ano, Ano AS ano, Mes AS mes,
    Trimestre AS trimestre, Semestre AS semestre,
    AnoMesTexto AS ano_mes_texto, MesNome AS mes_nome
FROM dbo.DimMes
WHERE MesAno > ?
ORDER BY MesAno
"""

SELECT_DIM_DRE_CLASSIFICACAO = """
SELECT
    Id AS classificacao_id, Fonte AS fonte, Categoria AS categoria,
    GrupoDRE AS grupo_dre, SubGrupo AS subgrupo,
    OrdemGrupo AS ordem_grupo, Ativo AS ativo
FROM dbo.DREClassificacao
"""
