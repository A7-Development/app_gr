"""Mappers QiTech — payloads brutos -> dicts canonicos prontos pra upsert.

Cada funcao aqui e pura: recebe o payload JSON de um endpoint especifico da
QiTech + contexto (tenant_id), devolve lista de dicts no formato que o ETL
passa direto pra `pg_insert(Table).values(...).on_conflict_do_update(...)`.

NAO grava no banco. NAO faz side-effect. Isso facilita:
- Teste com fixture JSON do disco (samples reais em qitech_samples/).
- Debug: dump de dict intermediario sem precisar subir Postgres.
- Reprocessamento offline de dados antigos.

Padrao igual aos `_map_*` do adapter Bitfin (ver etl.py do bitfin).
"""

from app.modules.integracoes.adapters.admin.qitech.mappers.conta_corrente import (
    map_conta_corrente,
)
from app.modules.integracoes.adapters.admin.qitech.mappers.cpr import map_cpr
from app.modules.integracoes.adapters.admin.qitech.mappers.demonstrativo_caixa import (
    map_demonstrativo_caixa,
)
from app.modules.integracoes.adapters.admin.qitech.mappers.mec import map_mec
from app.modules.integracoes.adapters.admin.qitech.mappers.outros_ativos import (
    map_outros_ativos,
)
from app.modules.integracoes.adapters.admin.qitech.mappers.outros_fundos import (
    map_outros_fundos,
)
from app.modules.integracoes.adapters.admin.qitech.mappers.rentabilidade import (
    map_rentabilidade,
)
from app.modules.integracoes.adapters.admin.qitech.mappers.rf import map_rf
from app.modules.integracoes.adapters.admin.qitech.mappers.rf_compromissadas import (
    map_rf_compromissadas,
)
from app.modules.integracoes.adapters.admin.qitech.mappers.tesouraria import (
    map_tesouraria,
)

__all__ = [
    "map_conta_corrente",
    "map_cpr",
    "map_demonstrativo_caixa",
    "map_mec",
    "map_outros_ativos",
    "map_outros_fundos",
    "map_rentabilidade",
    "map_rf",
    "map_rf_compromissadas",
    "map_tesouraria",
]
