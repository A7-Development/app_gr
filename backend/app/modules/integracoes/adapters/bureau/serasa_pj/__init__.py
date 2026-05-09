"""Serasa Experian — Business Information Report (CNPJ).

Endpoint: `/credit-services/business-information-report/v1/reports`
Documentacao: https://developer.serasaexperian.com.br/api/relatorio-avancado-pj

Caracteristicas do contrato A7 Credit (distribuidor):
    - Header `X-Retailer-Document-Id` (CNPJ do consultante real) e
      OBRIGATORIO em toda chamada — se omitido, consumo conta para a A7
      em vez do tenant.
    - Score model forcado: `H4PJ`.
    - Features SPC bloqueadas — nao tentar usar em `optionalFeatures`.
    - Reciprocidade silenciosa: pedido `_ANALITICO` pode ser downgrado
      para sintetico se a reciprocidade A7 quebrar — silver guarda
      `requested_report` separado de `actual_report_returned`.

Modelo: 1 credencial por tenant. O cache de token e chaveado por
(tenant_id, environment) — sem multi-UA, ao contrario do QiTech.

Arquitetura:
    version.py    — ADAPTER_VERSION registrado em proveniencia.
    config.py     — SerasaPjConfig: base_url + credenciais + retailer_document_id.
    endpoints.py  — catalogo de paths.
    errors.py     — hierarquia de excecoes tipadas.
    auth.py       — fetch + cache de access token (OAuth2 Client Credentials).
    connection.py — httpx.AsyncClient com Bearer + X-Retailer-Document-Id.
    client.py     — query_pj_analitico(cnpj): retorna payload bruto.
    mappers/      — raw -> silver (criados quando a tabela canonical existir).
"""
