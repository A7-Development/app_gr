"""Schemas Pydantic do modulo cadastros."""

from app.modules.cadastros.schemas.unidade_administrativa import (
    UnidadeAdministrativaCreate,
    UnidadeAdministrativaOut,
    UnidadeAdministrativaUpdate,
)

__all__ = [
    "UnidadeAdministrativaCreate",
    "UnidadeAdministrativaOut",
    "UnidadeAdministrativaUpdate",
]
