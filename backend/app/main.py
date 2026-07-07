"""FastAPI app entrypoint."""

import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    # §1b — reconcilia runs orfaos: como o motor roda em processo unico, um
    # run em RUNNING apos um restart perdeu sua task de execucao. Marca FAILED
    # pra nao ficar girando pra sempre (em vez do antigo "RUNNING preso").
    try:
        from app.agentic.workflows.services.engine import reconcile_orphaned_runs
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await reconcile_orphaned_runs(db)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "reconcile_orphaned_runs falhou no startup (seguindo mesmo assim)"
        )

    if _SCHEDULER_ENABLED:
        start_scheduler()
    yield
    # Shutdown
    if _SCHEDULER_ENABLED:
        shutdown_scheduler()


# A API e publica atras do gateway (callback.strataai.com.br) — o schema
# OpenAPI completo e mapa de reconhecimento pra atacante. Em producao,
# Swagger/ReDoc/openapi.json ficam desligados; em dev/test continuam ativos.
_IS_PRODUCTION = _settings.APP_ENV == "production"

app = FastAPI(
    title="GR API",
    description="Plataforma de inteligencia de dados para FIDCs",
    version=__version__,
    lifespan=lifespan,
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    # Dev: aceita qualquer porta de localhost (Next.js dev server cai em
    # porta aleatoria via autoPort:true quando 3000 esta ocupada). Seguro
    # porque so origens locais batem o regex.
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_logger = logging.getLogger(__name__)
# Espelha o allow_origin_regex do CORSMiddleware acima (localhost qualquer porta).
_LOCALHOST_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


def _cors_origin_for(origin: str | None) -> str | None:
    """Origin a ecoar no header de CORS, com a MESMA politica do middleware
    (match exato na allowlist OU regex localhost). None = nao permitido."""
    if not origin:
        return None
    if origin in _settings.cors_origins_list or _LOCALHOST_ORIGIN_RE.match(origin):
        return origin
    return None


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Resposta 500 que CARREGA header de CORS.

    Sem isto, uma excecao nao-tratada sobe ate o ServerErrorMiddleware do
    Starlette — que fica FORA do CORSMiddleware — e o 500 sai sem
    Access-Control-Allow-Origin. O browser entao mascara o erro real como
    "No 'Access-Control-Allow-Origin' header", escondendo a causa (ja aconteceu
    com a colisao de versao de workflow). Aqui logamos o traceback (igual ao
    comportamento padrao) e injetamos o CORS manualmente.

    HTTPException (404/401/409/...) NAO cai aqui — tem handler proprio e ja passa
    pelo CORSMiddleware normalmente.
    """
    _logger.exception("Erro nao tratado em %s %s", request.method, request.url.path)
    resp = JSONResponse(status_code=500, content={"detail": "Erro interno do servidor."})
    origin = _cors_origin_for(request.headers.get("origin"))
    if origin is not None:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Vary"] = "Origin"
    return resp


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Liveness/readiness endpoint."""
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=_settings.APP_ENV,
    )


app.include_router(api_router, prefix="/api/v1")
