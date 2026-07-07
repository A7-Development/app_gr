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
    r.TarifaPorOperacao AS tarifa_por_operacao,
    r.TarifaDeTed AS tarifa_de_ted,
    r.TotalDosRegistrosDeRecebiveis AS total_dos_registros_de_recebiveis,
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
    sp.PagamentosForaDaPracaDoSacadoTotal AS pagamentos_fora_praca_sacado,
    sp.PagamentosNaPracaDoClienteTotal AS pagamentos_praca_cliente,
    sp.PagamentosNaAgenciaDoClienteTotal AS pagamentos_agencia_cliente,
    sp.PagamentosEmBancoDigitalTotal AS pagamentos_banco_digital,
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
    i.ValorBase AS valor_base,
    i.QuantidadeDeDiasVencido AS dias_vencido,
    pc.PercentualDeMultaPorAtraso AS pct_multa,
    pc.PercentualDeJurosDeMora AS pct_juros,
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
LEFT JOIN dbo.ProcedimentoDeCobranca pc ON pc.TituloId = i.TituloId
LEFT JOIN dbo.Sacado sa ON sa.SacadoId = t.SacadoId
LEFT JOIN dbo.Entidade se ON se.EntidadeId = sa.EntidadeId
WHERE r.Efetivada = 1
  AND r.DataDeEfetivacao >= ?
  -- DiasVencido > 0 sem encargo lancado = mora PERDOADA na negociacao:
  -- entra com valor 0 + referencia da regua (metrica desconto concedido).
  AND (i.ValorDeJuros > 0 OR i.ValorDeMulta > 0 OR i.ValorDeDesagio > 0
       OR i.QuantidadeDeDiasVencido > 0)
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


# Relacao sacado x cedente (SacadoPosicaoCliente) — onde mora o sinal de
# fraude de praca (divergencia concentrada num unico cedente).
SELECT_POSICAO_SACADO_CEDENTE = """
SELECT
    spc.PosicaoId AS posicao_id,
    spc.ContaOperacionalId AS conta_operacional_source_id,
    s.SacadoId AS papel_source_id,
    s.EntidadeId AS entidade_source_id,
    cli.ClienteId AS cedente_papel_source_id,
    cli.EntidadeId AS cedente_entidade_source_id,
    spc.RiscoTotalQuantidade AS risco_total_qtd,
    spc.RiscoTotalTotal AS risco_total_valor,
    spc.RiscoVencidoQuantidade AS risco_vencido_qtd,
    spc.RiscoVencidoTotal AS risco_vencido_valor,
    spc.RiscoAVencerQuantidade AS risco_avencer_qtd,
    spc.RiscoAVencerTotal AS risco_avencer_valor,
    spc.TicketMedio AS ticket_medio,
    spc.IndiceDeLiquidez AS indice_liquidez,
    spc.HistoricoDeRecomprasQuantidade AS hist_recompras_qtd,
    spc.HistoricoDeRecomprasTotal AS hist_recompras_valor,
    spc.PagamentosForaDaPracaDoSacadoTotal AS pagamentos_fora_praca_sacado,
    spc.PagamentosNaPracaDoClienteTotal AS pagamentos_praca_cliente,
    spc.PagamentosNaAgenciaDoClienteTotal AS pagamentos_agencia_cliente,
    spc.PagamentosEmBancoDigitalTotal AS pagamentos_banco_digital
FROM dbo.SacadoPosicaoCliente spc
INNER JOIN dbo.Sacado s
    ON s.PosicaoId = spc.PosicaoId
LEFT JOIN dbo.ContaOperacional co
    ON co.ContaOperacionalId = spc.ContaOperacionalId
LEFT JOIN dbo.Cliente cli
    ON cli.ClienteId = co.ClienteId
"""

