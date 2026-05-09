"""DataProvider: entidade global de um vendor revendido pela A7.

Tabela `provedor_dados`. Uma linha por vendor (BigDataCorp, Infosimples).
Sem `tenant_id` — e catalogo do produto A7, compartilhado entre todos os
tenants que assinarem.

Distincao com SourceCatalog (em `app.shared.catalog`):
    SourceCatalog descreve fontes de dado *per-tenant* (Bitfin, QiTech, Serasa)
    onde cada tenant tem credencial propria. provedor_dados descreve servicos
    *globais* providos pela A7.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.data_providers.enums import DataProviderSlug


class DataProvider(Base):
    """Vendor global de dados externos."""

    __tablename__ = "provedor_dados"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_provedor_dados_slug"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    slug: Mapped[DataProviderSlug] = mapped_column(
        SAEnum(
            DataProviderSlug,
            name="data_provider_slug",
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    default_timeout_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30_000, server_default="30000"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Switch mestre A7 — desligado pausa todos os syncs e recusa consultas
    # de dominio mesmo que o tenant tenha subscription ativa. Util pra reagir
    # rapido a incidente do vendor sem depender de gerenciar N subscriptions.
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<DataProvider id={self.id} slug={self.slug.value} "
            f"name={self.name!r} enabled={self.enabled}>"
        )
