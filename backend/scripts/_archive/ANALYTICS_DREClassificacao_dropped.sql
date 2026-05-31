-- ============================================================================
-- ARQUIVO DE RECUPERACAO -- ANALYTICS.dbo.DREClassificacao (DROPADA 2026-05-31)
--
-- De-para legado (Fonte, Categoria) -> (GrupoDRE, SubGrupo, OrdemGrupo, Ativo).
-- Era consumido APENAS pela ANALYTICS.dbo.vw_DRE (ja dropada). Banco custom
-- A7-especifico (ANALYTICS), nao existe em tenant Bitfin novo.
--
-- SUPERADO por: gr_db.public.wh_dre_classification_rule (mesmas 77 regras,
-- migradas no adapter v2.0.0). A fonte de verdade viva e o gr_db -- este dump
-- e so para auditoria/historico. 0 dependentes confirmado antes do drop.
-- ============================================================================

CREATE TABLE [dbo].[DREClassificacao] (
    [Id]         INT            IDENTITY(1,1) NOT NULL,
    [Fonte]      VARCHAR(30)    NOT NULL,
    [Categoria]  NVARCHAR(200)  NOT NULL,
    [GrupoDRE]   NVARCHAR(50)   NOT NULL,
    [SubGrupo]   NVARCHAR(100)  NOT NULL,
    [OrdemGrupo] INT            NOT NULL,
    [Ativo]      BIT            NOT NULL CONSTRAINT [DF_DREClassificacao_Ativo] DEFAULT (1),
    CONSTRAINT [PK_DREClassificacao] PRIMARY KEY CLUSTERED ([Id]),
    CONSTRAINT [UQ_DREClassificacao_Fonte_Categoria] UNIQUE ([Fonte], [Categoria])
);

-- Dados (77 linhas) -- Id | Fonte | Categoria | GrupoDRE | SubGrupo | OrdemGrupo | Ativo
-- Copia viva e identica em gr_db.public.wh_dre_classification_rule.
--   EXCLUIDO (CONTAS_A_PAGAR, OrdemGrupo 0, Ativo 0): Cartao de Credito,
--     Contribuicao/Doacao, Estorno, Investimento, Outras Tarifas Bancarias,
--     Pagamento Operacional, Tomada de Recursos
--   RECEITA_OPERACIONAL (DRE_OPERACIONAL): Operacao(1), Credito Estruturado(2),
--     Recompra(3), Titulo(4), Conta Grafica(5), Despesa(7)
--   PROVISAO_PDD (DRE_OPERACIONAL): PDD(6)
--   DESPESA_ADMINISTRATIVA (CONTAS_A_PAGAR, OrdemGrupo 8): subgrupos Pessoal,
--     Beneficios, Tributos e Impostos, Servicos de Terceiros, Ocupacao e
--     Utilidades, Transporte e Veiculos, Marketing e Publicidade, Assinaturas
--     e Sistemas, Viagens e Deslocamentos, Outros
--   COMISSAO_COMERCIAL (COMISSAO): Comissao de Consultor(9)
-- (dump tabular completo preservado no historico do gr_db; ver
--  wh_dre_classification_rule WHERE valid_until IS NULL)
