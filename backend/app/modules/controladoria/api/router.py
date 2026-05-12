"""Controladoria — root router (monta L2)."""

from fastapi import APIRouter

from app.modules.controladoria.api import (
    cota_sub,
    dre,
    qitech_estoque_carteira,
    reports,
)

router = APIRouter()

# L2 Cota Sub — analise da cota subordinada do FIDC.
router.include_router(cota_sub.router)

# L2 DRE — Demonstrativo do Resultado do Exercicio. Le silver wh_dre_mensal
# populada pelo ETL Bitfin (bronze + classifier, ver commit 4d5399e).
router.include_router(dre.router)

# L2 Relatorios — catalogo unico de relatorios das administradoras (QiTech, ...).
# Plano: ~/.claude/plans/shimmering-snuggling-snail.md.
router.include_router(reports.router)

# Bundle de agregados do slug `qitech-estoque-carteira` (detail page rica).
# Tabela paginada de recebiveis continua via `GET /relatorios/{slug}` generico
# acima.
router.include_router(qitech_estoque_carteira.router)
