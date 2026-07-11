"""wh_titulo_fiscal — ponte titulo <-> NF-e (lastro fiscal do titulo).

Fonte: Bitfin `TituloFiscal` (join com `DocumentoFiscalNFe` para resolver
a chave de acesso de 44 digitos). 1 linha por associacao titulo<->nota;
um titulo pode ter N notas e uma nota pode lastrear N titulos.

Consumo principal: o monitoramento SERPRO (F3) — a regra de escopo e
"titulo EM ABERTO (wh_titulo.situacao=0) => vigia a chave da nota"
(decisao Ricardo 2026-07-11; vencimento NAO importa, titulo vencido em
aberto continua vigiado).
"""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class WhTituloFiscal(Auditable, Base):
    """Associacao titulo <-> NF-e (chave de acesso)."""

    __tablename__ = "wh_titulo_fiscal"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_titulo_fiscal"),
        Index("ix_wh_titulo_fiscal_tenant_titulo", "tenant_id", "titulo_id"),
        Index("ix_wh_titulo_fiscal_tenant_chave", "tenant_id", "chave_acesso"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Ids nativos do Bitfin (mesmo espaco de wh_titulo.titulo_id).
    titulo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nota_fiscal_eletronica_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chave_acesso: Mapped[str] = mapped_column(String(44), nullable=False)
    valor_associado: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
