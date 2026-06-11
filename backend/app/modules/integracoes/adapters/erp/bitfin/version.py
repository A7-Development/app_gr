"""Adapter version constant.

Incrementar ao mudar logica de extracao/mapeamento. Toda linha ingerida
referencia esta versao via `ingested_by_version`.

v2.0.0 (2026-05-12): silver `wh_dre_mensal` deixa de fetchar
`ANALYTICS.dbo.vw_DRE` e passa a montar DRE a partir do bronze de 3 fontes
em UNLTD_<X> (DemonstrativoDeResultado + PagamentoOpcaoDePagamento +
ComissaoComercialFechamento) aplicando classificacao nossa de
`wh_dre_classification_rule`. Adapter nao depende mais de ANALYTICS no
caminho critico do DRE -- viabiliza multi-tenant.

v2.1.0 (2026-05-22): SELECT_OPERACAO passa a resolver o cedente via
`Operacao.ContaOperacionalId -> ContaOperacional.ClienteId ->
Cliente.EntidadeId -> Entidade` e popula `wh_operacao.cedente_id`,
`cedente_nome`, `cedente_documento` (campo novo). Anterior usava lookup
via `wh_titulo_snapshot.snapshot_id == wh_operacao_item.titulo_id` que
juntava 2 espacos numericos diferentes e trazia cedentes errados (bug
visivel no drill 'Operacoes do dia' do /bi/operacoes4). Modelo e 1:1
(uma op tem um cedente, via conta operacional).

v2.2.0 (2026-05-31): ingestao do catalogo de tarifas
(`OrganizacaoTarifa` -> wh_bitfin_tarifa_catalogo) + classificacao da
RECEITA do DRE por NATUREZA (Desagio/Tarifa/Multa/Juros/Ad Valorem/Imposto)
ancorada no `Tipo` nativo do catalogo via `wh_bitfin_dre_natureza_rule`.
Silver `wh_dre_mensal` ganha colunas `natureza` + `fonte_integracao`.

v2.3.0 (2026-06-10): party model — endpoint `bitfin.entidades` ingere
Entidade completa (~20k, com CNAE/endereco/RJ/porte), papeis Cliente->
cedente e Sacado->sacado, e GrupoEconomico(Membro) para o warehouse
canonico wh_entidade / wh_entidade_fonte (crosswalk de identidade) /
wh_entidade_papel / wh_grupo_economico(_membro). Identidade: 1 entidade
por (tenant, documento normalizado); documento invalido = quarentena.

v2.4.0 (2026-06-10): F1 do party model -- o endpoint `bitfin.entidades`
passa a ingerir tambem as posicoes por papel: ClientePosicao ->
wh_posicao_cedente (risco/prazo carteira/liquidez), ClientePosicaoProduto ->
wh_posicao_cedente_produto (LIMITE operacional/tranche/risco por produto),
SacadoPosicao -> wh_posicao_sacado (subset essencial). Snapshot
vendor-computed, full refresh, ancorado em wh_entidade via crosswalk.

v2.5.0 (2026-06-10): REMOVIDA a classificacao por natureza do DRE
(`wh_bitfin_dre_natureza_rule` dropada + coluna `wh_dre_mensal.natureza`).
Motivo: a DemonstrativoDeResultado do Bitfin RECALCULA multa/juros
teoricamente (percentual contratual x dias) — nao reflete caixa. Receita
por natureza renasce fiel ao caixa no catalogo de receitas operacionais
(nova wh canonica, fontes: Titulo / ContaCorrenteLancamento / Recompra /
OperacaoRentabilidade). `wh_bitfin_tarifa_catalogo` permanece como
vocabulario controlado.

v2.6.0 (2026-06-10): ETL do catalogo de receitas (PR 2 — familias de mora):
3 syncs novos materializam wh_receita_operacional dirigidos por
wh_bitfin_receita_stream: mora_liquidacao (Titulo, caixa = pgto - liquido,
split juros x multa proporcional aos teoricos do ProcedimentoDeCobranca),
grafica (ContaCorrenteLancamento — prorrogacao/cartorio/acerto/tarifas/
repasses/financeira, codigos do catalogo, estornados excluidos, TituloId
extraido do ComplementoInterno), recompra (RecompraItem Efetivada=1,
juros/multa/desagio por titulo).

v2.7.0 (2026-06-10): PR 3 do catalogo de receitas — sync_receita_operacao:
OperacaoRentabilidade (efetivadas, Origem != recompra/homologacao) ->
streams desagio_operacao / tarifa_operacao / ad_valorem. Receita retida do
liquido na efetivacao (caixa por construcao). Cross-check: desagio do mes
== Σ OperacaoResultado.TotalDeJuros das efetivadas.

v2.7.1 (2026-06-11): FIX dupla contagem na mora de liquidacao — exclui
titulos liquidados POR RECOMPRA (Situacao=1 com RecompraItem Efetivada+
Liquidacao): o encargo deles e da regua de recompra e ja entra via stream
recompra. Descoberta da auditoria por Situacao: 1=liquidacao real (FAT/DMS,
regua ProcedimentoDeCobranca adere 98,5%), 5=baixa por recompra (100%),
3=cobranca simples CBS (mora do cliente, fora). A "mora da Comissaria" era
100% recompra. Gabarito novo: abr 31.381,79 / mai 31.329,59.

v2.8.0 (2026-06-11): split da mora de liquidacao deixa de ser proporcional
(rejeitado pelo Ricardo) — 3 saidas pela regua: |caixa - regua| <= R$1 ->
componentes EXATOS da regua (residuo no juros); fora -> ENCARGO_NEGOCIADO
sem decomposicao + valor_referencia_regua (desconto concedido = referencia
- valor). Recompra ganha referencia da regua contratual sobre dias
vencidos; mora perdoada (lancado 0, regua > 0) entra com valor 0 pra
metrica de desconto. Coluna nova wh_receita_operacional.
valor_referencia_regua (migration d9e3a7c1f5b2).

v2.9.0 (2026-06-11): SELECT_OPERACAO ingere as 3 tarifas que faltavam do
OperacaoResultado -- TarifaPorOperacao (TAC), TarifaDeTed e
TotalDosRegistrosDeRecebiveis. Sem elas a soma das tarifas do wh_operacao
nao reconciliava com o desagio total embutido no ValorPresente dos itens
(= valor_compra enviado a QiTech): gap de R$ 159,00 na op 9881 (TAC 120 +
TED 30 + reg. recebiveis 9). Base da visao de receita por acruo.

v2.10.0 (2026-06-11): METODO ACRUO — engine acruo.py deriva
wh_receita_acruo_dia (cota diaria da curva composta de desagio por titulo,
D+1 DU, ancora PV=ValorPresente, componentes desagio/adval/tarifas na
proporcao do desagio total, IOF fora). Saida antecipada = residual no dia
(acruo_antecipacao). Curva PARA no vencimento ORIGINAL (prorrogacao nao
estende — validado QiTech). 2 de 3 metodos (caixa | acruo | competencia).

v2.5.0 (2026-06-11): sinais de praca de pagamento (risco de autoliquidacao/
lastro frio). wh_posicao_sacado ganha 4 totais de praca (fora da praca do
sacado / praca do cliente / agencia do cliente / banco digital); novas
wh_posicao_sacado_cedente (SacadoPosicaoCliente — relacao NxN com praca,
risco e recompras) e wh_pagamento_praca_mensal (PosicaoHistoricaPagamentoPraca
— serie mensal 5 buckets desde 2022-01, por conta operacional/cedente).

v2.11.0 (2026-06-12): METODO CAIXA — engine caixa.py deriva
wh_receita_caixa: desagio + tarifas do titulo apropriados na SAIDA
(liquidacao/baixa/recompra pelo VN cheio/reoperacao). CORRECAO DE
ROTULAGEM (Ricardo): o bloco 'operacao' do wh_receita_operacional
(integral na efetivacao) e a COMPETENCIA, nao o caixa. 3 metodos
completos: CAIXA (saida) | COMPETENCIA (efetivacao) | ACRUO (curva).

v2.12.0 (2026-06-12): MORTE DA CADEIA DRE — pagina /controladoria/dre,
API, services, classifier e tabelas (wh_dre_mensal, wh_bitfin_raw_dre,
wh_dre_classification_rule, wh_dim_dre_classificacao) eliminados. Syncs
DRE removidos do pipeline. A apuracao de receita vive no catalogo
caixa-fiel (3 metodos); DRE sera reconstruida do zero sobre ele.
"""

ADAPTER_VERSION = "bitfin_adapter_v2.12.0"
