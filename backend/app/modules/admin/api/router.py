"""Admin module router — aggregates AI-related admin endpoints.

All routes here require BOTH:
    - The principal's tenant is the system maintainer
      (`require_system_maintainer`).
    - The principal has Module.ADMIN + Permission.ADMIN
      (`require_module(Module.ADMIN, Permission.ADMIN)`).

Mounted at `/admin` from `api/v1/router.py`.
"""

from fastapi import APIRouter

from app.modules.admin.api import (
    ai_agent_definitions,
    ai_agents,
    ai_expertises,
    ai_personas,
    ai_prompts,
    ai_provider_credentials,
    ai_subscriptions,
    ai_tools,
    data_contracts,
    data_provider_credentials,
    tenants,
    users,
)

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(ai_provider_credentials.router)
router.include_router(ai_subscriptions.router)
router.include_router(ai_prompts.router)
router.include_router(ai_agents.router)  # legado: /ai/agents (agent_config override)
router.include_router(ai_personas.router)
router.include_router(ai_expertises.router)
router.include_router(ai_agent_definitions.router)  # novo: /ia/agents (catalogo central)
router.include_router(ai_tools.router)  # F2.c.4: /ia/tools (read-only)
router.include_router(data_provider_credentials.router)  # /admin/data-providers
router.include_router(data_contracts.router)  # /admin/data-contracts (Fase 5)
router.include_router(tenants.router)
router.include_router(users.router)
