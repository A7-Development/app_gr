"""Adapter version — gravado em decision_log + proveniencia de cada linha.

Incrementar seguindo semver:
    MAJOR — muda contrato de output (quebra consumidores)
    MINOR — adiciona endpoint / campo opcional
    PATCH — correcao sem mudanca de contrato
"""

from __future__ import annotations

ADAPTER_VERSION = "qitech_adapter_v0.4.0"  # 2026-05-19: business key explicita em 16 silvers (source_id vira proveniencia pura). Conserto do bug v0.3.0 que duplicou wh_cpr_movimento REALINVEST 14/05.
