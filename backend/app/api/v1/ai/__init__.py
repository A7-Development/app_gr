"""AI capability endpoints (tenant-facing).

Mounted at `/ai` from `api/v1/router.py`.
"""

from fastapi import APIRouter

from app.api.v1.ai import chat, conversations, insights, quota

router = APIRouter(prefix="/ai", tags=["ai"])
router.include_router(chat.router)
router.include_router(insights.router)
router.include_router(quota.router)
router.include_router(conversations.router)

__all__ = ["router"]
