-- ============================================================================
-- ARQUIVO DE RECUPERACAO -- ANALYTICS.dbo.vw_DRE (DROPADA em 2026-05-31)
--
-- View legada de DRE (A7-especifica, banco custom ANALYTICS). Predecessora do
-- pipeline v2.0.0 do adapter Bitfin, que passou a montar o DRE direto das 3
-- tabelas NATIVAS do UNLTD_<cliente> (DemonstrativoDeResultado,
-- PagamentoOpcaoDePagamento, ComissaoComercialFechamento) + classifier no
-- gr_db (wh_dre_classification_rule). Ver adapters/erp/bitfin/version.py.
--
-- Motivo do DROP: ANALYTICS nao existe em tenant Bitfin novo; manter a view
-- dava falsa impressao de que o DRE depende dela. Confirmado antes do drop:
--   - 0 objetos no ANALYTICS referenciam vw_DRE (sql_expression_dependencies)
--   - nenhuma query do adapter faz fetch (so comentarios mencionam "vw_DRE")
--   - o DRE em producao le tabelas nativas, nao esta view
--
-- DDL preservada abaixo para recriacao caso necessario. A tabela companheira
-- ANALYTICS.dbo.DREClassificacao (de-para antigo) NAO foi dropada neste passo.
-- ============================================================================

CREATE VIEW [dbo].[vw_DRE] AS

-- ==============================================================
-- BLOCO 1: RECEITAS E CUSTOS OPERACIONAIS
-- Fonte: UNLTD_A7CREDIT.dbo.DemonstrativoDeResultado
-- ==============================================================
SELECT
    d.Ano,
    d.Mes,
    DATEFROMPARTS(d.Ano, d.Mes, 1)                                  AS Competencia,
    cls.OrdemGrupo,
    cls.GrupoDRE,
    cls.SubGrupo,
    d.Descricao,
    d.TotalApurado                                                   AS Receita,
    d.TotalDoCusto                                                   AS Custo,
    d.Resultado,
    d.Quantidade,
    CAST(NULL AS VARCHAR(200))                                       AS Fornecedor,
    CAST(NULL AS VARCHAR(20))                                        AS FornecedorDocumento,
    d.EntidadeId,
    d.ProdutoId,
    d.UnidadeAdministrativaId,
    cls.Fonte
FROM UNLTD_A7CREDIT.dbo.DemonstrativoDeResultado d
JOIN dbo.DREClassificacao cls
    ON cls.Fonte = 'DRE_OPERACIONAL'
    AND cls.Categoria = d.Categoria

UNION ALL

-- ==============================================================
-- BLOCO 2: DESPESAS ADMINISTRATIVAS (REGIME DE COMPETENCIA)
-- Fonte: UNLTD_A7CREDIT.dbo.PagamentoOpcaoDePagamento
-- UA via: PagamentoOperacao.UnidadeAdministrativaId
-- ==============================================================
SELECT
    YEAR(p.DataDeEmissao)                                            AS Ano,
    MONTH(p.DataDeEmissao)                                           AS Mes,
    DATEFROMPARTS(YEAR(p.DataDeEmissao), MONTH(p.DataDeEmissao), 1) AS Competencia,
    cls.OrdemGrupo,
    cls.GrupoDRE,
    cls.SubGrupo,
    p.Categoria                                                      AS Descricao,
    CAST(0 AS DECIMAL(18,5))                                         AS Receita,
    p.Valor                                                          AS Custo,
    -p.Valor                                                         AS Resultado,
    CAST(1 AS INT)                                                   AS Quantidade,
    e.Nome                                                           AS Fornecedor,
    e.Documento                                                      AS FornecedorDocumento,
    CAST(NULL AS INT)                                                AS EntidadeId,
    CAST(NULL AS INT)                                                AS ProdutoId,
    po.UnidadeAdministrativaId,
    cls.Fonte
FROM      UNLTD_A7CREDIT.dbo.PagamentoOpcaoDePagamento p
JOIN      UNLTD_A7CREDIT.dbo.PagamentoOperacao po ON p.OperacaoDePagamentosId = po.OperacaoDePagamentosId
JOIN      UNLTD_A7CREDIT.dbo.Fornecedor  f ON p.FornecedorId = f.FornecedorId
JOIN      UNLTD_A7CREDIT.dbo.Entidade    e ON f.EntidadeId   = e.EntidadeId
JOIN      dbo.DREClassificacao cls
    ON cls.Fonte = 'CONTAS_A_PAGAR'
    AND cls.Categoria = p.Categoria
WHERE cls.Ativo = 1

UNION ALL

-- ==============================================================
-- BLOCO 3: COMISSOES COMERCIAIS
-- Fonte: UNLTD_A7CREDIT.dbo.ComissaoComercialFechamento
-- UA via: MembroInterno.UnidadeAdministrativaId
-- ==============================================================
SELECT
    c.Ano,
    c.Mes,
    DATEFROMPARTS(c.Ano, c.Mes, 1)                                  AS Competencia,
    cls.OrdemGrupo,
    cls.GrupoDRE,
    cls.SubGrupo,
    cls.Categoria                                                    AS Descricao,
    CAST(0 AS DECIMAL(18,5))                                         AS Receita,
    c.Comissao                                                       AS Custo,
    -c.Comissao                                                      AS Resultado,
    CAST(1 AS INT)                                                   AS Quantidade,
    CAST(NULL AS VARCHAR(200))                                       AS Fornecedor,
    CAST(NULL AS VARCHAR(20))                                        AS FornecedorDocumento,
    CAST(NULL AS INT)                                                AS EntidadeId,
    CAST(NULL AS INT)                                                AS ProdutoId,
    mi.UnidadeAdministrativaId,
    cls.Fonte
FROM UNLTD_A7CREDIT.dbo.ComissaoComercialFechamento c
JOIN UNLTD_A7CREDIT.dbo.MembroInterno mi ON c.MembroInternoId = mi.MembroInternoId
CROSS JOIN dbo.DREClassificacao cls
WHERE cls.Fonte = 'COMISSAO'
  AND cls.Categoria = N'Comissao de Consultor'
  AND c.Comissao > 0
