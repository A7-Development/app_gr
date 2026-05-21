"""Endpoint routing — decide qual caminho processa cada endpoint.

A partir de 2026-05-21 (F3 do refactor de sync, ver
`project_qitech_sync_state_machine` memory), endpoints podem estar em 1 de 2
regimes:

- **Legado** (`state_machine_enabled=False`): processado pelos jobs
  `sync_dispatcher` + `reconciler` + `watermark_scanner` +
  `recent_complete_refresher`. 1 disparo no horario do `daily_at` + auto-heal
  por coverage gap.
- **State machine** (`state_machine_enabled=True`): processado pelo
  `state_machine_dispatcher` (tick 1min) + `state_machine_seeder` (nightly).
  Adaptive polling com transicoes ESPERADO/ATRASADO/SUSPEITO/FURO.

Este modulo provem o gate canonico que **todo job legado** consulta antes de
agir sobre um endpoint. Sem isso, ligar a flag causaria double-fetch (state
machine E legado disparando em paralelo).

Helper unico, leitura de catalogo in-memory (custo proximo de zero).
"""

from __future__ import annotations

from app.core.enums import SourceType


def is_state_machine_enabled(
    source_type: SourceType,
    endpoint_name: str,
) -> bool:
    """True se o endpoint esta sob o regime da state machine.

    Quando True, jobs legados (sync_dispatcher modo endpoint, reconciler,
    watermark_scanner, recent_complete_refresher) devem **pular** este
    endpoint — o `state_machine_dispatcher` cuida.

    Quando False (ou endpoint nao encontrado no catalogo), endpoint segue
    o caminho legado.
    """
    # Import lazy: `endpoint_routing` e consumido por `endpoint_scheduling`
    # que esta na cadeia de import de `public.py` — import top-level criaria
    # ciclo `public -> endpoint_scheduling -> endpoint_routing -> public`.
    from app.modules.integracoes.public import endpoint_catalog

    specs = endpoint_catalog(source_type)
    for spec in specs:
        if spec.name == endpoint_name:
            return spec.state_machine_enabled
    return False


__all__ = ["is_state_machine_enabled"]
