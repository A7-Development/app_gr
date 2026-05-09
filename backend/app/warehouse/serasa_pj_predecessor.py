"""wh_serasa_pj_predecessor -- sucessoes empresariais (predecessorList)."""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    ForeignKey,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SerasaPjPredecessor(Auditable, Base):
    """Sucessao empresarial — empresa anterior que foi sucedida pela target.

    Vem de `identificationReport.predecessorList[]`. Sinal forte pra
    credito: empresa que mudou de razao social ou CNPJ recentemente
    pode estar tentando "lavar" historico negativo.
    """

    __tablename__ = "wh_serasa_pj_predecessor"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_wh_serasa_pj_predecessor",
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

    predecessor_name: Mapped[str] = mapped_column(Text, nullable=False)
    predecessor_date: Mapped[date | None] = mapped_column(Date, nullable=True)
