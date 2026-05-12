"""Classifier COSIF — cascata override -> rule -> pendente.

Uso:
    cache = await load_rules_cache(db)
    overrides = await load_overrides(db, tenant_id, fundo_id)
    for row in silver_rows:
        res = classify(row, cache, overrides)
        # res.cosif, res.source, res.classe_sr_mez_sub, ...

Performance: cache de regras carregado 1x por request; overrides idem.
~200 rows/dia para REALINVEST = ~200 chamadas de classify(), todas
in-memory (sem ida ao DB).

Design completo: backend/docs/atribuicao-cota-sub-cosif.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.controladoria.models.cosif import (
    CosifCatalog,
    CosifRule,
    TenantPapelClassificacao,
)
from app.modules.controladoria.services.cosif.predicates import match


@dataclass(frozen=True)
class CosifResolution:
    """Resultado da classificacao para 1 row de silver."""

    cosif: str | None
    """Codigo COSIF resolvido. None = pendente classificacao."""

    source: str
    """'override' | 'rule:<rule_id_humano>' | 'pendente'"""

    confidence: str
    """'alta' | 'media' | 'baixa'"""

    classe_sr_mez_sub: str | None = None
    """senior | mezanino | subordinado | compensacao | None"""

    rule_id: UUID | None = None
    """ID da CosifRule que matchou (se source='rule:*')."""

    override_id: UUID | None = None
    """ID da TenantPapelClassificacao (se source='override')."""


@dataclass(frozen=True)
class _CachedRule:
    """Versao imutavel da regra para uso in-memory durante classify."""
    id: UUID
    silver_origin: str
    predicate: dict[str, Any]
    cosif_codigo: str | None
    classe_sr_mez_sub: str | None
    priority: int
    confidence: str
    rule_id_humano: str


@dataclass(frozen=True)
class _CachedOverride:
    """Versao imutavel do override (lookup por chave composta)."""
    id: UUID
    cosif_override: str
    classe_sr_mez_sub: str | None


async def load_rules_cache(
    db: AsyncSession,
) -> dict[str, list[_CachedRule]]:
    """Carrega todas as regras ativas agrupadas por silver_origin.

    Cada lista ordenada por priority desc — classify percorre na ordem.
    """
    today_check = "(valid_to IS NULL OR valid_to >= CURRENT_DATE)"
    rows = (
        await db.execute(
            select(CosifRule).where(
                CosifRule.valid_from <= __import__("datetime").date.today()
            )
        )
    ).scalars().all()
    out: dict[str, list[_CachedRule]] = {}
    for r in rows:
        if r.valid_to is not None and r.valid_to < __import__("datetime").date.today():
            continue
        cached = _CachedRule(
            id=r.id,
            silver_origin=r.silver_origin,
            predicate=r.predicate_jsonb,
            cosif_codigo=r.cosif_codigo,
            classe_sr_mez_sub=r.classe_sr_mez_sub,
            priority=r.priority,
            confidence=r.confidence,
            rule_id_humano=r.rule_id_humano,
        )
        out.setdefault(r.silver_origin, []).append(cached)
    # Ordena por priority desc dentro de cada silver_origin.
    for silver, lst in out.items():
        lst.sort(key=lambda x: (-x.priority, x.rule_id_humano))
    return out


async def load_overrides(
    db: AsyncSession,
    tenant_id: UUID,
    fundo_id: UUID,
) -> dict[tuple[str, str], _CachedOverride]:
    """Carrega overrides do tenant para um fundo. Chave: (silver, identificador)."""
    rows = (
        await db.execute(
            select(TenantPapelClassificacao).where(
                TenantPapelClassificacao.tenant_id == tenant_id,
                TenantPapelClassificacao.fundo_id == fundo_id,
            )
        )
    ).scalars().all()
    return {
        (r.silver_origin, r.identificador): _CachedOverride(
            id=r.id,
            cosif_override=r.cosif_override,
            classe_sr_mez_sub=r.classe_sr_mez_sub,
        )
        for r in rows
    }


async def load_catalog_tree(
    db: AsyncSession,
) -> dict[str, CosifCatalog]:
    """Carrega o catalogo COSIF inteiro (indexado por codigo)."""
    rows = (await db.execute(select(CosifCatalog))).scalars().all()
    return {r.codigo: r for r in rows}


def classify(
    silver_origin: str,
    row: dict[str, Any],
    rules_cache: dict[str, list[_CachedRule]],
    overrides: dict[tuple[str, str], _CachedOverride],
) -> CosifResolution:
    """Aplica cascata: override -> rule -> pendente.

    `row` deve conter pelo menos `codigo` (identificador estavel) + os
    campos referenciados pelos predicates ativos para `silver_origin`.

    Identificador para override: campo "codigo" ou "k" do row (fallback).
    """
    identificador = row.get("codigo") or row.get("k") or ""
    if identificador is not None:
        identificador = str(identificador).strip().upper()

    # (1) Override
    if identificador:
        ovr = overrides.get((silver_origin, identificador))
        if ovr:
            return CosifResolution(
                cosif=ovr.cosif_override,
                source="override",
                confidence="alta",
                classe_sr_mez_sub=ovr.classe_sr_mez_sub,
                override_id=ovr.id,
            )

    # (2) Regras estruturais
    for rule in rules_cache.get(silver_origin, []):
        if match(rule.predicate, row):
            return CosifResolution(
                cosif=rule.cosif_codigo,
                source=f"rule:{rule.rule_id_humano}",
                confidence=rule.confidence,
                classe_sr_mez_sub=rule.classe_sr_mez_sub,
                rule_id=rule.id,
            )

    # (3) Pendente
    return CosifResolution(
        cosif=None,
        source="pendente",
        confidence="baixa",
    )
