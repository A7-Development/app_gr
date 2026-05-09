"""DataProviderCredential: credenciais globais cifradas para um provider.

Tabela `provedor_dados_credencial`. Mesmo padrao de `ai_provider_credential`:
sem `tenant_id`, JSONB cifrado via envelope (`app.shared.crypto.envelope`),
multipla credencial por provider permitida (rotacao zero-downtime).

Formato do `encrypted_payload` plaintext (apos decrypt):
    BigDataCorp:
        {"access_token": "...", "token_id": "..."}
    Infosimples:
        {"api_key": "..."}

O adapter de cada vendor sabe interpretar seu formato — esta tabela so
armazena o JSONB opaco.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DataProviderCredential(Base):
    """Credencial global cifrada para um vendor de dados."""

    __tablename__ = "provedor_dados_credencial"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    provider_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provedor_dados.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Rotulo livre pra distinguir credenciais (ex.: "bigdatacorp_prod_2026",
    # "bigdatacorp_uat"). Unique global porque o mantenedor le a lista plana.
    alias: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # Envelope-encrypted JSON dict — formato vendor-specific. Ver docstring.
    encrypted_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # ZDR (Zero Data Retention): true => provider contratualmente nao retem
    # dados das consultas. Reservado para futura check em ambiente prod
    # (paralelo ao ai_provider_credential.zdr_enabled).
    zdr_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )

    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rotated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

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
            f"<DataProviderCredential id={self.id} provider_id={self.provider_id} "
            f"alias={self.alias!r} active={self.active}>"
        )
