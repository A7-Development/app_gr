"""Public contract of Integracoes module.

Outros modulos podem importar APENAS o que esta exposto aqui. Internals
(`models/`, `services/`, `adapters/`) sao proibidos de serem acessados de fora.

Consumidores atuais:
- `app/scheduler/sync_dispatcher.py` usa `list_due_configs`, `run_sync_one`
  e `rule_name_for` para disparar ciclos com base em `tenant_source_config`.
- `app/modules/integracoes/routers/sources.py` usa `run_sync_one` / `run_ping`
  para sync manual e teste de conexao.
- Outros modulos podem usar `is_source_enabled` para checar se uma fonte esta
  habilitada para um tenant (ex.: empty state no BI).
"""

from app.modules.integracoes.services.eligibility import (
    is_source_enabled,
    list_enabled_configs,
)
from app.modules.integracoes.services.serasa_pj_query import (
    execute_pj_query as execute_serasa_pj_query,
)
from app.modules.integracoes.services.sync_runner import (
    rule_name_for,
    run_ping,
    run_sync_cycle,
    run_sync_one,
)

__all__ = [
    "execute_serasa_pj_query",
    "is_source_enabled",
    "list_enabled_configs",
    "rule_name_for",
    "run_ping",
    "run_sync_cycle",
    "run_sync_one",
]
