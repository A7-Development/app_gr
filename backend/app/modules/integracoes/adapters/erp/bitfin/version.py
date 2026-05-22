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
"""

ADAPTER_VERSION = "bitfin_adapter_v2.1.0"
