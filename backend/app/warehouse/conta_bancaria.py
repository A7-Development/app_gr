"""Registered bank accounts per entity (wh_conta_bancaria).

Cadastral mirror of Bitfin `ContaBancaria` (+ `Banco` / `BancoAgencia`
lookups): in which bank/branch each entity (cedente, sacado, fundo) holds
its registered accounts — including the account where the fund settles the
cedente's operations.

Primary consumer: the S1 "praca do cedente" feature of the liquidation
detection model (memoria project_deteccao_anomalias_liquidacao) — a boleto
paid at a branch where the CEDENTE banks is the strongest self-liquidation
signal. Matching keys against CNAB praca (F1): `banco_codigo` is the COMPE
code (same code space as wh_boleto_evento.banco_pagador) and
`agencia_codigo` matches agencia_pagadora (compare zero-padded).
"""

from decimal import Decimal  # noqa: F401  (kept for parity with sibling models)
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class ContaBancariaEntidade(Auditable, Base):
    """One registered bank account of one entity (source_id = ContaBancariaId)."""

    __tablename__ = "wh_conta_bancaria"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_conta_bancaria"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Bitfin EntidadeId + normalized document (join key against wh_operacao
    # cedente_documento / wh_entidade documento; grupo via documento raiz).
    entidade_source_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    entidade_documento: Mapped[str | None] = mapped_column(
        String(14), nullable=True, index=True
    )

    banco_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # COMPE code as the ERP registers it (matches CNAB banco_pagador).
    banco_codigo: Mapped[str | None] = mapped_column(String(3), nullable=True, index=True)
    banco_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    banco_digital: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    agencia_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    agencia_digito: Mapped[str | None] = mapped_column(String(2), nullable=True)
    agencia_localidade: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agencia_estado: Mapped[str | None] = mapped_column(String(2), nullable=True)

    numero_conta: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tipo_conta: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ativa: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    escrow: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    suporte_para_depositos: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ContaBancariaEntidade doc={self.entidade_documento} "
            f"banco={self.banco_codigo} ag={self.agencia_codigo}>"
        )
