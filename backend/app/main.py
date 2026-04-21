"""FastAPI app entrypoint."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.api.v1.schemas import HealthResponse
from app.core.config import get_settings
from app.scheduler.scheduler import shutdown_scheduler, start_scheduler

_settings = get_settings()

# Permite desabilitar o scheduler em contexto de test/CI (APP_SCHEDULER=off)
_SCHEDULER_ENABLED = os.getenv("APP_SCHEDULER", "on").lower() not in {"off", "false", "0"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    """App lifespan (startup/shutdown hooks)."""
    # Startup
    if _SCHEDULER_ENABLED:
        start_scheduler()
    yield
    # Shutdown
    if _SCHEDULER_ENABLED:
        shutdown_scheduler()


app = FastAPI(
    title="GR API",
    description="Plataforma de inteligencia de dados para FIDCs",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Liveness/readiness endpoint."""
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=_settings.APP_ENV,
    )


app.include_router(api_router, prefix="/api/v1")
