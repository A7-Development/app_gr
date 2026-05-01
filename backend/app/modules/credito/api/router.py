"""Sub-router for /api/v1/credito.

Mounted in `app.api.v1` along with the other module routers.
"""

from fastapi import APIRouter

from app.modules.credito.api import checklist, dossier, template, workflow

router = APIRouter(prefix="/credito", tags=["credito"])

router.include_router(dossier.router)
router.include_router(workflow.router)
router.include_router(checklist.router)
router.include_router(template.router)
