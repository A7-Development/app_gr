"""Warehouse canonico do GR.

Espelho normalizado das views/tabelas do ANALYTICS + Bitfin com metadata de
proveniencia (mixin Auditable). Populado pelo ETL em `app/scheduler/jobs/`.

Convencoes:
- Prefixo `wh_` em todas as tabelas.
- `tenant_id` NOT NULL em toda tabela de fato.
- Campos em snake_case (source PascalCase do Bitfin preservado em `source_id`).
- Valores monetarios em `Numeric(18, 4)` (suficiente para FIDCs).
- Datetimes sempre com timezone.
"""

from app.warehouse.dim import DimDreClassificacao, DimMes
from app.warehouse.dre import DreMensal
from app.warehouse.operacao import Operacao, OperacaoItem
from app.warehouse.titulo import Titulo
from app.warehouse.titulo_snapshot import TituloSnapshot

__all__ = [
    "DimDreClassificacao",
    "DimMes",
    "DreMensal",
    "Operacao",
    "OperacaoItem",
    "Titulo",
    "TituloSnapshot",
]
