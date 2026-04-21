"""wh_dre_mensal — DRE consolidada mensal.

Fonte: `ANALYTICS.vw_DRE` (ja processa e consolida automaticamente).

Serve:
- L2 DRE (visualizacao direta)
- Eventualmente cross-check com receitas realizadas de outros fatos.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
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


class DreMensal(Auditable, Base):
    """Uma linha da DRE mensal (por grupo/subgrupo/descricao/fornecedor)."""

    __tablename__ = "wh_dre_mensal"
    __table_args__ = (
        # Semantica: linha unica por tenant + competencia + hierarquia + dimensoes-chave.
        # Problema: entidade_id/produto_id sao nullable e NULL != NULL em uq — por isso o ETL
        # monta um source_id sintetico com todos os campos e usa uq_wh_dre_mensal_source.
        UniqueConstraint(
            "tenant_id",
            "competencia",
            "grupo_dre",
            "subgrupo",
            "descricao",
            "entidade_id",
            "produto_id",
            "fonte",
            name="uq_wh_dre_mensal",
        ),
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_dre_mensal_source"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Temporal
    ano: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Hierarquia DRE
    ordem_grupo: Mapped[int] = mapped_column(Integer, nullable=False)
    grupo_dre: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subgrupo: Mapped[str] = mapped_column(String(100), nullable=False)
    descricao: Mapped[str] = mapped_column(String(250), nullable=False)

    # Dimensoes
    fornecedor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fornecedor_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
    entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    produto_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unidade_administrativa_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fonte: Mapped[str] = mapped_column(String(30), nullable=False)

    # Medidas
    receita: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    custo: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    resultado: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
