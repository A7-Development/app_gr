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
# 2=encargo variavel) -- base do catalogo de receitas operacionais e
# detector de item novo. ~60 linhas; full refresh por sync.
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


# ---- Reconcile (anti-join): conjunto VIVO de ids no Bitfin, id-only ----
#
# Sem watermark — precisamos do universo INTEIRO para detectar delecoes
# (o que existe no espelho mas nao aqui = orfao). Usadas por
# `etl.reconcile_bitfin_mirror` (hard-delete de orfaos no gr_db). Cada
# filtro espelha o da sync correspondente para nao marcar como orfa uma
# linha que a sync nunca ingeriu (ex.: OperacaoItem sem OperacaoId).

SELECT_TITULO_IDS = "SELECT TituloId AS source_id FROM dbo.Titulo"

SELECT_OPERACAO_IDS = "SELECT OperacaoId AS source_id FROM dbo.Operacao"

SELECT_OPERACAO_ITEM_IDS = (
    "SELECT ItemDaOperacaoId AS source_id FROM dbo.OperacaoItem "
    "WHERE OperacaoId IS NOT NULL"
)


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

# Posicao de debentures AO VIVO (snapshot diario). `DebentureSubscricao.
# TotalBruto/TotalLiquido/Valor` sao mantidos pela Bitfin com correcao diaria
# (CorrecaoDiaria=1, CDI+spread) -- e por subscricao (cada uma acumula sobre o
# seu proprio principal/data de integralizacao). Conferido: SUM(TotalBruto) das
# Integralizadas == fechamento mensal de PosicaoHistoricaDebenture do mes
# corrente. UA via DebentureEscritura.UnidadeAdministrativaId.
SELECT_DEBENTURE_POSICAO_LIVE = """
SELECT s.SubscricaoId               AS subscricao_id,
       esc.UnidadeAdministrativaId  AS ua_id,
       s.QuantidadeDeDebenturesAtual AS quantidade,
       s.Valor                      AS valor,
       s.TotalBruto                 AS total_bruto,
       s.TotalLiquido               AS total_liquido
FROM dbo.DebentureSubscricao s
JOIN dbo.DebentureSerie se     ON se.SerieId = s.SerieId
JOIN dbo.DebentureEscritura esc ON esc.EscrituraId = se.EscrituraId
WHERE s.Status = 'Integralizada'
ORDER BY esc.UnidadeAdministrativaId, s.SubscricaoId
"""



# ---- Party model (wh_entidade + papeis + grupo economico) ----
# Entidade completa (nao confundir com SELECT_ENTIDADE_DRE, que e o
# subconjunto ~90 referenciado no DRE). `Documento` vem zero-padded a
# 15 chars para PJ e 11 para PF — normalizacao em app/shared/documento.py.
SELECT_ENTIDADE_FULL = """
SELECT
    e.EntidadeId AS entidade_id,
    e.Tipo AS tipo,
    e.Documento AS documento,
    e.Nome AS nome,
    e.ChaveDoCnae AS cnae_chave,
    c.Denominacao AS cnae_denominacao,
    e.Porte AS porte,
    e.DataDeConstituicao AS data_constituicao,
    e.EmRecuperacaoJudicial AS em_recuperacao_judicial,
    e.DataDaRecuperacaoJudicial AS data_recuperacao_judicial,
    e.Logradouro AS logradouro,
    e.Numero AS endereco_numero,
    e.Complemento AS complemento,
    e.Bairro AS bairro,
    e.Localidade AS localidade,
    e.Estado AS estado,
    e.Cep AS cep,
    e.Pais AS pais,
    e.EnderecoVerificado AS endereco_verificado,
    e.GrupoEconomicoId AS grupo_economico_source_id,
    e.DataDeCadastro AS data_cadastro_fonte
FROM dbo.Entidade e
LEFT JOIN dbo.Cnae c
    ON c.Chave = e.ChaveDoCnae
"""

# Papel CEDENTE (Cliente, no vocabulario Bitfin). ClienteId e a ponte
# para wh_operacao.cedente_id.
SELECT_CLIENTE_PAPEL = """
SELECT
    ClienteId AS papel_source_id,
    EntidadeId AS entidade_source_id,
    Status AS status_int,
    Situacao AS situacao,
    DataDeCadastro AS data_cadastro_fonte
FROM dbo.Cliente
"""

