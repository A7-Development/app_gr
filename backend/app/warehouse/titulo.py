"""wh_titulo — titulos individuais (atual + historico) com horizonte futuro.

Fonte: Bitfin `Titulo`.

Serve:
- L2 Fluxo de caixa (titulos com `DataDeVencimentoEfetiva > hoje` para projecao)
- Ficha (lista completa de titulos de um cedente/sacado)

Diferente de `wh_titulo_snapshot` (agregado diario): aqui cada row e UM titulo
(nao ha duplicacao por data_ref). Atualizado conforme Bitfin via ETL.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class Titulo(Auditable, Base):
    """Um titulo de recebivel (duplicata, cheque, nota, etc.)."""

    __tablename__ = "wh_titulo"
    __table_args__ = (UniqueConstraint("tenant_id", "source_id", name="uq_wh_titulo"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    titulo_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sigla: Mapped[str] = mapped_column(String(4), nullable=False)
    numero: Mapped[str] = mapped_column(String(50), nullable=False)

    # Temporal
    data_de_emissao: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_de_vencimento: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_de_vencimento_efetiva: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    data_de_cadastro: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_da_situacao: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_do_status: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Valores
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valor_do_pagamento: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    valor_liquido: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    saldo_devedor: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0, index=True
    )

    # Status / situacao
    situacao: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    meio: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # FKs (mantemos como int, referenciam Bitfin)
    sacado_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    conta_operacional_id: Mapped[int] = mapped_column(Integer, nullable=False)
    unidade_administrativa_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    operacao_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    subscricao_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retencao_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Protesto / negativacao
    data_permitida_para_protesto: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_da_solicitacao_do_protesto: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_do_envio_ao_cartorio: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_do_protesto: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_da_sustacao_do_protesto: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_do_cancelamento_do_protesto: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sustado_judicialmente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_permitida_para_negativacao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_da_negativacao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_do_cancelamento_da_negativacao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    codigo_de_registro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tags: Mapped[str | None] = mapped_column(String(1000), nullable=True)
