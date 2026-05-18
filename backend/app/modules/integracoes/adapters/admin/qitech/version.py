"""Adapter version — gravado em decision_log + proveniencia de cada linha.

Incrementar seguindo semver:
    MAJOR — muda contrato de output (quebra consumidores)
    MINOR — adiciona endpoint / campo opcional
    PATCH — correcao sem mudanca de contrato
"""

from __future__ import annotations

ADAPTER_VERSION = "qitech_adapter_v0.2.1"  # 2026-05-18: fix escala centavos em aquisicao_consolidada
