"""Modelos COSIF — infraestrutura de classificacao agnostica multi-tenant.

Arquitetura em 3 camadas (cascata override -> rule -> pendente):

  CosifCatalog          arvore COSIF oficial (PLANO COSIF II — BACEN)
  CosifRule             regras estruturais agnosticas (system maintainer A7)
  TenantPapelClassificacao  overrides editaveis livremente por tenant admin

Classificacao e RUNTIME — nao ha coluna `cosif_codigo` em silvers. Decisao
2026-05-11 apos confirmar que raw QiTech nao traz cosif em nenhum dos 10
endpoints.

Migration: alembic/versions/ba7032c76c17_cosif_infra_*.
Design: backend/docs/atribuicao-cota-sub-cosif.md.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class CosifCatalog(Base):
    """Arvore oficial do PLANO COSIF II.

    Auto-referencial via `parent_codigo` — permite reconstruir hierarquia
    em qualquer profundidade (nivel 1-6).
    """

    __tablename__ = "cosif_catalog"
    __table_args__ = (
        CheckConstraint(
            "natureza IN ('D','C')", name="ck_cosif_catalog_natureza"
        ),
        Index("ix_cosif_catalog_parent_codigo", "parent_codigo"),
        Index("ix_cosif_catalog_grupo", "grupo"),
    )

    codigo: Mapped[str] = mapped_column(String(20), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # 'D' = Devedora (Ativo), 'C' = Credora (Passivo, PL, Receitas).
    natureza: Mapped[str] = mapped_column(String(1), nullable=False)
    parent_codigo: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("cosif_catalog.codigo", ondelete="RESTRICT"),
        nullable=True,
    )
    nivel: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Grupo do plano: 1=Ativo, 3/9=Compensacao, 4=Passivo, 6=PL, 7=Receitas,
    # 8=Despesas. Replica `codigo[0]` por performance de filtro.
    grupo: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # ID do plano: 5 = PLANO COSIF II (default — REALINVEST).
    plano_id: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("5")
    )


class CosifRule(Base):
    """Regra estrutural agnostica para classificacao.

    Predicado serializado em JSONB. Suporta:
      {"field":"<col>", "op":"<eq|ne|in|contains|contains_ci|starts_with|
                                ends_with|qtde_signal>", "value":<v>}
      {"all":[...]}  -> AND
      {"any":[...]}  -> OR

    `cosif_codigo` pode ser NULL — regra que marca como
    "pendente_classificacao" (caso da contrapartida de compensacao 3/9).
    """

    __tablename__ = "cosif_rule"
    __table_args__ = (
        UniqueConstraint(
            "rule_id_humano", name="uq_cosif_rule_rule_id_humano"
        ),
        CheckConstraint(
            "confidence IN ('alta','media','baixa')",
            name="ck_cosif_rule_confidence",
        ),
        Index(
            "ix_cosif_rule_busca", "silver_origin", "priority"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    silver_origin: Mapped[str] = mapped_column(String(50), nullable=False)
    predicate_jsonb: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    # NULL = regra que marca como pendente (ex.: contrapartida compensacao).
    cosif_codigo: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("cosif_catalog.codigo", ondelete="RESTRICT"),
        nullable=True,
    )
    classe_sr_mez_sub: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    # Maior priority = avaliada primeiro (regra mais especifica vence).
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'alta'")
    )
    rule_id_humano: Mapped[str] = mapped_column(String(80), nullable=False)
    valid_from: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    classifier_version: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'1.0.0'")
    )


class TenantPapelClassificacao(Base):
    """Override por tenant — editavel livremente via /admin/cosif.

    Identificador = chave estavel do admin (campo `codigo` do payload — ex.:
    'REALIAVE', 'BRADESCO', 'PDD'). Quando o classifier roda, override
    com mesmo (tenant_id, fundo_id, silver_origin, identificador) vence
    qualquer regra estrutural.
    """

    __tablename__ = "tenant_papel_classificacao"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "fundo_id",
            "silver_origin",
            "identificador",
            name="uq_tenant_papel_classificacao",
        ),
        Index(
            "ix_tenant_papel_classificacao_lookup",
            "tenant_id",
            "fundo_id",
            "silver_origin",
            "identificador",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    fundo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "cadastros_unidade_administrativa.id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    silver_origin: Mapped[str] = mapped_column(String(50), nullable=False)
    identificador: Mapped[str] = mapped_column(String(80), nullable=False)
    cosif_override: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("cosif_catalog.codigo", ondelete="RESTRICT"),
        nullable=False,
    )
    classe_sr_mez_sub: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
