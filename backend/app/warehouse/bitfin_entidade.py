"""wh_bitfin_entidade -- dim de entidades (cedentes) do Bitfin.

Resolve `entidade_id -> nome/documento` para os agregados do DRE (a coluna
`entidade_id` do silver `wh_dre_mensal` e o cedente da operacao). A tabela
`Entidade` do Bitfin tem ~20k linhas (cedentes, sacados, fornecedores...),
mas so as que aparecem no DRE (~90) interessam aqui -- o sync ingere o
subconjunto referenciado pelo DemonstrativoDeResultado.

Per-tenant. Proveniencia em colunas proprias (camada de referencia
ingerida, sem Auditable).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WhBitfinEntidade(Base):
    """Entidade Bitfin (cedente no contexto do DRE), por tenant."""

    __tablename__ = "wh_bitfin_entidade"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "entidade_id", name="uq_wh_bitfin_entidade"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # EntidadeId do Bitfin (chave de negocio; casa com wh_dre_mensal.entidade_id).
    entidade_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    documento: Mapped[str | None] = mapped_column(String(20), nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_by_version: Mapped[str] = mapped_column(String(30), nullable=False)
