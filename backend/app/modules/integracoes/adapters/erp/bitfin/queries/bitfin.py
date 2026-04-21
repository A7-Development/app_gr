"""Queries contra o database UNLTD_A7CREDIT (Bitfin ERP)."""

SELECT_OPERACAO = """
SELECT
    o.OperacaoId AS operacao_id,
    o.DataDeCadastro AS data_de_cadastro,
    o.DataDeEfetivacao AS data_de_efetivacao,
    o.Efetivada AS efetivada,
    o.QuantidadeDeTitulos AS quantidade_de_titulos,
    o.Origem AS origem,
    o.Modalidade AS modalidade,
    o.Coobrigacao AS coobrigacao,
    o.CodigoDeRegistro AS codigo_de_registro,
    o.ContratoId AS contrato_id,
    o.Tags AS tags,
    o.ContaOperacionalId AS conta_operacional_id,
    o.UnidadeAdministrativaId AS unidade_administrativa_id,
    r.PrazoMedioReal AS prazo_medio_real,
    r.PrazoMedioCobrado AS prazo_medio_cobrado,
    r.TotalBruto AS total_bruto,
    r.TotalLiquido AS total_liquido,
    r.TotalDeJuros AS total_de_juros,
    r.TotalDeAdValorem AS total_de_ad_valorem,
    r.TotalDeIof AS total_de_iof,
    r.TotalDeImposto AS total_de_imposto,
    r.TotalDeRebate AS total_de_rebate,
    r.ValorMedioDosTitulos AS valor_medio_dos_titulos,
    r.ValorMedioPorSacado AS valor_medio_por_sacado,
    r.QuantidadeDeSacados AS quantidade_de_sacados,
    r.TaxaDeJuros AS taxa_de_juros,
    r.TaxaDeAdValorem AS taxa_de_ad_valorem,
    r.TaxaDeIof AS taxa_de_iof,
    r.TaxaDeImposto AS taxa_de_imposto,
    r.TaxaDeRebate AS taxa_de_rebate,
    r.Spread AS spread,
    r.FatorDeDescontoCobrado AS fator_de_desconto_cobrado,
    r.FatorDeDescontoReal AS fator_de_desconto_real,
    r.FloatingParaPrazo AS floating_para_prazo,
    r.TotalDasConsultasFinanceiras AS total_das_consultas_financeiras,
    r.TotalDosRegistrosBancarios AS total_dos_registros_bancarios,
    r.TotalDasConsultasFiscais AS total_das_consultas_fiscais,
    r.TotalDosComunicadosDeCessao AS total_dos_comunicados_de_cessao,
    r.TotalDosDocumentosDigitais AS total_dos_documentos_digitais,
    r.TotalDosDescontosOuAbatimentos AS total_dos_descontos_ou_abatimentos,
    r.DataDoUltimoVencimento AS data_do_ultimo_vencimento
FROM dbo.Operacao o
LEFT JOIN dbo.OperacaoResultado r
    ON r.ResultadoDaOperacaoId = o.ResultadoDaOperacaoId
WHERE o.DataDeCadastro > ?
"""

SELECT_OPERACAO_ITEM = """
SELECT
    ItemDaOperacaoId AS item_da_operacao_id,
    OperacaoId AS operacao_id,
    TituloId AS titulo_id,
    ValorBase AS valor_base,
    ValorLiquido AS valor_liquido,
    ValorPresente AS valor_presente,
    ValorDeJuros AS valor_de_juros,
    ValorDoAdValorem AS valor_do_ad_valorem,
    ValorDoIof AS valor_do_iof,
    ValorDoRebate AS valor_do_rebate,
    SaldoDevedor AS saldo_devedor,
    PrazoReal AS prazo_real,
    PrazoCobrado AS prazo_cobrado,
    DataDeVencimentoOriginal AS data_de_vencimento_original,
    SugeridoParaExclusao AS sugerido_para_exclusao
FROM dbo.OperacaoItem
WHERE OperacaoId IS NOT NULL
"""

SELECT_TITULO = """
SELECT
    TituloId AS titulo_id,
    Sigla AS sigla, Numero AS numero,
    DataDeEmissao AS data_de_emissao,
    DataDeVencimento AS data_de_vencimento,
    DataDeVencimentoEfetiva AS data_de_vencimento_efetiva,
    DataDeCadastro AS data_de_cadastro,
    DataDaSituacao AS data_da_situacao,
    DataDoStatus AS data_do_status,
    Valor AS valor, ValorDoPagamento AS valor_do_pagamento,
    ValorLiquido AS valor_liquido, SaldoDevedor AS saldo_devedor,
    Situacao AS situacao, Status AS status, Meio AS meio,
    SacadoId AS sacado_id,
    ContaOperacionalId AS conta_operacional_id,
    UnidadeAdministrativaId AS unidade_administrativa_id,
    OperacaoId AS operacao_id,
    SubscricaoId AS subscricao_id,
    RetencaoId AS retencao_id,
    DataPermitidaParaProtesto AS data_permitida_para_protesto,
    DataDaSolicitacaoDoProtesto AS data_da_solicitacao_do_protesto,
    DataDoEnvioAoCartorio AS data_do_envio_ao_cartorio,
    DataDoProtesto AS data_do_protesto,
    DataDaSustacaoDoProtesto AS data_da_sustacao_do_protesto,
    DataDoCancelamentoDoProtesto AS data_do_cancelamento_do_protesto,
    SustadoJudicialmente AS sustado_judicialmente,
    DataPermitidaParaNegativacao AS data_permitida_para_negativacao,
    DataDaNegativacao AS data_da_negativacao,
    DataDoCancelamentoDaNegativacao AS data_do_cancelamento_da_negativacao,
    CodigoDeRegistro AS codigo_de_registro,
    Tags AS tags
FROM dbo.Titulo
WHERE DataDaSituacao > ?
"""


# Dimensao: Unidade Administrativa (UA).
# Bitfin usa `Alias` como display name (nao tem campo "Nome" propriamente
# dito). Full refresh sempre — poucas linhas (3 no ambiente atual), mudam
# raramente. Popula `wh_dim_unidade_administrativa`.
SELECT_UNIDADE_ADMINISTRATIVA = """
SELECT
    UnidadeAdministrativaId AS ua_id,
    Alias AS nome,
    Ativa AS ativa,
    Classe AS classe
FROM dbo.UnidadeAdministrativa
"""


# Dimensao: Produto.
# `Descricao` e o nome amigavel (ex.: "Faturização"); `Sigla` e o codigo
# curto (ex.: "FAT") que aparece como prefixo em `Operacao.Modalidade`.
# Popula `wh_dim_produto`.
SELECT_PRODUTO = """
SELECT
    ProdutoId AS produto_id,
    Sigla AS sigla,
    Descricao AS nome,
    TipoDeContrato AS tipo_de_contrato,
    ProdutoDeRisco AS produto_de_risco
FROM dbo.Produto
"""

