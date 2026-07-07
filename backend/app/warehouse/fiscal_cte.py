"""CT-e coletado via landing zone fiscal (Strata Collector) -- raw + silver.

Mesma arquitetura de `fiscal_nfe.py` (bronze zip -> raw JSONB integral ->
silver curado). Decisao Ricardo 2026-07-07: CT-e consumido 100%.

`wh_cte_nfe` materializa o elo CT-e -> chaves das NF-e transportadas
(`infDoc/infNFe/chave`) -- prova de transporte/entrega do lastro.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.auditable import Auditable


class CteRawDocumento(Base):
    """XML do CT-e integral em JSONB canonico (1 linha por cteProc)."""

    __tablename__ = "wh_cte_raw_documento"
    __table_args__ = (
        UniqueConstraint("tenant_id", "chave_acesso", name="uq_wh_cte_raw_tenant_chave"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chave_acesso: Mapped[str] = mapped_column(String(44), nullable=False)
    schema_versao: Mapped[str | None] = mapped_column(String(8), nullable=True)
    documento: Mapped[dict] = mapped_column(JSONB, nullable=False)

    file_landing_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("file_landing.id", ondelete="SET NULL"),
        nullable=True,
    )
    nome_arquivo_xml: Mapped[str] = mapped_column(String(512), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fetched_by_version: Mapped[str] = mapped_column(String(32), nullable=False)


class Cte(Auditable, Base):
    """Silver curado do CT-e."""

    __tablename__ = "wh_cte"
    __table_args__ = (
        UniqueConstraint("tenant_id", "chave_acesso", name="uq_wh_cte_tenant_chave"),
        Index("ix_wh_cte_tenant_remetente", "tenant_id", "remetente_documento"),
        Index("ix_wh_cte_tenant_emissao", "tenant_id", "data_emissao"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_documento_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_cte_raw_documento.id", ondelete="RESTRICT"),
        nullable=False,
    )

    chave_acesso: Mapped[str] = mapped_column(String(44), nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    serie: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cfop: Mapped[str | None] = mapped_column(String(4), nullable=True)
    natureza_operacao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    data_emissao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tipo_cte: Mapped[str | None] = mapped_column(String(1), nullable=True)
    municipio_inicio: Mapped[str | None] = mapped_column(String(80), nullable=True)
    uf_inicio: Mapped[str | None] = mapped_column(String(2), nullable=True)
    municipio_fim: Mapped[str | None] = mapped_column(String(80), nullable=True)
    uf_fim: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Partes: emitente = transportadora
    emitente_documento: Mapped[str] = mapped_column(String(14), nullable=False)
    emitente_nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    remetente_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    remetente_nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    destinatario_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    destinatario_nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expedidor_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    recebedor_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    # toma: 0=rem 1=exped 2=receb 3=dest 4=outros
    tomador_codigo: Mapped[str | None] = mapped_column(String(1), nullable=True)

    valor_prestacao: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_receber: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_carga: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    produto_predominante: Mapped[str | None] = mapped_column(String(120), nullable=True)

    cstat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    autorizada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    protocolo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_autorizacao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CteNfe(Base):
    """Elo CT-e -> NF-e transportada (infDoc/infNFe/chave)."""

    __tablename__ = "wh_cte_nfe"
    __table_args__ = (
        UniqueConstraint("cte_id", "chave_nfe", name="uq_wh_cte_nfe_cte_chave"),
        Index("ix_wh_cte_nfe_tenant_chave_nfe", "tenant_id", "chave_nfe"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cte_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_cte.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chave_nfe: Mapped[str] = mapped_column(String(44), nullable=False)
