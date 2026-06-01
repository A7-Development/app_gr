"""Queries contra o database UNLTD_<cliente> (Bitfin ERP).

A partir do adapter v2.0.0 todas as fontes do DRE vivem aqui (mais nenhum
fetch contra ANALYTICS para o caminho critico do DRE). Tres fontes:

- DemonstrativoDeResultado (bloco 1: receitas/custos operacionais)
- PagamentoOpcaoDePagamento (bloco 2: despesas administrativas)
- ComissaoComercialFechamento (bloco 3: comissoes comerciais)
"""

# ─── Relay Serasa (consultas Serasa armazenadas no Bitfin) ─────────────────
# Incremental por ConsultaFinanceiraId (IDENTITY, append-only). TOP (?) limita
# o lote; o 2o ? e o watermark. Fonte fixa em Relato PJ (o mapper seg-028 do GR
# so consome esse produto). Relatorio = varbinary gzip(JSON) → bytes no pyodbc.
SELECT_CONSULTA_FINANCEIRA_SINCE_ID = """
SELECT TOP (?) ConsultaFinanceiraId, Documento, DataFinal, Relatorio
FROM dbo.ConsultaFinanceira
WHERE ConsultaFinanceiraId > ? AND Fonte = 'Serasa - Relato PJ'
ORDER BY ConsultaFinanceiraId
"""

SELECT_DRE_DEMONSTRATIVO_RAW = """
SELECT
    Ano AS ano, Mes AS mes,
    -- Competencia derivada de (Ano, Mes) — DemonstrativoDeResultado nao tem
    -- coluna explicita; e o campo natural para agrupar o snapshot na bronze.
    CAST(DATEFROMPARTS(Ano, Mes, 1) AS DATE) AS competencia,
    Data AS snapshot_at,
    Categoria AS categoria, Descricao AS descricao,
    TotalApurado AS total_apurado,
    Quantidade AS quantidade,
    TotalDoCusto AS total_do_custo,
    Resultado AS resultado,
    EntidadeId AS entidade_id,
    ProdutoId AS produto_id,
    UnidadeAdministrativaId AS unidade_administrativa_id,
    GerenteId AS gerente_id,
    SubgerenteId AS subgerente_id,
    SuperintendenteId AS superintendente_id,
    DiretorId AS diretor_id
FROM dbo.DemonstrativoDeResultado
WHERE DATEFROMPARTS(Ano, Mes, 1) >= ?
ORDER BY competencia, EntidadeId, Categoria, Descricao
"""

# Catalogo de tarifas/encargos (OrganizacaoTarifa) -- template da organizacao.
# Vocabulario CONTROLADO de (Categoria, Descricao) + Tipo (1=tarifa fixa,
# 2=encargo variavel) que ancora a classificacao por NATUREZA do DRE
# (wh_bitfin_dre_natureza_rule). ~60 linhas; full refresh por sync.
SELECT_ORGANIZACAO_TARIFA = """
SELECT
    Categoria AS categoria,
    Descricao AS descricao,
    Tipo AS tipo,
    Comissionada AS comissionada
FROM dbo.OrganizacaoTarifa
ORDER BY Categoria, Descricao
"""

# Dim de entidades (cedentes) -- resolve entidade_id -> nome/documento para
# os agregados do DRE. Entidade tem ~20k linhas; ingerimos so o subconjunto
# referenciado pelo DemonstrativoDeResultado (~90). Full refresh por sync.
SELECT_ENTIDADE_DRE = """
SELECT e.EntidadeId AS entidade_id, e.Nome AS nome, e.Documento AS documento
FROM dbo.Entidade e
WHERE e.EntidadeId IN (
    SELECT DISTINCT EntidadeId
    FROM dbo.DemonstrativoDeResultado
    WHERE EntidadeId IS NOT NULL
)
ORDER BY e.EntidadeId
"""

