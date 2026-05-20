"""BI module — root router (monta todas as L2 + metadados)."""

from fastapi import APIRouter

from app.modules.bi.api import (
    benchmark,
    benchmark2,
    metadata,
    operacoes2,
    operacoes4,
)

router = APIRouter()

# L2 Operacoes — entrega canonica desde 2026-05-17 (substituiu o legado).
# KPI Strip global + 4 abas (Volume & Ritmo, Produtos & Pricing, Receita,
# Cedentes & Concentracao). Pagina vive em `/bi/operacoes2` no frontend
# (rename pasta -> /bi/operacoes pendente: tech debt).
router.include_router(operacoes2.router)

# L2 Operacoes4 — pagina /bi/operacoes4 (Mes Corrente · controladoria,
# regime caixa). Lente alternativa de operacoes3 com foco em composicao
# da receita + yield por DU. Ver CLAUDE.md banner operacoes4.
router.include_router(operacoes4.router)

# L2 Benchmark (CVM FIDC via postgres_fdw — CLAUDE.md 13.1).
# Pre-requisito runtime: schema `cvm_remote.*` configurado no gr_db.
router.include_router(benchmark.router)

# L2 Benchmark2 (lista completa de fundos CVM — usa <DataTableShell>).
router.include_router(benchmark2.router)

# Endpoints de taxonomia/metadata usados pelos filtros do frontend.
router.include_router(metadata.router)
