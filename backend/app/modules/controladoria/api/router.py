"""Controladoria — root router (monta L2)."""

from fastapi import APIRouter

from app.modules.controladoria.api import cota_sub, reports

router = APIRouter()

# L2 Cota Sub — analise da cota subordinada do FIDC.
router.include_router(cota_sub.router)

# L2 Relatorios — catalogo unico de relatorios das administradoras (QiTech, ...).
# Plano: ~/.claude/plans/shimmering-snuggling-snail.md.
router.include_router(reports.router)
