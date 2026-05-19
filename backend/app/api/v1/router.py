"""API v1 root router — aggregates cross-cutting + all modules."""

from fastapi import APIRouter

from app.api.v1 import audit, auth, invitations, system
from app.api.v1.ai import router as ai_router
from app.modules.admin.api import router as admin_router
from app.modules.bi.api.router import router as bi_router
from app.modules.cadastros.api.router import router as cadastros_router
from app.modules.controladoria.api.router import router as controladoria_router
from app.modules.credito.api.router import router as credito_router
from app.modules.integracoes.routers.endpoints import (
    router as integracoes_endpoints_router,
)
from app.modules.integracoes.routers.qitech_bank_account import (
    router as integracoes_qitech_bank_account_router,
)
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

# Public invitation endpoints (no auth — accepts/preview).
api_router.include_router(invitations.router)

# AI capability (transversal — own subscription/permission, see CLAUDE.md sec 19).
api_router.include_router(ai_router)

# Admin module (system maintainer only — gestao global de IA, credenciais, etc).
api_router.include_router(admin_router)

# Modules (each endpoint uses `require_module(Module.X, Permission.Y)`).
api_router.include_router(bi_router, prefix="/bi", tags=["bi"])
api_router.include_router(
    cadastros_router, prefix="/cadastros", tags=["cadastros"]
)
api_router.include_router(
    controladoria_router, prefix="/controladoria", tags=["controladoria"]
)
# Modulo credito — dossie inteligente + workflow visual + agentes especialistas.
# (router ja inclui prefix="/credito" internamente)
api_router.include_router(credito_router)
api_router.include_router(
    integracoes_sources_router, prefix="/integracoes", tags=["integracoes"]
)
api_router.include_router(
    integracoes_endpoints_router,
    prefix="/integracoes",
    tags=["integracoes:endpoints"],
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
api_router.include_router(
    integracoes_qitech_bank_account_router,
    prefix="/integracoes",
    tags=["integracoes:qitech-bank-account"],
)
