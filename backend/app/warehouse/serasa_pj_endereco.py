"""wh_serasa_pj_endereco -- enderecos derivados de uma consulta Serasa PJ."""

from uuid import UUID, uuid4

from sqlalchemy import (
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SerasaPjEndereco(Auditable, Base):
    """Endereco listado numa consulta Serasa PJ."""

    __tablename__ = "wh_serasa_pj_endereco"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_serasa_pj_endereco"
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

    # 'comercial', 'residencial', 'fiscal', etc — texto livre da Serasa.
    tipo: Mapped[str | None] = mapped_column(String(32), nullable=True)
    logradouro: Mapped[str | None] = mapped_column(Text, nullable=True)
    numero: Mapped[str | None] = mapped_column(String(16), nullable=True)
    complemento: Mapped[str | None] = mapped_column(Text, nullable=True)
    bairro: Mapped[str | None] = mapped_column(Text, nullable=True)
    cidade: Mapped[str | None] = mapped_column(Text, nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)
