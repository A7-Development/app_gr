"""wh_saldo_bancario_diario -- saldo de conta-corrente bancaria por dia.

Granularidade: 1 linha por (tenant, ua, agencia, conta, data_posicao).
Re-ingerir o mesmo dia/conta e idempotente via UQ (tenant_id, source_id) --
padrao do warehouse.

Fonte inicial: QiTech `/v2/bank-account/balance/{agencia}/{conta}/{data}`
(adapter `admin:qitech`, familia bank-account). CNPJ titular vem da UA dona
da credencial -- NAO se cadastra no payload, fica implicito via ua_id.

Diferenca vs `wh_saldo_conta_corrente`:
- `wh_saldo_conta_corrente` vem do relatorio agregado /netreport/.../conta-corrente/
  que QiTech entrega por carteira+banco em granularidade alta.
- `wh_saldo_bancario_diario` vem da chamada per-conta /bank-account/balance/
  que da o saldo *daquela conta-corrente especifica* da UA. Granularidade
  diferente, fonte diferente, uso diferente.

Quando o mapper enxergar payload real da QiTech, campos opcionais (banco_nome,
moeda, etc.) ganham populacao. Por enquanto aceitamos null pra nao bloquear
ingestao.
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


class SaldoBancarioDiario(Auditable, Base):
    """Saldo de fechamento de uma conta-corrente bancaria num dia."""

    __tablename__ = "wh_saldo_bancario_diario"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_saldo_bancario_diario"
        ),
        Index(
            "ix_wh_saldo_bancario_diario_tenant_data",
            "tenant_id",
            "data_posicao",
        ),
        Index(
            "ix_wh_saldo_bancario_diario_tenant_conta_data",
            "tenant_id",
            "agencia",
            "conta",
            "data_posicao",
        ),
        Index(
            "ix_wh_saldo_bancario_diario_tenant_ua_data",
            "tenant_id",
            "unidade_administrativa_id",
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
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
        ),
        nullable=True,
        index=True,
    )

    # -- Quando --
    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # -- Conta --
    agencia: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    conta: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Campos opcionais que aparecem quando o payload da QiTech inclui banco.
    # Ate o mapper observar payload real, ficam null sem bloquear ingestao.
    banco_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    banco_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    moeda: Mapped[str] = mapped_column(
        String(3), nullable=False, default="BRL", server_default=text("'BRL'")
    )

    # -- Fato --
    # Saldo pode ser negativo (cheque especial, conta-garantia em uso).
    saldo: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
