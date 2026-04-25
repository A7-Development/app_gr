"""Cadastros -- root router (monta todas as L2 do modulo)."""

from fastapi import APIRouter

from app.modules.cadastros.api import unidades_administrativas

router = APIRouter()

# L2 Unidades Administrativas (Sprint UA, primeira entrega do modulo).
router.include_router(unidades_administrativas.router)
