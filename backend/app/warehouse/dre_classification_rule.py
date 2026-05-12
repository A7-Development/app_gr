"""wh_dre_classification_rule -- regra de classificacao DRE (silver, agnostica).

Substitui o lookup que vivia em `ANALYTICS.dbo.DREClassificacao` (banco
A7-especifico em cima do MSSQL Bitfin). Agora a regra mora no nosso gr_db,
versionada e com override por tenant — alinhado com CLAUDE.md secao 13
(adapter pattern, dado canonico) e secao 14.3 (versionamento de regras).

Modelo de uso (cascata):

    1. Mapper bronze -> silver passa (tenant_id, fonte, categoria) ao classifier.
    2. Classifier procura:
       (a) regra com tenant_id = :tenant e valid_until IS NULL  -> match? usa.
       (b) regra com tenant_id IS NULL e valid_until IS NULL    -> match? usa.
       (c) nenhuma das duas -> retorna None (silver descarta a linha).

`fonte` espelha o vocabulario do Bitfin (`DRE_OPERACIONAL`, `CONTAS_A_PAGAR`,
`COMISSAO`) por enquanto. Quando outro adapter (ex.: QiTech FIDC) precisar
classificar DRE, ele passa o proprio `fonte` (ex.: `QITECH_RELATORIO`) e
cria suas regras — o classifier nao muda.

`version` carrega versionamento da regra (CLAUDE.md secao 14.3). Mappers
podem pinar `classify(..., version=N)` quando precisarem rodar replay com
uma versao anterior do conjunto de regras.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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


class WhDreClassificationRule(Base):
    """Regra (Fonte, Categoria) -> (GrupoDRE, SubGrupo, OrdemGrupo, Ativo).

    Linha com `tenant_id IS NULL` = regra GLOBAL aplicavel a qualquer tenant.
    Linha com `tenant_id = X` = override para o tenant X (vence sobre global).

    Soft-delete via `valid_until`: regra ativa quando `valid_until IS NULL`.
    Edit-in-place quebra audit trail; sempre `UPDATE ... SET valid_until = today`
    + INSERT da nova versao.
    """

    __tablename__ = "wh_dre_classification_rule"
    __table_args__ = (
        # Lookup canonico do classifier: por (fonte, categoria) com filtro
        # tenant_id IN (:t, NULL). Cobre as 3 fontes do Bitfin hoje.
        Index(
            "ix_wh_dre_classification_rule_lookup",
            "fonte",
            "categoria",
            "tenant_id",
            postgresql_where="valid_until IS NULL",
        ),
        # Garante 1 regra ATIVA por (tenant_id, fonte, categoria). Partial
        # unique index com NULLS NOT DISTINCT trata tenant_id NULL como
        # comparavel a outro NULL (Postgres 15+).
        Index(
            "uq_wh_dre_classification_rule_active",
            "tenant_id",
            "fonte",
            "categoria",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where="valid_until IS NULL",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # NULL = regra global aplicavel a qualquer tenant. NOT NULL = override
    # so vale para o tenant referenciado.
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Versao da regra (CLAUDE.md secao 14.3). Default 1; bump explicito
    # quando o conjunto de regras evolui. Versoes coexistem para replay.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Chave da regra. `fonte` espelha o discriminator que o mapper passa
    # (hoje os 3 do Bitfin; futuro: outros adapters trazem seu proprio).
    fonte: Mapped[str] = mapped_column(String(50), nullable=False)
    categoria: Mapped[str] = mapped_column(String(200), nullable=False)

    # Output da classificacao.
    grupo_dre: Mapped[str] = mapped_column(String(50), nullable=False)
    subgrupo: Mapped[str] = mapped_column(String(100), nullable=False)
    ordem_grupo: Mapped[int] = mapped_column(Integer, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Validade temporal. Soft-delete via `valid_until`.
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Audit.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