# Papel SACADO. SacadoId e a ponte para wh_titulo.sacado_id.
SELECT_SACADO_PAPEL = """
SELECT
    SacadoId AS papel_source_id,
    EntidadeId AS entidade_source_id,
    DataDeCadastro AS data_cadastro_fonte
FROM dbo.Sacado
"""

SELECT_GRUPO_ECONOMICO = """
SELECT
    GrupoEconomicoId AS grupo_source_id,
    Nome AS nome,
    Segmento AS segmento,
    QuantidadeDeMembros AS quantidade_membros,
    DataDeCadastro AS data_cadastro_fonte
FROM dbo.GrupoEconomico
"""

SELECT_GRUPO_ECONOMICO_MEMBRO = """
SELECT
    GrupoEconomicoId AS grupo_source_id,
    EntidadeId AS entidade_source_id,
    Vinculo AS vinculo,
    DataDeCadastro AS data_cadastro_fonte
FROM dbo.GrupoEconomicoMembro
"""


# ---- Posicoes por papel (F1 do party model) ----
# Snapshots consolidados que o Bitfin calcula por papel. JOIN com Cliente/
# Sacado traz a ponte (ClienteId/SacadoId + EntidadeId) para ancorar na
# entidade canonica.
SELECT_POSICAO_CEDENTE = """
SELECT
    cp.PosicaoId AS posicao_id,
    c.ClienteId AS papel_source_id,
    c.EntidadeId AS entidade_source_id,
    cp.RiscoTotalQuantidade AS risco_total_qtd,
    cp.RiscoTotalTotal AS risco_total_valor,
    cp.RiscoVencidoQuantidade AS risco_vencido_qtd,
    cp.RiscoVencidoTotal AS risco_vencido_valor,
    cp.RiscoAVencerQuantidade AS risco_avencer_qtd,
    cp.RiscoAVencerTotal AS risco_avencer_valor,
    cp.PrazoMedioDeFaturamento AS prazo_medio_carteira,
    cp.IndiceDeLiquidez AS indice_liquidez,
    cp.VencimentarioDaLiquidez AS vencimentario_liquidez,
    cp.QtdeDeDiasDaLiquidez AS liquidez_qtde_dias,
    cp.DataInicialDaLiquidez AS liquidez_data_inicial,
    cp.DataFinalDaLiquidez AS liquidez_data_final,
    cp.TotalDosLiquidadosDaLiquidez AS liquidez_total_liquidados,
    cp.TotalDosRecompradosDaLiquidez AS liquidez_total_recomprados,
    cp.TotalDoVencidosPenalizadosDaLiquidez AS liquidez_total_vencidos_penalizados,
    cp.TotalDoVencidosNaoPenalizadosDaLiquidez AS liquidez_total_vencidos_nao_penalizados,
    cp.DataDeApuracaoDaLiquidez AS liquidez_data_apuracao
FROM dbo.ClientePosicao cp
INNER JOIN dbo.Cliente c
    ON c.PosicaoId = cp.PosicaoId
"""

SELECT_POSICAO_CEDENTE_PRODUTO = """
SELECT
    cpp.PosicaoId AS posicao_id,
    cpp.ProdutoId AS produto_source_id,
    pr.Sigla AS produto_sigla,
    c.ClienteId AS papel_source_id,
    c.EntidadeId AS entidade_source_id,
    cpp.LimiteOperacional AS limite_operacional,
    cpp.Tranche AS tranche,
    cpp.IndiceDeLiquidez AS indice_liquidez,
    cpp.RiscoTotalQuantidade AS risco_total_qtd,
    cpp.RiscoTotalTotal AS risco_total_valor,
    cpp.RiscoVencidoQuantidade AS risco_vencido_qtd,
    cpp.RiscoVencidoTotal AS risco_vencido_valor,
    cpp.RiscoAVencerQuantidade AS risco_avencer_qtd,
    cpp.RiscoAVencerTotal AS risco_avencer_valor,
    cpp.HistoricoDeLiquidacoesQuantidade AS hist_liquidacoes_qtd,
    cpp.HistoricoDeLiquidacoesTotal AS hist_liquidacoes_valor,
    cpp.HistoricoDeBaixadosQuantidade AS hist_baixados_qtd,
    cpp.HistoricoDeBaixadosTotal AS hist_baixados_valor
FROM dbo.ClientePosicaoProduto cpp
INNER JOIN dbo.Cliente c
    ON c.PosicaoId = cpp.PosicaoId
LEFT JOIN dbo.Produto pr
    ON pr.ProdutoId = cpp.ProdutoId
"""

