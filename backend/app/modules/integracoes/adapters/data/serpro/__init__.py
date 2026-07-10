"""Adapter SERPRO -- API Consulta NF-e (gateway.apiserpro.serpro.gov.br).

Estado vivo da NF-e por chave de acesso: cStat atual (cancelamento pos-
autorizacao), manifestacao do destinatario e lista completa de eventos
(procEventosNFe). Complementa a landing fiscal (DOCUMENT_NFE), que carrega
o retrato do XML no momento da autorizacao.

Credencial em `tenant_source_config` (source_type=DATA_SERPRO_NFE),
compartilhada com o contrato que o Bitfin ja consome (decisao 2026-07-10:
consumo somado, rateio fino via header x-request-tag).
"""
