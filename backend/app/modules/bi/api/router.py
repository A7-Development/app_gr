"""BI module — root router (monta todas as L2 + metadados)."""

from fastapi import APIRouter

from app.modules.bi.api import benchmark, benchmark2, metadata, operacoes, operacoes2

router = APIRouter()

# L2 Operacoes (Sprint 4 entrega inicial).
router.include_router(operacoes.router)

# L2 Operacoes2 (refatoracao 2026-05-03): nova UX em rota paralela.
# KPI Strip global + 4 abas (Volume & Ritmo, Produtos & Pricing, Receita,
# Cedentes & Concentracao). Pagina vive em `/bi/operacoes2` no frontend.
router.include_router(operacoes2.router)

# L2 Benchmark (CVM FIDC via postgres_fdw — CLAUDE.md 13.1).
# Pre-requisito runtime: schema `cvm_remote.*` configurado no gr_db.
router.include_router(benchmark.router)

# L2 Benchmark2 (lista completa de fundos CVM — usa <DataTableShell>).
router.include_router(benchmark2.router)

# Endpoints de taxonomia/metadata usados pelos filtros do frontend.
router.include_router(metadata.router)
