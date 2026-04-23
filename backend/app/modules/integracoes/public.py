"""Public contract of Integracoes module.

Outros modulos podem importar APENAS o que esta exposto aqui. Internals
(`models/`, `services/`, `adapters/`) sao proibidos de serem acessados de fora.

Consumidores atuais:
- `app/scheduler/jobs/bitfin_sync.py` usa `run_sync_cycle` para disparar ciclos.
- `app/modules/integracoes/routers/sources.py` usa `run_sync_one` / `run_ping`
  para sync manual e teste de conexao.
- Outros modulos podem usar `is_source_enabled` para checar se uma fonte esta
  habilitada para um tenant (ex.: empty state no BI).
"""

from app.modules.integracoes.services.eligibility import is_source_enabled
from app.modules.integracoes.services.sync_runner import (
    run_ping,
    run_sync_cycle,
    run_sync_one,
)

__all__ = [
    "is_source_enabled",
    "run_ping",
    "run_sync_cycle",
    "run_sync_one",
]
