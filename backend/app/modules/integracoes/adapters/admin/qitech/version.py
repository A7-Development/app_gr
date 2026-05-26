"""Adapter version — gravado em decision_log + proveniencia de cada linha.

Incrementar seguindo semver:
    MAJOR — muda contrato de output (quebra consumidores)
    MINOR — adiciona endpoint / campo opcional
    PATCH — correcao sem mudanca de contrato
"""

from __future__ import annotations

ADAPTER_VERSION = "qitech_adapter_v0.5.0"  # 2026-05-26: bank_account.statement mapper corrigido contra payload real (tipoLancamento C/D/S; descarta saldos S; historico.{codigo,descricao}; doc via inscricao; id estavel `lancamento`). Antes: tipo sempre 'C', descricao nula, dict cru em historico.
