"""Aggregate router of the Risco module (mounted under /api/v1/risco)."""

from fastapi import APIRouter

from app.modules.risco.api.contratos_liquidacao import router as contratos_liquidacao_router
from app.modules.risco.api.curadoria_liquidacoes import router as curadoria_liquidacoes_router

router = APIRouter()
router.include_router(contratos_liquidacao_router)
router.include_router(curadoria_liquidacoes_router)
