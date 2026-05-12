"""Modulo Controladoria: contabilidade, DRE, balancete, DFC. Reaproveita servicos do app_controladoria."""

# Registry SQLAlchemy: garante que models cosif estao registrados no
# Base.metadata antes de qualquer query (necessario para autoflush e
# relationships funcionarem com FKs cross-table).
from app.modules.controladoria.models import (  # noqa: F401
    CosifCatalog,
    CosifRule,
    TenantPapelClassificacao,
)
