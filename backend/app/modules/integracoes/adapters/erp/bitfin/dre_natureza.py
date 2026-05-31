"""Loader do de-para de NATUREZA da receita do DRE (wh_bitfin_dre_natureza_rule).

Espelha `load_dre_classifier` (classificacao de grupo), mas para a dimensao
mais fina de NATUREZA: (fonte, categoria, descricao) -> natureza.

Mora no adapter (CLAUDE.md 13.2.1: a traducao raw->silver e responsabilidade
do adapter). Lookup O(1) em memoria, construido 1x por sync. Cascata
override-por-tenant -> global, igual ao classifier.

Retorna None para chave sem regra -> mapper grava natureza NULL = "nao
classificada" (flag de governanca, nunca chutada).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse.bitfin_dre_natureza_rule import WhBitfinDreNaturezaRule

# Chave (fonte, categoria, descricao) -> natureza.
NaturezaMap = dict[tuple[str, str, str], str]


async def load_dre_natureza(db: AsyncSession, tenant_id: UUID) -> NaturezaMap:
    """Carrega regras de natureza ativas (global + override do tenant).

    Override do tenant vence sobre a global na mesma (fonte, categoria,
    descricao): globais primeiro, overrides depois -> dict[key] sobrescreve.
    """
    stmt = (
        select(WhBitfinDreNaturezaRule)
        .where(
            WhBitfinDreNaturezaRule.valid_until.is_(None),
            or_(
                WhBitfinDreNaturezaRule.tenant_id == tenant_id,
                WhBitfinDreNaturezaRule.tenant_id.is_(None),
            ),
        )
        .order_by(WhBitfinDreNaturezaRule.tenant_id.is_not(None))
    )
    rows = (await db.execute(stmt)).scalars().all()

    natureza_map: NaturezaMap = {}
    for r in rows:
        natureza_map[(r.fonte, r.categoria, r.descricao)] = r.natureza
    return natureza_map
