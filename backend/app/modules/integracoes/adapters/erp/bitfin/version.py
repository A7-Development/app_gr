"""Adapter version constant.

Incrementar ao mudar logica de extracao/mapeamento. Toda linha ingerida
referencia esta versao via `ingested_by_version`.

v2.0.0 (2026-05-12): silver `wh_dre_mensal` deixa de fetchar
`ANALYTICS.dbo.vw_DRE` e passa a montar DRE a partir do bronze de 3 fontes
em UNLTD_<X> (DemonstrativoDeResultado + PagamentoOpcaoDePagamento +
ComissaoComercialFechamento) aplicando classificacao nossa de
`wh_dre_classification_rule`. Adapter nao depende mais de ANALYTICS no
caminho critico do DRE -- viabiliza multi-tenant.
"""

ADAPTER_VERSION = "bitfin_adapter_v2.0.0"
