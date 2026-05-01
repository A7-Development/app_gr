"""wh_serasa_pj_inquiry_mensal -- agregado mensal de consultas (13 meses)."""

from uuid import UUID, uuid4

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SerasaPjInquiryMensal(Auditable, Base):
    """Quantidade de consultas mes a mes (de `quantity.historical[]`).

    Cada linha = 1 mes de referencia. Serasa tipicamente devolve 13
    meses (mes corrente + 12 anteriores). Util pra grafico de
    tendencia de "credit shopping" — picos de consultas em meses
    recentes podem indicar busca ativa de credito.
    """

    __tablename__ = "wh_serasa_pj_inquiry_mensal"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_inquiry_mensal",
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

    # Mes de referencia "YYYY-MM" (ex.: "2026-04").
    inquiry_year_month: Mapped[str] = mapped_column(
        String(7), nullable=False
    )
    occurrences: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
