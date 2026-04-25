"""wh_saldo_conta_corrente -- saldo bancario / conta corrente por instituicao.

Granularidade: 1 linha por (tenant_id, data_posicao, carteira_cliente_id,
codigo_conta). Re-ingerir o mesmo dia e idempotente via unique
(tenant_id, source_id) -- padrao do warehouse.

Fonte inicial: QiTech `/v2/netreport/report/market/conta-corrente/{data}`
(adapter `admin:qitech`). Modelo projetado pra aceitar outras fontes
equivalentes (outros admins) no futuro sem refactor.

Dimensoes:
- **Carteira**: `carteira_cliente_id` + `carteira_cliente_nome` +
  `carteira_cliente_doc` (CNPJ).
- **Conta**: `codigo` (chave do banco/conta na QiTech, ex.: "BRADESCO",
  "SOCOPA", "CONCILIA"), `descricao`, `instituicao`.
- **Quando**: `data_posicao`.

Fatos:
- `valor_total`: saldo do dia. Pode ser negativo (sobrescritos a conciliar).
- `percentual_sobre_conta_corrente` / `percentual_sobre_total`: composicao.

Ver `docs/integracao-qitech.md`.
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


class SaldoContaCorrente(Auditable, Base):
    """Saldo de conta corrente / cash position numa data."""

    __tablename__ = "wh_saldo_conta_corrente"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_saldo_conta_corrente"
        ),
        Index(
            "ix_wh_saldo_conta_corrente_tenant_data",
            "tenant_id",
            "data_posicao",
        ),
        Index(
            "ix_wh_saldo_conta_corrente_tenant_carteira",
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

    # -- Quando --
    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # -- Carteira --
    carteira_cliente_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    carteira_cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    carteira_cliente_doc: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )

    # -- Conta --
    # `codigo` na QiTech vai de literal banco ("BRADESCO") ate codigo interno
    # ("CONCILIA", "SOCOPA"). Mantem string.
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    instituicao: Mapped[str] = mapped_column(String(100), nullable=False)

    # -- Fatos --
    # Saldo pode ser negativo (creditos a conciliar, sobrescritos contabeis).
    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Percentuais sempre em % (175.64 = 175.64%). Pode passar de 100 quando
    # tem alavancagem ou ajuste contabil — nao clampar.
    percentual_sobre_conta_corrente: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
    percentual_sobre_total: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
