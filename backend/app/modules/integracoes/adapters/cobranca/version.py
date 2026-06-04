"""Adapter version constant (cobranca / CNAB).

Incrementar ao mudar logica de captura/landing/parsing/mapeamento. Toda linha
de bronze referencia esta versao via `fetched_by_version`; o silver
`wh_boleto` via `ingested_by_version`.

v0.1.0 (2026-06-04): fundacao -- FileSource (local_path + upload) + landing
do arquivo CNAB cru no bronze (wh_cnab_raw_arquivo). Parsers por banco e
mapper para wh_boleto ainda nao implementados.
"""

ADAPTER_VERSION = "cobranca_adapter_v0.1.0"