# Serie mensal de pagamentos por praca, por conta operacional (cedente).
# 5 buckets somam o total pago do mes. Historico desde 2022-01.
SELECT_PAGAMENTO_PRACA_MENSAL = """
SELECT
    php.ContaOperacionalId AS conta_operacional_source_id,
    php.Ano AS ano,
    php.Mes AS mes,
    cli.ClienteId AS cedente_papel_source_id,
    cli.EntidadeId AS cedente_entidade_source_id,
    php.PagoNaPracaDoSacado AS pago_na_praca_sacado,
    php.PagoForaDaPracaDoSacado AS pago_fora_praca_sacado,
    php.PagoNaPracaDoCliente AS pago_na_praca_cliente,
    php.PagoNaAgenciaDoCliente AS pago_na_agencia_cliente,
    php.PagoEmBancoDigital AS pago_em_banco_digital
FROM dbo.PosicaoHistoricaPagamentoPraca php
LEFT JOIN dbo.ContaOperacional co
    ON co.ContaOperacionalId = php.ContaOperacionalId
LEFT JOIN dbo.Cliente cli
    ON cli.ClienteId = co.ClienteId
"""


# ---------------------------------------------------------------------------
# Liquidacao declarada (F3 antifraude) — endpoint `bitfin.liquidacoes`.
# Desfecho DECLARADO por titulo: evento bancario (36/37), recompra (2
# caminhos), baixa manual classificada por evidencia, baixa administrativa
# e perda. Ver app/warehouse/liquidacao.py.
# ---------------------------------------------------------------------------

# Evento bancario: unicos codigos que carregam ValorPago (36 Liquidacao
# Normal, 37 Liquidacao em Cartorio). Max 1 por titulo (validado no recon).
SELECT_LIQUIDACAO_BANCARIA = """
SELECT
    t.TituloId AS titulo_id,
    t.OperacaoId AS operacao_id,
    t.UnidadeAdministrativaId AS unidade_administrativa_id,
    t.Situacao AS situacao_titulo,
    t.Valor AS valor_titulo,
    o.Codigo AS meio_codigo,
    o.Data AS data_evento,
    o.DataDeCredito AS data_credito,
    o.ValorPago AS valor_pago,
    o.TotalDeJuros AS juros,
    o.AgenciaId AS agencia_id,
    o.LocalDoPagamento AS local_pagamento,
    o.PagoForaDaPracaDoSacado AS pago_fora_praca_sacado,
    o.PagoNaPracaDoCliente AS pago_na_praca_cliente,
    o.PagoNaAgenciaDoCliente AS pago_na_agencia_cliente,
    o.PagoNaAgenciaDoSacado AS pago_na_agencia_sacado,
    o.PagoEmBancoDigital AS pago_em_banco_digital,
    p.Registrado AS registrado,
    p.CarteiraBancariaId AS carteira_bancaria_id
FROM dbo.CobrancaAcoesOcorrencia o
JOIN dbo.ProcedimentoDeCobranca p
    ON p.ProcedimentoDeCobrancaId = o.ProcedimentoDeCobrancaId
JOIN dbo.Titulo t
    ON t.TituloId = p.TituloId
WHERE o.Codigo IN ('36', '37')
"""

