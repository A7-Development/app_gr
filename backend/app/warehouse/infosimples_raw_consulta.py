"""Bronze das consultas on-demand à Infosimples (wh_infosimples_raw_consulta).

Espelha `wh_bdc_raw_consulta` (§13.2): payload de RESPONSE cru e imutável,
proveniência em colunas próprias (fetched_at, fetched_by_version, sha256).

ATENÇÃO PII: o REQUEST carrega logins de portal (JUCESP) — por isso o bronze
guarda apenas o RESPONSE + identificadores da consulta (documento, path).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InfosimplesRawConsulta(Base):
    """Payload cru de uma consulta on-demand à Infosimples."""

    __tablename__ = "wh_infosimples_raw_consulta"
    __table_args__ = (
        # "Última consulta do documento X no tenant Y" — cache de janela e
        # re-mapeamento sobre raw.
        Index(
            "ix_wh_infosimples_raw_tenant_doc_fetched",
            "tenant_id",
            "documento",
            text("fetched_at DESC"),
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
        index=True,
    )

    # Identificador principal da consulta (dígitos): CNPJ ou NIRE.
    documento: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Código NEUTRO (white-label) pedido pelo caller — ex.: "JUNTA-SP-FICHA".
    public_code: Mapped[str] = mapped_column(String(64), nullable=False)
    # Path técnico da consulta no vendor — ex.: "junta-comercial/sp/completa".
    consulta_path: Mapped[str] = mapped_column(String(128), nullable=False)

    # `code` aplicacional da Infosimples (200=ok; 6xx falha de consulta).
    api_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    found: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # RESPONSE cru (imutável após INSERT). Nunca o request (PII de login).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )

    latency_ms: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 1), nullable=True
    )

    # Quem disparou — `dossie:<id>`, `user:<id>`, `system:<job>`.
    triggered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    fetched_by_version: Mapped[str] = mapped_column(String(128), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<InfosimplesRawConsulta documento={self.documento} "
            f"public_code={self.public_code!r} found={self.found}>"
        )
