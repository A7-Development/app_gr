"""Adapter BigDataCorp — sync de catalogo + consultas on-demand.

Vendor de dados externos (PJ/PF/processos/veiculos) com contrato global A7.
Endpoints sao POST por categoria (`/empresas`, `/pessoas`, `/precos/`, ...)
com body `{ "Datasets": "<code>", "q": "doc{<docnum>}", "Limit": N }`.

API de Precos (`POST /precos/`) e gratuita e devolve a tabela completa de
datasets habilitados pra conta — usada pelo `pricing_sync` pra popular o
catalogo sem seed manual.

Auth: dois headers fixos (`AccessToken`, `TokenId`) — sem token TTL ou
refresh flow. Credencial cifrada vive em `provedor_dados_credencial`.

Fase 1 (este adapter, 2026-05-05):
    - client.query_pricing()           — chama /precos/ e devolve catalogo
    - pricing_sync.sync_catalog()      — diffs e grava em provedor_dados_dataset
    - etl.sync_catalog_for_provider()  — entry point com log em sync_run

Consumo de domain (Fase 3, futuro): client.query_dataset(category, dataset, q).
"""

from app.modules.integracoes.adapters.data.bigdatacorp.version import (
    ADAPTER_VERSION,
)

__all__ = ["ADAPTER_VERSION"]
