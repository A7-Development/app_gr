"""DRE classifier -- (Fonte, Categoria) -> (GrupoDRE, SubGrupo, OrdemGrupo, Ativo).

Substitui o lookup `ANALYTICS.dbo.DREClassificacao` (A7-especifico). A regra
agora mora em `wh_dre_classification_rule` no gr_db (CLAUDE.md secao 14.3),
com cascata override-por-tenant -> regra global.

Performance: load_dre_classifier carrega todas as regras ativas em memoria
(~77 globais + alguns overrides). Per-row classify e O(1) -- adequado para
runs com milhares de linhas por competencia.

Versionamento: cada `WhDreClassificationRule.version` carrega o numero da
versao da regra (CLAUDE.md secao 14.3). Por enquanto o classifier sempre
usa a versao "ativa" (valid_until IS NULL); replay com versao antiga e
followup quando aparecer necessidade.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse.dre_classification_rule import WhDreClassificationRule


@dataclass(frozen=True)
class DreClassification:
    """Resultado da classificacao para 1 row de bronze."""

    grupo_dre: str
    subgrupo: str
    ordem_grupo: int
    ativo: bool
    rule_version: int
    source: str
    """'tenant_override' | 'global'"""


class DreClassifier:
    """Lookup in-memory de regras DRE. Construir uma vez por sync."""

    def __init__(self, rules: dict[tuple[str, str], DreClassification]):
        self._rules = rules

    def classify(self, fonte: str, categoria: str) -> DreClassification | None:
        """Retorna a classificacao da (fonte, categoria) ou None se nao houver
        regra. Caller decide se descarta ou loga warning."""
        return self._rules.get((fonte, categoria))

    @property
    def rule_count(self) -> int:
        return len(self._rules)


async def load_dre_classifier(
    db: AsyncSession, tenant_id: UUID
) -> DreClassifier:
    """Carrega regras DRE ativas para o tenant + globais. Override de
    tenant vence sobre global (mesmo (fonte, categoria)).

    Implementacao da cascata: ordena rows com `tenant_id IS NULL` primeiro,
    `tenant_id = :t` por ultimo. Construindo o dict nessa ordem, o override
    de tenant sobrescreve o global no `dict[key] = ...`.
    """
    stmt = (
        select(WhDreClassificationRule)
        .where(
            WhDreClassificationRule.valid_until.is_(None),
            or_(
                WhDreClassificationRule.tenant_id == tenant_id,
                WhDreClassificationRule.tenant_id.is_(None),
            ),
        )
        # Globais primeiro, overrides depois -> overrides vencem no dict.
        .order_by(WhDreClassificationRule.tenant_id.is_not(None))
    )
    rows = (await db.execute(stmt)).scalars().all()

    rules: dict[tuple[str, str], DreClassification] = {}
    for r in rows:
        key = (r.fonte, r.categoria)
        rules[key] = DreClassification(
            grupo_dre=r.grupo_dre,
            subgrupo=r.subgrupo,
            ordem_grupo=r.ordem_grupo,
            ativo=r.ativo,
            rule_version=r.version,
            source="tenant_override" if r.tenant_id is not None else "global",
        )
    return DreClassifier(rules)
