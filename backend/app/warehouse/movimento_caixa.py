"""wh_movimento_caixa -- demonstrativo de caixa (entradas/saidas/saldo).

Granularidade: 1 linha por (tenant, dataLiquidacao, hash do conteudo do
movimento). QiTech NAO devolve id estavel — pode ter dois lancamentos com
mesma descricao no mesmo dia (ex.: 2 resgates de mesmo fundo). Por isso
`source_id` inclui sha16 do item completo: garante unicidade. Trade-off:
se a QiTech corrigir um typo numa descricao, vira linha nova em vez de
update (aceitavel pra MVP — documentado no plano).

Fonte: QiTech `/v2/netreport/report/market/demonstrativo-caixa/{data}`.
"""

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
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class MovimentoCaixa(Auditable, Base):
    """Movimento de caixa (entrada/saida/saldo) num dia."""

    __tablename__ = "wh_movimento_caixa"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_movimento_caixa"),
        Index(
            "ix_wh_movimento_caixa_tenant_data",
            "tenant_id",
            "data_liquidacao",
        ),
        Index(
            "ix_wh_movimento_caixa_tenant_carteira",
            "tenant_id",
            "carteira_cliente_doc",
            "data_liquidacao",
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

    # `data_liquidacao` vem do `dataLiquidação` da QiTech. Pode diferir do
    # dia da fetch (ex.: pre-aviso de movimento futuro).
    data_liquidacao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    carteira_cliente_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    carteira_cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    carteira_cliente_doc: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )

    # Tipo de registro QiTech: 1=movimento, 2=saldo de fechamento, ...
    tipo_de_registro: Mapped[int] = mapped_column(Integer, nullable=False)
    # Descricao pode ser longa ("Aplicação no Fundo X [Y] a pagar em DD/MM/YYYY").
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    historico_traduzido: Mapped[str] = mapped_column(Text, nullable=False)

    # Dados bancarios (geralmente null em demonstrativo de caixa do FIDC).
    banco: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agencia: Mapped[str | None] = mapped_column(String(20), nullable=True)
    conta_corrente: Mapped[str | None] = mapped_column(String(30), nullable=True)
    digito: Mapped[str | None] = mapped_column(String(5), nullable=True)
    id_conta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conta_investimento: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Fluxo. Saidas vem negativas da QiTech.
    entradas: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    saidas: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    saldo: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
