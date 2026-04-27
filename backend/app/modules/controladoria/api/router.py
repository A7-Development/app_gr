"""Controladoria — root router (monta L2)."""

from fastapi import APIRouter

from app.modules.controladoria.api import cota_sub

router = APIRouter()

# L2 Cota Sub — analise da cota subordinada do FIDC.
router.include_router(cota_sub.router)