SELECT_POSICAO_SACADO = """
SELECT
    sp.PosicaoId AS posicao_id,
    s.SacadoId AS papel_source_id,
    s.EntidadeId AS entidade_source_id,
    sp.RiscoTotalQuantidade AS risco_total_qtd,
    sp.RiscoTotalTotal AS risco_total_valor,
    sp.RiscoVencidoQuantidade AS risco_vencido_qtd,
    sp.RiscoVencidoTotal AS risco_vencido_valor,
    sp.RiscoAVencerQuantidade AS risco_avencer_qtd,
    sp.RiscoAVencerTotal AS risco_avencer_valor,
    sp.TicketMedio AS ticket_medio,
    sp.IndiceDePontualidade AS indice_pontualidade,
    sp.ProrrogadosQuantidade AS prorrogados_qtd,
    sp.ProrrogadosTotal AS prorrogados_valor,
    sp.PrazoMedioDeProrrogacao AS prazo_medio_prorrogacao,
    sp.HistoricoDeTitulosQuantidade AS hist_titulos_qtd,
    sp.HistoricoDeTitulosTotal AS hist_titulos_valor,
    sp.HistoricoDeLiquidacoesQuantidade AS hist_liquidacoes_qtd,
    sp.HistoricoDeLiquidacoesTotal AS hist_liquidacoes_valor,
    sp.HistoricoDeRecomprasQuantidade AS hist_recompras_qtd,
    sp.HistoricoDeRecomprasTotal AS hist_recompras_valor,
    sp.IndiceDeLiquidez AS indice_liquidez,
    sp.VencimentarioDaLiquidez AS vencimentario_liquidez,
    sp.QtdeDeDiasDaLiquidez AS liquidez_qtde_dias,
    sp.DataInicialDaLiquidez AS liquidez_data_inicial,
    sp.DataFinalDaLiquidez AS liquidez_data_final,
    sp.TotalDosLiquidadosDaLiquidez AS liquidez_total_liquidados,
    sp.TotalDosRecompradosDaLiquidez AS liquidez_total_recomprados,
    sp.TotalDoVencidosPenalizadosDaLiquidez AS liquidez_total_vencidos_penalizados,
    sp.TotalDoVencidosNaoPenalizadosDaLiquidez AS liquidez_total_vencidos_nao_penalizados,
    sp.DataDeApuracaoDaLiquidez AS liquidez_data_apuracao
FROM dbo.SacadoPosicao sp
INNER JOIN dbo.Sacado s
    ON s.PosicaoId = sp.PosicaoId
"""


# ---- Catalogo de receitas operacionais (caixa-fiel) ----
# Fontes que refletem liquidacao financeira REAL — nunca a
# DemonstrativoDeResultado (mora teorica). Consumidas por receitas.py,
# dirigidas pelo catalogo wh_bitfin_receita_stream.

