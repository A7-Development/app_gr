"""Resolve the stable titulo identity of each boleto event.

Bug fix (Ricardo 2026-07-09, cross-checked against Bitfin): `nosso_numero`
COLLIDES across cedentes (the collecting bank reuses it), so joining a
payment event to a titulo by nosso_numero fans out and fabricates false
praca convergence. The event, however, carries its own `numero_documento`
(= the titulo number), which resolves to a single titulo in 96% of cases;
value is the tie-breaker for the rest.

`titulo_id` (Bitfin TituloId, already in wh_titulo) is the AUTHORITATIVE
identity — using it is proveniencia, not ERP analysis (praca stays 100% from
our CNAB). This materializes it on wh_boleto_evento so every downstream join
(deteccao, praca, S2) uses a clean identity instead of the colliding key.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Cascade: match event.numero_documento -> wh_titulo.numero; when the number
# maps to more than one titulo (different cedentes reuse numbers), pick the
# titulo whose face value is closest to the paid value.
_RESOLVE = text("""
UPDATE wh_boleto_evento be
SET titulo_id = (
    SELECT t.titulo_id
    FROM wh_titulo t
    WHERE t.tenant_id = be.tenant_id
      AND t.numero = be.numero_documento
    ORDER BY abs(coalesce(t.valor, 0) - coalesce(be.valor_pago, be.valor_titulo, 0)) ASC,
             t.titulo_id ASC
    LIMIT 1
)
WHERE be.tenant_id = :tenant_id
  AND be.numero_documento IS NOT NULL
""")


async def resolve_titulo_ids(db: AsyncSession, tenant_id: UUID) -> int:
    """Populate wh_boleto_evento.titulo_id for a tenant. Returns rows updated."""
    result = await db.execute(_RESOLVE, {"tenant_id": tenant_id})
    n = result.rowcount or 0
    logger.info("resolve_titulo_ids: %d eventos com titulo_id resolvido", n)
    return n
