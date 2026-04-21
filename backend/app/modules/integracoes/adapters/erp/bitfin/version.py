"""Adapter version constant.

Incrementar ao mudar logica de extracao/mapeamento. Toda linha ingerida
referencia esta versao via `ingested_by_version`.
"""

ADAPTER_VERSION = "bitfin_adapter_v1.0.0"

# Databases MSSQL alvo (ambos na mesma instancia configurada em `.env`)
DB_BITFIN = "UNLTD_A7CREDIT"
DB_ANALYTICS = "ANALYTICS"
