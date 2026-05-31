"""wh_bitfin_dre_natureza_rule -- de-para de NATUREZA da receita do DRE Bitfin.

Granularidade (fonte, categoria, descricao) -> natureza. Mais fina que a
classificacao de GRUPO (wh_dre_classification_rule, nivel categoria): a
natureza distingue, DENTRO de uma categoria, a economia da linha.

Naturezas (otica da factoring/gestora -- todas RECEITA):
    DESAGIO     -- juros/desconto da antecipacao
    TARIFA      -- tarifas de servico e reembolsos
    MULTA       -- multas (atraso, prorrogacao)
    JUROS       -- juros de mora/recompra/prorrogacao
    AD_VALOREM  -- receita de servico ad valorem (factoring)
    IMPOSTO     -- repasse de tributo (ex.: IOF) que a factoring arrecada

Ancorada no catalogo NATIVO do Bitfin (OrganizacaoTarifa.Tipo), NAO em
heuristica de texto:
    Tipo 1 -> sempre TARIFA
    Tipo 2 -> de-para explicito (seed da migration)
Item sem regra -> mapper grava natureza NULL (linha de receita com natureza
NULL = "nao classificado", flag de governanca -- nunca chutado).

Cascata + soft-delete espelham wh_dre_classification_rule (CLAUDE.md 14.3):
tenant_id NULL = regra global; tenant_id = X = override; ativa quando
valid_until IS NULL.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WhBitfinDreNaturezaRule(Base):
    """Regra (Fonte, Categoria, Descricao) -> Natureza. Global ou override."""

    __tablename__ = "wh_bitfin_dre_natureza_rule"
    __table_args__ = (
        Index(
            "ix_wh_bitfin_dre_natureza_rule_lookup",
            "fonte",
            "categoria",
            "descricao",
            "tenant_id",
            postgresql_where="valid_until IS NULL",
        ),
        Index(
            "uq_wh_bitfin_dre_natureza_rule_active",
            "tenant_id",
            "fonte",
            "categoria",
            "descricao",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where="valid_until IS NULL",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Chave (mesma granularidade que o mapper resolve por linha do demonstrativo).
    fonte: Mapped[str] = mapped_column(String(50), nullable=False)
    categoria: Mapped[str] = mapped_column(String(50), nullable=False)
    descricao: Mapped[str] = mapped_column(String(80), nullable=False)

    # Output: natureza da receita (DESAGIO/TARIFA/MULTA/JUROS/AD_VALOREM/IMPOSTO).
    natureza: Mapped[str] = mapped_column(String(20), nullable=False)

    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
