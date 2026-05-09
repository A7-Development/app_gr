"""wh_serasa_pj_restricao -- restricoes derivadas de uma consulta Serasa PJ."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
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


class SerasaPjRestricao(Auditable, Base):
    """Restricao (REFIN, PEFIN, protesto, cheque) listada numa consulta.

    Tabela polimorfica via coluna `tipo`. Detalhes especificos do tipo
    (banco do cheque, cartorio do protesto, etc.) ficam em `detalhe`
    JSONB — a fonte da verdade continua sendo o raw em
    `wh_serasa_pj_raw_relatorio.payload`.
    """

    __tablename__ = "wh_serasa_pj_restricao"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_serasa_pj_restricao"
        ),
        # "Quantas consultas com PEFIN no tenant?" / time-series por tipo.
        Index(
            "ix_wh_serasa_pj_restricao_tenant_tipo",
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

    # 'refin' | 'pefin' | 'protesto' | 'cheque' | (futuros).
    tipo: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    valor: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    credor: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_ocorrencia: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_baixa: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Campos especificos por tipo que nao cabem em colunas tipadas
    # (ex.: cidade do protesto, banco do cheque, comarca). Nao e payload
    # bruto — e um subset derivado pelo mapper.
    detalhe: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
