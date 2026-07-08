"""Bank branch registry mirrored from the ERP (wh_banco_agencia).

Second rung of the agency-resolution ladder (decisao Ricardo 2026-07-08):
    1st  ref_bacen_agencia   (public Olinda snapshot — CURRENT positions only)
    2nd  wh_banco_agencia    (this mirror: 24.660 branches the ERP knows,
                              including EXTINCT/renumbered ones the Bacen
                              snapshot lost — e.g. Bradesco 1417/Penha-RJ)
    3rd  nao_resolvida       (explicit state, never silently guessed)

The mirror keeps EVERY source row (source_id = AgenciaId); duplicates per
(banco, agencia) are resolved at LOOKUP time by the ladder (rows with a city
win). Provenance of a resolution is exposed as `praca_fonte` — both in the
calculation memory and as a model feature.
"""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class WhBancoAgencia(Auditable, Base):
    """One ERP-registered bank branch (source_id = Bitfin AgenciaId)."""

    __tablename__ = "wh_banco_agencia"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_banco_agencia"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    agencia_source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # COMPE (mesmo espaco de codigo do CNAB banco_pagador).
    banco_codigo: Mapped[str | None] = mapped_column(String(3), nullable=True, index=True)
    banco_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agencia_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    agencia_digito: Mapped[str | None] = mapped_column(String(2), nullable=True)
    localidade: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estado: Mapped[str | None] = mapped_column(String(2), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(9), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<WhBancoAgencia {self.banco_codigo}/{self.agencia_codigo} "
            f"{self.localidade}/{self.estado}>"
        )
