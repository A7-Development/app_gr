"""wh_mec_evolucao_cotas -- Mapa Evolutivo de Cotas (MEC).

Patrimonio + quantidade + cota + variacoes por classe de cota num data.
Granularidade: 1 linha por (tenant, data, clienteId/classe). UQ via
(tenant_id, source_id) onde source_id = `{clienteId}|{YYYY-MM-DD}`.

Fonte: QiTech `/v2/netreport/report/market/mec/{data}`.

Sample: 3 linhas (REALINVEST, REALINVEST MEZ, REALINVEST SEN — uma por
classe de cota).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class MecEvolucaoCotas(Auditable, Base):
    """Mapa Evolutivo de Cotas (MEC) -- 1 linha por classe de cota num dia."""

    __tablename__ = "wh_mec_evolucao_cotas"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_mec_evolucao_cotas"
        ),
        Index(
            "ix_wh_mec_evolucao_cotas_tenant_data",
            "tenant_id",
            "data_posicao",
        ),
        Index(
            "ix_wh_mec_evolucao_cotas_tenant_carteira",
            "tenant_id",
            "carteira_cliente_doc",
            "data_posicao",
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
    # UA dona da credencial que produziu esta linha (multi-UA, Phase F).
    # Nullable apenas para retrocompat com linhas legacy ingeridas antes
    # da introducao de multi-UA. Toda nova linha gravada pelo adapter
    # informa explicitamente.
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
        ),
        nullable=True,
        index=True,
    )

    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    carteira_cliente_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    carteira_cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    carteira_cliente_doc: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )

    # Fluxo
    entradas: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    saidas: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    aporte: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    retirada: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Posicao / cota
    patrimonio: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    valor_da_cota: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)

    # Variacoes (em %, 4 casas — observado max 4 no sample).
    variacao_diaria: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    variacao_mensal: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    variacao_anual: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    variacao_total: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
