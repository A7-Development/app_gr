"""BI module — root router (monta todas as L2 + metadados)."""

from fastapi import APIRouter

from app.modules.bi.api import benchmark, metadata, operacoes

router = APIRouter()

# L2 Operacoes (Sprint 4 entrega inicial).
router.include_router(operacoes.router)

# L2 Benchmark (CVM FIDC via postgres_fdw — CLAUDE.md 13.1).
# Pre-requisito runtime: schema `cvm_remote.*` configurado no gr_db.
router.include_router(benchmark.router)

# Endpoints de taxonomia/metadata usados pelos filtros do frontend.
router.include_router(metadata.router)
