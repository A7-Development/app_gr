"""Provedores de dados externos — capability transversal vendida pela A7.

Categoria paralela a `app/shared/ai/`: dados externos (BigDataCorp, Infosimples)
sao providos pela A7 via UMA conta global (credencial cifrada, sem tenant_id) e
revendidos aos tenants. Adapter HTTP per provider vive em
`app/modules/integracoes/adapters/data/<vendor>/` (regra CLAUDE.md §13).

Modelo paralelo a `app/shared/ai/`:
    - provedor_dados                       (entidade global)
    - provedor_dados_credencial            (envelope-cifrada, global)
    - provedor_dados_dataset               (catalogo dinamico por provider)
    - provedor_dados_dataset_preco_historico (append-only, mudancas detectadas)
    - provedor_dados_sync_run              (log de cada catalog sync)

Subscription per tenant + metering chegam na Fase 3 deste plano (ainda nao
existem nesta camada — Fase 1 e so infra de catalogo).
"""
