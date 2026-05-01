"""wh_serasa_pj_socio -- QSA derivado de uma consulta Serasa PJ."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SerasaPjSocio(Auditable, Base):
    """Socio (PF/PJ) listado no QSA de uma consulta Serasa PJ.

    Granularidade: 1 linha por (consulta_id, documento). Snapshot da
    composicao societaria no momento da consulta.
    """

    __tablename__ = "wh_serasa_pj_socio"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_serasa_pj_socio"
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

    # CPF (11) ou CNPJ (14), so digitos.
    documento: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )
    documento_tipo: Mapped[str] = mapped_column(
        String(8), nullable=False
    )  # 'cpf' | 'cnpj' | 'unknown'

    nome: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualificacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    percentual: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 4), nullable=True
    )
    data_entrada: Mapped[date | None] = mapped_column(Date, nullable=True)