# Mora paga na liquidacao do titulo. Espelha o filtro da proc
# DemonstrativoDeResultados (DM/DS/NP, produto de risco, pago apos o
# vencimento efetivo) mas captura o CAIXA (ValorDoPagamento - ValorLiquido),
# nao o teorico. Percentuais do ProcedimentoDeCobranca vem como PARAMETRO
# para o split juros x multa (LEFT JOIN: titulo sem procedimento -> split
# 100% juros). `dias_atraso` contra o vencimento ORIGINAL (convencao da
# proc e do acruo).
SELECT_RECEITA_MORA_TITULO = """
SELECT
    t.TituloId AS titulo_id,
    t.Numero AS documento,
    CONVERT(date, t.DataDaSituacao) AS data_evento,
    t.ValorLiquido AS valor_liquido,
    t.ValorDoPagamento AS valor_do_pagamento,
    DATEDIFF(DAY, t.DataDeVencimento, CONVERT(date, t.DataDaSituacao)) AS dias_atraso,
    pc.PercentualDeMultaPorAtraso AS pct_multa,
    pc.PercentualDeJurosDeMora AS pct_juros,
    t.UnidadeAdministrativaId AS unidade_administrativa_id,
    co.ProdutoId AS produto_id,
    ce.EntidadeId AS cedente_entidade_id,
    ce.Nome AS cedente_nome,
    ce.Documento AS cedente_documento,
    se.Nome AS sacado_nome,
    se.Documento AS sacado_documento
FROM dbo.Titulo t
INNER JOIN dbo.ContaOperacional co ON co.ContaOperacionalId = t.ContaOperacionalId
INNER JOIN dbo.Produto p ON p.ProdutoId = co.ProdutoId
LEFT JOIN dbo.ProcedimentoDeCobranca pc ON pc.TituloId = t.TituloId
LEFT JOIN dbo.Cliente cli ON cli.ClienteId = co.ClienteId
LEFT JOIN dbo.Entidade ce ON ce.EntidadeId = cli.EntidadeId
LEFT JOIN dbo.Sacado sa ON sa.SacadoId = t.SacadoId
LEFT JOIN dbo.Entidade se ON se.EntidadeId = sa.EntidadeId
WHERE t.Situacao = 1
  AND t.Sigla IN ('DM', 'DS', 'NP')
  AND p.ProdutoDeRisco = 1
  AND t.ValorDoPagamento > t.ValorLiquido
  AND CONVERT(date, t.DataDaSituacao) > CONVERT(date, t.DataDeVencimentoEfetiva)
  AND t.DataDaSituacao >= ?
  -- Recompra-liquidacao FORA (descoberta 2026-06-11): quando a recompra
  -- liquida o titulo (Liquidacao=1), o Bitfin grava ValorDoPagamento =
  -- recomprado + encargos DE RECOMPRA na Titulo com Situacao=1 — o mesmo
  -- encargo ja entra via RecompraItem (regua propria: TaxaDeJuros/Multa da
  -- recompra). Sem este filtro, dupla contagem (527/551 batem centavo a
  -- centavo). Situacao 5 (baixa por recompra pura) nunca entra (Situacao=1).
  AND NOT EXISTS (
      SELECT 1 FROM dbo.RecompraItem i
      JOIN dbo.Recompra r ON r.RecompraId = i.RecompraId
      WHERE i.TituloId = t.TituloId AND r.Efetivada = 1 AND r.Liquidacao = 1
  )
"""

# Lancamentos de receita na conta grafica. `{codes}` e preenchido em runtime
# com placeholders (?) — os codigos vem do catalogo de streams, nunca
# hardcoded aqui. So debitos (Valor < 0 = cobranca ao cliente = receita);
# estornados excluidos (mesma regra da proc DemonstrativoDeResultados).
# UA/cliente via OUTER APPLY TOP 1 — a mesma ContaCorrente pode ter N
# ContaOperacional (uma por produto); sem o TOP 1 o join duplicaria o
# lancamento. ProdutoId fica NULL de proposito (ambiguo nesse grao).
SELECT_RECEITA_GRAFICA_TEMPLATE = """
SELECT
    l.LancamentoId AS lancamento_id,
    CONVERT(date, l.Data) AS data_evento,
    l.Valor AS valor,
    l.Codigo AS codigo,
    l.Descricao AS descricao,
    l.ComplementoInterno AS complemento_interno,
    oa.UnidadeAdministrativaId AS unidade_administrativa_id,
    oa.EntidadeId AS cedente_entidade_id,
    oa.Nome AS cedente_nome,
    oa.Documento AS cedente_documento
FROM dbo.ContaCorrenteLancamento l
OUTER APPLY (
    SELECT TOP 1
        co.UnidadeAdministrativaId,
        ce.EntidadeId,
        ce.Nome,
        ce.Documento
    FROM dbo.ContaOperacional co
    LEFT JOIN dbo.Cliente cli ON cli.ClienteId = co.ClienteId
    LEFT JOIN dbo.Entidade ce ON ce.EntidadeId = cli.EntidadeId
    WHERE co.ContaCorrenteId = l.ContaCorrenteId
    ORDER BY co.ContaOperacionalId
) oa
WHERE l.Codigo IN ({codes})
  AND l.Valor < 0
  AND l.Data >= ?
  AND l.LancamentoId NOT IN (
      SELECT IdentificadorDoLancamento
      FROM dbo.RequerimentoContaOperacionalEstornoLancamento
  )
"""

