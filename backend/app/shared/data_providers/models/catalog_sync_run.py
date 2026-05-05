"""DataProviderCatalogSyncRun: log de cada execucao de sync de catalogo.

Tabela `provedor_dados_sync_run`. Registra cada chamada do
`pricing_sync.py::sync_catalog` para um provider — sucesso ou falha.

Diferente do `decision_log` (que e per-tenant): catalog sync e A7-global,
nao tem `tenant_id`. E observabilidade interna do mantenedor — UI de
`/admin/servicos-externos/provedores-dados/[provider]/sync` consome esta
tabela para mostrar historico e diff.

Vincula com `provedor_dados_dataset_preco_historico.sync_run_id` (price
history grava qual run detectou cada mudanca).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.data_providers.enums import CatalogSyncStatus


class DataProviderCatalogSyncRun(Base):
    """Uma execucao do sync de catalogo de um provider."""

    __tablename__ = "provedor_dados_sync_run"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    provider_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provedor_dados.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Versao do adapter que rodou — registra evolucao do parser. Ex.:
    # "bigdatacorp_adapter_v1.0.0".
    adapter_version: Mapped[str] = mapped_column(String(64), nullable=False)

    # Quem disparou: "scheduler" (cron diario) | "manual" (script CLI ou
    # botao na UI futura). Texto livre — nao constraint.
    triggered_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="manual", server_default="manual"
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[CatalogSyncStatus] = mapped_column(
        SAEnum(
            CatalogSyncStatus,
            name="catalog_sync_status",
            native_enum=False,
            length=16,
        ),
        nullable=False,
        default=CatalogSyncStatus.IN_PROGRESS,
        server_default=CatalogSyncStatus.IN_PROGRESS.value,
        index=True,
    )

    # Contadores agregados — preenchidos no final. NULL durante run.
    datasets_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    datasets_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    datasets_unchanged: Mapped[int | None] = mapped_column(Integer, nullable=True)
    datasets_removed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ID da credencial usada — fica em metadado para auditoria de "quem
    # autenticou esta consulta". NULL se a credencial foi deletada
    # posteriormente (SET NULL).
    credential_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provedor_dados_credencial.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CatalogSyncRun id={self.id} provider_id={self.provider_id} "
            f"status={self.status.value} "
            f"added={self.datasets_added} updated={self.datasets_updated}>"
        )