# Bronze: PagamentoOpcaoDePagamento (despesas administrativas — bloco 2
# do DRE). Vw_DRE original usa INNER JOIN com DREClassificacao filtrando
# `Ativo=1`; aqui mantemos LEFT JOIN com Fornecedor/Entidade (preservando
# linhas sem fornecedor) e SEM filtro de classificacao — o filtro acontece
# no silver mapper apos consultar `wh_dre_classification_rule`.
#
# Competencia derivada de DataDeEmissao (regime de competencia).
#
# Volume tipico: 45-156 linhas/competencia (A7 Credit 2025/2026). Payload
# JSONB cabe num row de bronze sem stress.
SELECT_DRE_PAGAMENTO_RAW = """
SELECT
    p.OpcaoDePagamentoId AS opcao_de_pagamento_id,
    YEAR(p.DataDeEmissao) AS ano,
    MONTH(p.DataDeEmissao) AS mes,
    CAST(DATEFROMPARTS(YEAR(p.DataDeEmissao), MONTH(p.DataDeEmissao), 1) AS DATE) AS competencia,
    p.Categoria AS categoria,
    p.Tipo AS tipo,
    p.Direcao AS direcao,
    p.Valor AS valor,
    p.ValorAtualizado AS valor_atualizado,
    p.DataDeEmissao AS data_de_emissao,
    p.DataDeVencimento AS data_de_vencimento,
    p.DataDePagamento AS data_de_pagamento,
    p.DataParaPagamento AS data_para_pagamento,
    p.Pago AS pago,
    p.FornecedorId AS fornecedor_id,
    p.OperacaoDePagamentosId AS operacao_de_pagamentos_id,
    po.UnidadeAdministrativaId AS unidade_administrativa_id,
    e.EntidadeId AS entidade_id_fornecedor,
    e.Nome AS fornecedor_nome,
    e.Documento AS fornecedor_documento,
    p.Observacoes AS observacoes,
    p.DescricaoDoLancamento AS descricao_do_lancamento
FROM dbo.PagamentoOpcaoDePagamento p
LEFT JOIN dbo.PagamentoOperacao po
    ON p.OperacaoDePagamentosId = po.OperacaoDePagamentosId
LEFT JOIN dbo.Fornecedor f
    ON p.FornecedorId = f.FornecedorId
LEFT JOIN dbo.Entidade e
    ON f.EntidadeId = e.EntidadeId
WHERE DATEFROMPARTS(YEAR(p.DataDeEmissao), MONTH(p.DataDeEmissao), 1) >= ?
ORDER BY competencia, opcao_de_pagamento_id
"""


# Bronze: ComissaoComercialFechamento (comissoes comerciais — bloco 3
# do DRE). Granularidade fonte: 1 row por (MembroInterno, Ano, Mes).
# Volume: ~3 linhas/competencia.
#
# Vw_DRE original filtra `Comissao > 0`; aqui preservamos todas as rows
# (zero/negativo pode ser util para auditoria), filtro acontece no silver.
SELECT_DRE_COMISSAO_RAW = """
SELECT
    c.MembroInternoId AS membro_interno_id,
    c.Ano AS ano,
    c.Mes AS mes,
    CAST(DATEFROMPARTS(c.Ano, c.Mes, 1) AS DATE) AS competencia,
    c.Data AS data_snapshot,
    c.ResultadoPositivo AS resultado_positivo,
    c.ResultadoNegativo AS resultado_negativo,
    c.ResultadoBruto AS resultado_bruto,
    c.PercentualMedio AS percentual_medio,
    c.ResultadoFinal AS resultado_final,
    c.ComissaoGarantidaAplicada AS comissao_garantida_aplicada,
    c.ValorDaComissaoGarantida AS valor_da_comissao_garantida,
    c.SaldoDevedor AS saldo_devedor,
    c.Comissao AS comissao,
    c.SaldoAnterior AS saldo_anterior,
    mi.UnidadeAdministrativaId AS unidade_administrativa_id
FROM dbo.ComissaoComercialFechamento c
LEFT JOIN dbo.MembroInterno mi
    ON c.MembroInternoId = mi.MembroInternoId
WHERE DATEFROMPARTS(c.Ano, c.Mes, 1) >= ?
ORDER BY competencia, membro_interno_id
"""


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
    r.DataDoUltimoVencimento AS data_do_ultimo_vencimento,
    -- Cedente (= Cliente, no vocabulario Bitfin). Resolvido via
    -- ContaOperacional (modelo 1:1, validado em 2026-05-22: 9269/9269
    -- ops historicas resolveram). Documento e o CNPJ/CPF formatado
    -- como string (sem mascara — exatamente como Bitfin armazena).
    cli.ClienteId AS cedente_id,
    ent.Nome AS cedente_nome,
    ent.Documento AS cedente_documento
