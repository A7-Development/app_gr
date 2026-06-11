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
"""

ADAPTER_VERSION = "bitfin_adapter_v2.7.0"
