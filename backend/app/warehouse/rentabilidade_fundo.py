"""wh_rentabilidade_fundo -- metricas de rentabilidade por classe de cota.

Granularidade: 1 linha por (tenant, data, classe_de_cota, indexador).
27 linhas no sample REALINVEST = 3 classes x 9 indexadores
(PATRIMON, COTA, CDI, SEL, DOL, IBOV FEC, IGPM, Ctbrpfee, Qtd Cota, Vlr Cota).

`indexador` mantido como String(20) — nao enum, absorve novos indexadores
sem migration.

Fonte: QiTech `/v2/netreport/report/market/rentabilidade/{data}`.
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


class RentabilidadeFundo(Auditable, Base):
    """Metrica de rentabilidade do FIDC por classe de cota e indexador."""

    __tablename__ = "wh_rentabilidade_fundo"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_rentabilidade_fundo"
        ),
        Index(
            "ix_wh_rentabilidade_fundo_tenant_data",
            "tenant_id",
            "data_posicao",
        ),
        Index(
            "ix_wh_rentabilidade_fundo_tenant_carteira",
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

    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    carteira_cliente_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    carteira_cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    carteira_cliente_doc: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )

    indexador: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Todas as metricas Numeric(12,8) -- preserva 7 casas (observado max
    # 7 nas % bench) + 1 de margem. Nullable porque QiTech mistura: nem
    # todo indexador tem todas as metricas (PATRIMON so tem patrimonio,
    # COTA so tem rentabilidades).
    percentual_bench_mark: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), nullable=True
    )
    rentabilidade_real: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), nullable=True
    )
    rentabilidade_diaria: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), nullable=True
    )
    rentabilidade_mensal: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), nullable=True
    )
    rentabilidade_anual: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), nullable=True
    )
    rentabilidade_6_meses: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), nullable=True
    )
    rentabilidade_12_meses: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), nullable=True
    )

    valor_patrimonio: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    codigo_isin: Mapped[str | None] = mapped_column(String(20), nullable=True)

    percentual_6_meses: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), nullable=True
    )
    percentual_12_meses: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), nullable=True
    )