FROM dbo.Operacao o
LEFT JOIN dbo.OperacaoResultado r
    ON r.ResultadoDaOperacaoId = o.ResultadoDaOperacaoId
LEFT JOIN dbo.ContaOperacional co
    ON co.ContaOperacionalId = o.ContaOperacionalId
LEFT JOIN dbo.Cliente cli
    ON cli.ClienteId = co.ClienteId
LEFT JOIN dbo.Entidade ent
    ON ent.EntidadeId = cli.EntidadeId
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
#
# Campos estruturais (Tipo + Entidade*) introduzidos em 2026-05-09 para
# suportar VOP Potencial (filtro por FIDC/Securitizadora) e joins canonicos
# multi-tenant (Conta-Bancaria.EntidadeId -> UA.EntidadeId).
SELECT_UNIDADE_ADMINISTRATIVA = """
SELECT
    UnidadeAdministrativaId AS ua_id,
    Alias AS nome,
    Ativa AS ativa,
    Classe AS classe,
    Tipo AS tipo,
    EntidadeId AS entidade_id,
    EntidadeIdAdministradora AS entidade_id_administradora,
    EntidadeIdGestora AS entidade_id_gestora,
    EntidadeIdCustodiante AS entidade_id_custodiante
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


# Caixa Snapshot — saldo atual de cada ContaBancaria de UA do fundo.
# Popula `wh_caixa_snapshot` com 1 linha por (conta_bancaria_id, hoje).
#
# Joins:
#   ContaBancaria cb         -- identidade da conta + flags estruturais
#   ContaCorrente cc         -- saldo (cb -> cc via cb.ContaCorrenteId)
#   UnidadeAdministrativa ua -- ownership por EntidadeId direto
#   ContaBancariaCaucao cau  -- presenca = conta caucionada
#   ContaBancariaTrava trv   -- presenca = conta travada
#
# Filtros: INNER JOIN UA via EntidadeId garante que apenas contas DE UA
# (nao contas de cedentes ou avalistas) entrem. NAO filtra por `ua.Tipo`
# aqui -- captura todas as UAs (incl. Tipo NULL "outras" como Onboard) e
# deixa o BI service filtrar por estrutura quando preciso (saldo medio /
# eficiencia comercial e valido em qualquer UA; VOP Potencial filtra
# Tipo IN (1, 2)). Conta com `ContaCorrenteId IS NULL` (raras) sao
# ignoradas via INNER JOIN ContaCorrente.
SELECT_CAIXA_SNAPSHOT = """
SELECT
    cb.ContaBancariaId AS conta_bancaria_id,
    cb.ContaCorrenteId AS conta_corrente_id,
    cb.Numero AS numero,
    cb.Descricao AS descricao,
    cb.Tipo AS conta_bancaria_tipo,
    cb.BancoId AS banco_id,
    cb.AgenciaId AS agencia_id,
    ua.UnidadeAdministrativaId AS unidade_administrativa_id,
    cb.Ativa AS ativa,
    cb.Escrow AS eh_escrow,
    CASE WHEN cau.ContaBancariaId IS NOT NULL THEN 1 ELSE 0 END AS eh_caucao,
    CASE WHEN trv.ContaBancariaId IS NOT NULL THEN 1 ELSE 0 END AS eh_travada,
    cc.Saldo AS saldo
FROM dbo.ContaBancaria cb
INNER JOIN dbo.ContaCorrente cc
    ON cc.ContaCorrenteId = cb.ContaCorrenteId
INNER JOIN dbo.UnidadeAdministrativa ua
    ON ua.EntidadeId = cb.EntidadeId
LEFT JOIN dbo.ContaBancariaCaucao cau
    ON cau.ContaBancariaId = cb.ContaBancariaId
   AND cau.Ativa = 1
LEFT JOIN dbo.ContaBancariaTrava trv
    ON trv.ContaBancariaId = cb.ContaBancariaId
"""

