"""wh_serasa_pj_restricao_summary -- agregado por categoria de restricao."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SerasaPjRestricaoSummary(Auditable, Base):
    """Sumario agregado por categoria de restricao numa consulta.

    Granularidade: 1 linha por (consulta_id, tipo). Categorias possiveis:
    pefin, refin, protesto, cheque, collection.

    Vem de `negativeData.<categoria>.summary` no payload Serasa. Existe
    pra suportar dashboards/queries de risco que querem totais
    agregados sem JOIN nas filhas individuais.
    """

    __tablename__ = "wh_serasa_pj_restricao_summary"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_restricao_summary",
        ),
        Index(
            "ix_wh_serasa_pj_restricao_summary_tenant_tipo",
            "tenant_id",
            "tipo",
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

    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    balance: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    first_occurrence: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    last_occurrence: Mapped[date | None] = mapped_column(Date, nullable=True)