# Titulo liquidado no ERP (Situacao 1/2) SEM evento bancario de liquidacao —
# baixa manual, classificada por evidencia no mapper:
#   teve_baixa_confirmada=1 + registrado=1 -> baixa_confirmada (FORTE)
#   sem procedimento OU registrado=0      -> sem_registro (deposito plausivel)
#   registrado=1 sem ocorrencia            -> sem_ocorrencia (fraco)
SELECT_LIQUIDACAO_SEM_TRILHO = """
SELECT
    t.TituloId AS titulo_id,
    t.OperacaoId AS operacao_id,
    t.UnidadeAdministrativaId AS unidade_administrativa_id,
    t.Situacao AS situacao_titulo,
    t.Valor AS valor_titulo,
    t.ValorDoPagamento AS valor_pago,
    t.DataDaSituacao AS data_evento,
    p.Registrado AS registrado,
    p.CarteiraBancariaId AS carteira_bancaria_id,
    CASE WHEN EXISTS (
        SELECT 1 FROM dbo.CobrancaAcoesOcorrencia bx
        WHERE bx.ProcedimentoDeCobrancaId = p.ProcedimentoDeCobrancaId
          AND bx.Codigo = '05'
    ) THEN 1 ELSE 0 END AS teve_baixa_confirmada
FROM dbo.Titulo t
LEFT JOIN dbo.ProcedimentoDeCobranca p
    ON p.TituloId = t.TituloId
WHERE t.Situacao IN (1, 2)
  AND NOT EXISTS (
      SELECT 1
      FROM dbo.ProcedimentoDeCobranca p2
      JOIN dbo.CobrancaAcoesOcorrencia o
          ON o.ProcedimentoDeCobrancaId = p2.ProcedimentoDeCobrancaId
         AND o.Codigo IN ('36', '37')
      WHERE p2.TituloId = t.TituloId
  )
"""

# Recompra efetivada — caminho 1 (RecompraItem). Titulo pode aparecer em
# multiplas recompras (94 casos no recon) -> business key inclui RecompraId.
SELECT_LIQUIDACAO_RECOMPRA = """
SELECT
    ri.RecompraId AS recompra_id,
    ri.TituloId AS titulo_id,
    t.OperacaoId AS operacao_id,
    t.UnidadeAdministrativaId AS unidade_administrativa_id,
    t.Situacao AS situacao_titulo,
    t.Valor AS valor_titulo,
    r.DataDeEfetivacao AS data_evento,
    ri.ValorRecomprado AS valor_pago,
    ri.ValorDeJuros AS juros
FROM dbo.RecompraItem ri
JOIN dbo.Recompra r
    ON r.RecompraId = ri.RecompraId
   AND r.Efetivada = 1
JOIN dbo.Titulo t
    ON t.TituloId = ri.TituloId
"""

# Recompra efetivada — caminho 2 (transferencia de operacao). E o caminho
# que a view de elegibilidade do Bitfin perde (638 titulos no recon).
SELECT_LIQUIDACAO_TRANSFERENCIA = """
SELECT
    tt.TituloId AS titulo_id,
    tt.OperacaoIdDeOrigem AS operacao_id,
    tt.OperacaoIdDeDestino AS operacao_destino_id,
    tt.DataDeEfetivacao AS data_evento,
    t.UnidadeAdministrativaId AS unidade_administrativa_id,
    t.Situacao AS situacao_titulo,
    t.Valor AS valor_titulo
FROM dbo.TituloTransferencia tt
JOIN dbo.Titulo t
    ON t.TituloId = tt.TituloId
WHERE tt.Efetivada = 1
  AND tt.Motivo = 'Recompra'
"""

# Saidas sem dinheiro: Situacao 3 (Baixado) sem transferencia-recompra =
# baixa administrativa ("titulo saiu da carteira sem dinheiro entrar");
# Situacao 9 = perda (write-off contabil).
SELECT_LIQUIDACAO_BAIXA_ADMIN = """
SELECT
    t.TituloId AS titulo_id,
    t.OperacaoId AS operacao_id,
    t.UnidadeAdministrativaId AS unidade_administrativa_id,
    t.Situacao AS situacao_titulo,
    t.Valor AS valor_titulo,
    t.ValorDoPagamento AS valor_pago,
    t.DataDaSituacao AS data_evento
FROM dbo.Titulo t
WHERE (
        t.Situacao = 3
        AND NOT EXISTS (
            SELECT 1 FROM dbo.TituloTransferencia tt
            WHERE tt.TituloId = t.TituloId AND tt.Efetivada = 1
        )
      )
   OR t.Situacao = 9
"""
