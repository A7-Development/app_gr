"""FileLanding: registry (camada bronze, CLAUDE.md 13.2) da landing zone.

Uma linha por arquivo recebido pelo File Gateway — venha do Strata Collector
(servidor do cliente), de upload pela UI ou de API futura. O blob mora no
`StorageBackend` (`storage_key`); aqui fica o indice com proveniencia.

Imutavel apos gravacao (como toda raw): nao ha re-escrita semantica. A unica
mutacao permitida e o marcador operacional `consumed_at` (quando o ETL a
jusante ingeriu o arquivo) — estado de esteira, nao conteudo.

Nao usa mixin `Auditable` (excecao §14.1 para camada raw): a proveniencia
mora em colunas proprias (sha256, received_at, agent_credential_id,
agent_version).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class FileLanding(Base):
    __tablename__ = "file_landing"
    __table_args__ = (
        # Dedup por conteudo dentro do escopo (tenant, source_label): o mesmo
        # arquivo reenviado pelo agente (retry, re-scan) e no-op.
        UniqueConstraint(
            "tenant_id",
            "source_label",
            "sha256",
            name="uq_file_landing_tenant_source_sha",
        ),
        # Consulta tipica dos consumidores: pendentes de um source_label.
        Index(
            "ix_file_landing_tenant_source_received",
            "tenant_id",
            "source_label",
            "received_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cadastros_unidade_administrativa.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Rotulo da esteira de origem (ex.: "cobranca_cnab", "bitfin_xml_operacoes",
    # "credito_declaracao_faturamento"). Vocabulario vive na watch_config /
    # feature que ingere — adicionar esteira nova = label novo, nao tabela nova.
    source_label: Mapped[str] = mapped_column(String(64), nullable=False)

    nome_arquivo: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Key no StorageBackend: <tenant>/<ua|sem-ua>/<label>/<yyyy>/<mm>/<sha256>
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Quem entregou. NULL = upload de UI/API (usuario autenticado — trilha no
    # decision_log do batch). SET NULL preserva a linha se a credencial morrer.
    agent_credential_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_credential.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Marcador operacional: quando o consumidor (ETL cobranca, parser XML)
    # processou este arquivo. NULL = pendente.
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<FileLanding tenant={self.tenant_id} label={self.source_label} "
            f"arquivo={self.nome_arquivo!r}>"
        )
