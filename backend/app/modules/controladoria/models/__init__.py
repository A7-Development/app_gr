"""Modelos SQLAlchemy do modulo controladoria."""

from app.modules.controladoria.models.cosif import (
    CosifCatalog,
    CosifRule,
    TenantPapelClassificacao,
)

__all__ = [
    "CosifCatalog",
    "CosifRule",
    "TenantPapelClassificacao",
]
