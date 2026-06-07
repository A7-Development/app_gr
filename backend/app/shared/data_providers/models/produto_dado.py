"""ProdutoDado — o "produto de dado" lógico (unidade de consumo).

Ver `docs/central-de-dados-arquitetura.md` §5. O Produto é o que o tenant/agente
PEDE ("Cadastro PJ" / public_code CAD-PJ), definido pelo que entrega — não por
qual vendor o cumpre. Carrega `public_code` (white-label) e é a âncora do
contrato. Um ou mais `ProdutoDadoOrigem` (datasets de origem físicos) o
alimentam — base do fallback multi-provedor.

Começa global (`tenant_id` NULL); override por tenant é futuro.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class ProdutoDado(Base):
    """Unidade lógica de consumo (white-label). Âncora do contrato + public_code."""

    __tablename__ = "produto_dado"
    __table_args__ = (
        UniqueConstraint("public_code", name="uq_produto_dado_public_code"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # Código neutro exposto ao tenant/agente (CAD-PJ). White-label.
    public_code: Mapped[str] = mapped_column(String(64), nullable=False)
    nome_pt_br: Mapped[str] = mapped_column(String(128), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Tabela silver canônica onde o dado deste produto materializa
    # (ex.: wh_pj_cadastro). NULL quando ainda não materializado (§5.1).
    silver_target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Global = NULL; override/custom por tenant é futuro (decisão 14.3).
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<ProdutoDado {self.public_code!r}>"


class ProdutoDadoOrigem(Base):
    """Um dataset de origem (físico) que cumpre um Produto de Dado.

    Identidade da origem = tupla do contrato (provider/api_endpoint/dataset_code),
    mesma chave de `dataset_contract`. `prioridade` ordena o roteamento/fallback
    (1 = origem primária).
    """

    __tablename__ = "produto_dado_origem"
    __table_args__ = (
        UniqueConstraint(
            "produto_id",
            "provider",
            "api_endpoint",
            "dataset_code",
            name="uq_produto_dado_origem",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    produto_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("produto_dado.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    api_endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(128), nullable=False)
    prioridade: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<ProdutoDadoOrigem produto={self.produto_id} "
            f"{self.provider}/{self.api_endpoint}/{self.dataset_code} "
            f"prio={self.prioridade}>"
        )
