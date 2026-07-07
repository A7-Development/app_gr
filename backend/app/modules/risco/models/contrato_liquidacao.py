"""ProdutoContratoLiquidacao: declared liquidation contract per product.

First primitive of the anti-fraud program (auto-liquidacao, memoria
project_fraude_autoliquidacao_cnab): for each product (wh_dim_produto sigla)
the curator DECLARES how liquidation is expected to happen. The signal
engine (F4) reads the ACTIVE (latest) version; observed behaviour diverging
from the declared contract is either a curation item or a fraud signal.

Versioning follows the premise_set pattern (CLAUDE.md 14.3): rows are
append-only, every edit inserts version+1 for the same (tenant, sigla).
The active contract is simply the highest version. A product WITHOUT any
row is "em aberto" (contract not yet defined — engine does not score it).

Three declared fields (decisao Ricardo 2026-07-07 — "risco estrutural" was
deliberately REMOVED, it is derived, not declared):
    - fluxo_esperado: how money is expected to arrive.
    - boleto: is a bank-registered boleto expected for titles of this product?
      Three states because of Intercompany ("permitido" = may happen, no alert).
    - baixa_manual: is a manual write-off normal operation or an anomaly?
"""

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class FluxoLiquidacao(enum.StrEnum):
    """Expected liquidation flow for a product."""

    BOLETO_BANCARIO = "boleto_bancario"
    DEPOSITO_EM_CONTA = "deposito_em_conta"
    LIQUIDACAO_INTERNA = "liquidacao_interna"


class ExpectativaBoleto(enum.StrEnum):
    """Is a bank-registered boleto expected for titles of this product?"""

    OBRIGATORIO = "obrigatorio"
    PERMITIDO = "permitido"
    NAO_ESPERADO = "nao_esperado"


class ExpectativaBaixaManual(enum.StrEnum):
    """Is a manual write-off (baixa manual) normal or anomalous here?"""

    NORMAL = "normal"
    ANOMALA = "anomala"


class ProdutoContratoLiquidacao(Base):
    """Versioned liquidation contract of one product (append-only)."""

    __tablename__ = "produto_contrato_liquidacao"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "produto_sigla",
            "version",
            name="uq_contrato_liquidacao_produto_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Natural key of the product (wh_dim_produto.sigla). Not a hard FK on
    # purpose: wh_dim_produto is a re-mappable silver table; the contract is
    # domain config and must survive an ETL rewrite.
    produto_sigla: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    fluxo_esperado: Mapped[FluxoLiquidacao] = mapped_column(
        SAEnum(FluxoLiquidacao, native_enum=False, length=32), nullable=False
    )
    boleto: Mapped[ExpectativaBoleto] = mapped_column(
        SAEnum(ExpectativaBoleto, native_enum=False, length=32), nullable=False
    )
    baixa_manual: Mapped[ExpectativaBaixaManual] = mapped_column(
        SAEnum(ExpectativaBaixaManual, native_enum=False, length=32), nullable=False
    )

    justificativa: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<ProdutoContratoLiquidacao {self.produto_sigla!r} v={self.version} "
            f"tenant={self.tenant_id}>"
        )
