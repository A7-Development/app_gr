"""Central metadata imports — imported by Alembic env.py to discover all models.

All SQLAlchemy models must be imported here (directly or transitively) so Alembic
can auto-detect them during migration generation.
"""

# Core base
from app.core.database import Base

# Shared kernel
from app.shared.audit_log.decision_log import DecisionLog  # noqa: F401
from app.shared.audit_log.premise_set import PremiseSet  # noqa: F401
from app.shared.catalog.source_catalog import SourceCatalog  # noqa: F401
from app.shared.catalog.tenant_source_config import TenantSourceConfig  # noqa: F401
from app.shared.identity.subscription import TenantModuleSubscription  # noqa: F401
from app.shared.identity.tenant import Tenant  # noqa: F401
from app.shared.identity.user import User  # noqa: F401
from app.shared.identity.user_permission import UserModulePermission  # noqa: F401

# Warehouse (populado pelo ETL no Sprint 3)
from app.warehouse.dim import DimDreClassificacao, DimMes  # noqa: F401
from app.warehouse.dre import DreMensal  # noqa: F401
from app.warehouse.operacao import Operacao, OperacaoItem  # noqa: F401
from app.warehouse.titulo import Titulo  # noqa: F401
from app.warehouse.titulo_snapshot import TituloSnapshot  # noqa: F401

# Warehouse models (populated from Sprint 2/3) — to be added later
# from app.warehouse.bitfin_operacoes import ...

target_metadata = Base.metadata
