"""Aggregate router of the Risco module (mounted under /api/v1/risco)."""

from fastapi import APIRouter

from app.modules.risco.api.cedentes import router as cedentes_router
from app.modules.risco.api.contratos_liquidacao import router as contratos_liquidacao_router
from app.modules.risco.api.curadoria_liquidacoes import router as curadoria_liquidacoes_router
from app.modules.risco.api.lastro_fiscal import router as lastro_fiscal_router
from app.modules.risco.api.padroes_liquidacao import router as padroes_liquidacao_router
from app.modules.risco.api.rating_liquidacao import router as rating_liquidacao_router

router = APIRouter()
router.include_router(cedentes_router)
router.include_router(contratos_liquidacao_router)
router.include_router(curadoria_liquidacoes_router)
router.include_router(lastro_fiscal_router)
router.include_router(padroes_liquidacao_router)
router.include_router(rating_liquidacao_router)
