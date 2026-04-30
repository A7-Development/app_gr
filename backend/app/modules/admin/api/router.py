"""Admin module router — aggregates AI-related admin endpoints.

All routes here require BOTH:
    - The principal's tenant is the system maintainer
      (`require_system_maintainer`).
    - The principal has Module.ADMIN + Permission.ADMIN
      (`require_module(Module.ADMIN, Permission.ADMIN)`).

Mounted at `/admin` from `api/v1/router.py`.
"""

from fastapi import APIRouter

from app.modules.admin.api import ai_prompts, ai_provider_credentials, ai_subscriptions

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(ai_provider_credentials.router)
router.include_router(ai_subscriptions.router)
router.include_router(ai_prompts.router)
