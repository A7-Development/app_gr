"""wh_serasa_pj_inquiry_anterior -- consultas previas feitas no CNPJ."""

from datetime import date
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SerasaPjInquiryAnterior(Auditable, Base):
    """Consulta anterior feita no CNPJ (de `facts.inquiryCompanyResponse.results[]`).

    Lista as empresas que consultaram este CNPJ recentemente (com
    occurrenceDate e daysQuantity = quantos dias atras). Util pra
    detectar "shopping de credito" — quando a empresa-alvo busca
    credito em multiplas instituicoes.
    """

    __tablename__ = "wh_serasa_pj_inquiry_anterior"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_inquiry_anterior",
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
    consulta_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_serasa_pj_consulta.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    company_document_id: Mapped[str | None] = mapped_column(
        String(14), nullable=True, index=True
    )
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_alias: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurrence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    days_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Bloco bruto preservado pra futuras descobertas no payload.
    detalhe: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
