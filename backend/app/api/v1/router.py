"""API v1 root router — aggregates cross-cutting + all modules."""

from fastapi import APIRouter

from app.api.v1 import audit, auth, system
from app.modules.bi.api.router import router as bi_router
from app.modules.cadastros.api.router import router as cadastros_router
from app.modules.integracoes.routers.qitech_custodia import (
    router as integracoes_qitech_custodia_router,
)
from app.modules.integracoes.routers.qitech_jobs import (
    router as integracoes_qitech_jobs_router,
)
from app.modules.integracoes.routers.sources import router as integracoes_sources_router
from app.modules.integracoes.routers.webhooks import router as integracoes_webhooks_router

api_router = APIRouter()

# Cross-cutting (no module guard; auth-only)
api_router.include_router(auth.router)
api_router.include_router(audit.router)
api_router.include_router(system.router)

# Modules (each endpoint uses `require_module(Module.X, Permission.Y)`).
api_router.include_router(bi_router, prefix="/bi", tags=["bi"])
api_router.include_router(
    cadastros_router, prefix="/cadastros", tags=["cadastros"]
)
api_router.include_router(
    integracoes_sources_router, prefix="/integracoes", tags=["integracoes"]
)
api_router.include_router(
    integracoes_webhooks_router, prefix="/integracoes", tags=["integracoes:webhooks"]
)
api_router.include_router(
    integracoes_qitech_jobs_router,
    prefix="/integracoes",
    tags=["integracoes:qitech-jobs"],
)
api_router.include_router(
    integracoes_qitech_custodia_router,
    prefix="/integracoes",
    tags=["integracoes:qitech-custodia"],
)
