"""API v1 root router — aggregates cross-cutting + all modules."""

from fastapi import APIRouter

from app.api.v1 import audit, auth
from app.modules.bi.api.router import router as bi_router

api_router = APIRouter()

# Cross-cutting (no module guard; auth-only)
api_router.include_router(auth.router)
api_router.include_router(audit.router)

# Modules (each endpoint uses `require_module(Module.X, Permission.Y)`).
api_router.include_router(bi_router, prefix="/bi", tags=["bi"])
