"""wh_serasa_pj_participacao -- participacoes em outras empresas."""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
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


class SerasaPjParticipacao(Auditable, Base):
    """Participacao da empresa-alvo em outras empresas (grupo economico).

    Granularidade: 1 linha por (consulta_id, documento_empresa). Util pra
    analise de grupo economico — JOIN com `wh_serasa_pj_socio` permite
    encontrar conexoes indiretas (mesmo socio em multiplas empresas).
    """

    __tablename__ = "wh_serasa_pj_participacao"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_serasa_pj_participacao"
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

    # CNPJ (14 digitos) da empresa em que a target participa.
    documento_empresa: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )
    razao_social: Mapped[str | None] = mapped_column(Text, nullable=True)
    percentual: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 4), nullable=True
    )
    qualificacao: Mapped[str | None] = mapped_column(Text, nullable=True)