# Juros/multa/desagio de recompra, POR TITULO (RecompraItem), apenas
# recompras efetivadas (liquidacao financeira via PagamentoOperacional —
# tipicamente netting contra o liquido de operacao nova).
SELECT_RECEITA_RECOMPRA = """
SELECT
    i.RecompraId AS recompra_id,
    i.TituloId AS titulo_id,
    t.Numero AS documento,
    CONVERT(date, r.DataDeEfetivacao) AS data_evento,
    i.ValorDeJuros AS valor_de_juros,
    i.ValorDeMulta AS valor_de_multa,
    i.ValorDeDesagio AS valor_de_desagio,
    r.UnidadeAdministrativaId AS unidade_administrativa_id,
    co.ProdutoId AS produto_id,
    ce.EntidadeId AS cedente_entidade_id,
    ce.Nome AS cedente_nome,
    ce.Documento AS cedente_documento,
    se.Nome AS sacado_nome,
    se.Documento AS sacado_documento
FROM dbo.RecompraItem i
INNER JOIN dbo.Recompra r ON r.RecompraId = i.RecompraId
LEFT JOIN dbo.ContaOperacional co ON co.ContaOperacionalId = r.ContaOperacionalId
LEFT JOIN dbo.Cliente cli ON cli.ClienteId = co.ClienteId
LEFT JOIN dbo.Entidade ce ON ce.EntidadeId = cli.EntidadeId
LEFT JOIN dbo.Titulo t ON t.TituloId = i.TituloId
LEFT JOIN dbo.Sacado sa ON sa.SacadoId = t.SacadoId
LEFT JOIN dbo.Entidade se ON se.EntidadeId = sa.EntidadeId
WHERE r.Efetivada = 1
  AND r.DataDeEfetivacao >= ?
  AND (i.ValorDeJuros > 0 OR i.ValorDeMulta > 0 OR i.ValorDeDesagio > 0)
"""

# Rentabilidade da operacao (desagio + tarifas + ad valorem) — receita RETIDA
# do liquido na efetivacao (caixa por construcao). (OperacaoId, Descricao) e
# unico (validado 2026-06-10). Origem 2/4 (Recompra/Homologacao) excluidas:
# o desagio de recompra ja entra via RecompraItem — incluir aqui duplicaria.
# Cross-check canonico: SUM(Aplicado WHERE Descricao='Deságio') ==
# SUM(OperacaoResultado.TotalDeJuros) das mesmas operacoes.
SELECT_RECEITA_OPERACAO_RENT = """
SELECT
    r.OperacaoId AS operacao_id,
    r.Descricao AS rentabilidade_descricao,
    r.Aplicado AS aplicado,
    CONVERT(date, o.DataDeEfetivacao) AS data_evento,
    o.UnidadeAdministrativaId AS unidade_administrativa_id,
    co.ProdutoId AS produto_id,
    ce.EntidadeId AS cedente_entidade_id,
    ce.Nome AS cedente_nome,
    ce.Documento AS cedente_documento
FROM dbo.OperacaoRentabilidade r
INNER JOIN dbo.Operacao o ON o.OperacaoId = r.OperacaoId
LEFT JOIN dbo.ContaOperacional co ON co.ContaOperacionalId = o.ContaOperacionalId
LEFT JOIN dbo.Cliente cli ON cli.ClienteId = co.ClienteId
LEFT JOIN dbo.Entidade ce ON ce.EntidadeId = cli.EntidadeId
WHERE o.Efetivada = 1
  AND o.Origem NOT IN (2, 4)
  AND r.Aplicado > 0
  AND o.DataDeEfetivacao >= ?
"""
