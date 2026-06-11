"""Controladoria — root router (monta L2)."""

from fastapi import APIRouter

from app.modules.controladoria.api import (
    conciliacao_boleto,
    cota_sub,
    evolucao_patrimonial,
    qitech_estoque_carteira,
    reports,
)

router = APIRouter()

# L2 Cota Sub — analise da cota subordinada do FIDC.
router.include_router(cota_sub.router)

# L2 Evolucao Patrimonial — serie temporal do PL do passivo (todas as classes).
router.include_router(evolucao_patrimonial.router)


# L2 Relatorios — catalogo unico de relatorios das administradoras (QiTech, ...).
# Plano: ~/.claude/plans/shimmering-snuggling-snail.md.
router.include_router(reports.router)

# Bundle de agregados do slug `qitech-estoque-carteira` (detail page rica).
# Tabela paginada de recebiveis continua via `GET /relatorios/{slug}` generico
# acima.
router.include_router(qitech_estoque_carteira.router)

# L2 Conciliacoes > Banco Cobrador — carteira Bitfin x boletos CNAB.
router.include_router(conciliacao_boleto.router)
