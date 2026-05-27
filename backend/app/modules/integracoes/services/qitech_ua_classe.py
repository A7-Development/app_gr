"""Catalog lookup: which cota classes a QiTech `market/*` payload must carry.

Bridges the pre-registered catalog (`qitech_ua_classe`, per UA) and the
completeness assessor. Two pieces:

1. `_EXPECTED_PAPEIS_BY_TIPO` — a STATIC map (property of the QiTech API,
   identical across tenants) declaring which cota papeis each `market/*`
   endpoint family carries. Empirically: mec/rf/rentabilidade/tesouraria/
   demonstrativo-caixa break down per class (Sub+Mez+Sen); conta-corrente/
   cpr/outros-ativos/outros-fundos/rf-compromissadas are consolidated and
   carry only the Subordinada.

2. `get_expected_classes(...)` — intersects that static map with the
   tenant/UA catalog rows that are *vigente* on the position date, returning
   the set of `clienteId`s the payload must contain. Empty set = "no opinion"
   → the assessor falls back to its legacy heuristic.

Keyed by the BARE `tipo_de_mercado` (hyphen form, e.g. "conta-corrente") to
match what `etl._upsert_raw` and `completeness._ASSESSORS` already use — NOT
the dotted/underscore `endpoint_name` of `endpoint_date_state`.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PapelCota
from app.modules.integracoes.models.qitech_ua_classe import QiTechUaClasse

# Which cota papeis each market endpoint family is expected to carry.
# Endpoints absent from this map → catalog NOT applied (assessor falls back to
# its legacy heuristic). Derived empirically from stored payloads (2026-05).
_EXPECTED_PAPEIS_BY_TIPO: dict[str, frozenset[PapelCota]] = {
    # Break down per cota class.
    "mec": frozenset({PapelCota.SUBORDINADA, PapelCota.MEZANINO, PapelCota.SENIOR}),
    "rf": frozenset({PapelCota.SUBORDINADA, PapelCota.MEZANINO, PapelCota.SENIOR}),
    "rentabilidade": frozenset(
        {PapelCota.SUBORDINADA, PapelCota.MEZANINO, PapelCota.SENIOR}
    ),
    "tesouraria": frozenset(
        {PapelCota.SUBORDINADA, PapelCota.MEZANINO, PapelCota.SENIOR}
    ),
    "demonstrativo-caixa": frozenset(
        {PapelCota.SUBORDINADA, PapelCota.MEZANINO, PapelCota.SENIOR}
    ),
    # Consolidated at the fund level — only the Subordinada appears.
    "conta-corrente": frozenset({PapelCota.SUBORDINADA}),
    "cpr": frozenset({PapelCota.SUBORDINADA}),
    "outros-ativos": frozenset({PapelCota.SUBORDINADA}),
    "outros-fundos": frozenset({PapelCota.SUBORDINADA}),
    "rf-compromissadas": frozenset({PapelCota.SUBORDINADA}),
}


def tipo_supports_catalog(tipo_de_mercado: str) -> bool:
    """Whether a tipo participates in catalog-based completeness."""
    return tipo_de_mercado in _EXPECTED_PAPEIS_BY_TIPO


async def get_expected_classes(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    tipo_de_mercado: str,
    on_date: date,
) -> set[str]:
    """Return the `clienteId`s expected for this endpoint+date.

    A clienteId is expected when its catalog row is (a) vigente on `on_date`
    (`ativo_desde <= on_date` AND (`ativo_ate` IS NULL OR `ativo_ate >=
    on_date`)) and (b) its `papel` is in the static map for `tipo_de_mercado`.

    Returns an EMPTY set (the "fall back to legacy" signal) when:
      - the UA is unknown (`unidade_administrativa_id is None`),
      - the tipo does not participate in catalog assessment,
      - or the UA has no matching vigente catalog rows.

    Tenant isolation: the query is scoped by `tenant_id` first (CLAUDE.md §10).
    """
    if unidade_administrativa_id is None:
        return set()
    expected_papeis = _EXPECTED_PAPEIS_BY_TIPO.get(tipo_de_mercado)
    if not expected_papeis:
        return set()

    wanted = {p.value for p in expected_papeis}
    stmt = select(QiTechUaClasse.cliente_id, QiTechUaClasse.papel).where(
        QiTechUaClasse.tenant_id == tenant_id,
        QiTechUaClasse.unidade_administrativa_id == unidade_administrativa_id,
        QiTechUaClasse.ativo_desde <= on_date,
        (QiTechUaClasse.ativo_ate.is_(None))
        | (QiTechUaClasse.ativo_ate >= on_date),
    )
    rows = (await db.execute(stmt)).all()
    return {cliente_id for cliente_id, papel in rows if papel in wanted}
