"""Contrato de Dados (Data Contract) — governança de campos por dataset.

Ver `docs/contratos-de-dados-fontes-externas.md`. Hierarquia:

    Provedor → API/Endpoint → Dataset → Campo

O **contrato é por dataset** (provider + api_endpoint + dataset_code). Carrega
os campos (`DatasetField`) com o roteamento para as 5 superfícies (silver / tela
/ tool / agente / check). É a fonte ÚNICA da verdade — dev constrói o mecanismo
que lê o contrato; o usuário é dono da política.

Versionamento IMUTÁVEL + ponteiro ativo (espelha `ai_prompt` / `ai_prompt_active`):
toda edição cria nova versão; `DatasetContractActive` aponta a versão em produção
(rollback de 1 clique). Começa GLOBAL (tenant_id NULL); override por tenant é
evolução futura.

Tabela NOVA e genérica (decisão 2026-06-06) — vale pra qualquer fonte
(BDC/QiTech/Bitfin/Serasa). O catálogo white-label `provedor_dados_dataset`
apenas linka via `public_code`.

Valores de string controlados (sem SAEnum — evita gotcha de name/value):
    status:        draft | active | archived
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DatasetContract(Base):
    """Cabeçalho do contrato — 1 por (provider, api_endpoint, dataset_code, version)."""

    __tablename__ = "dataset_contract"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "api_endpoint",
            "dataset_code",
            "version",
            name="uq_dataset_contract_identity_version",
        ),
        Index(
            "ix_dataset_contract_identity",
            "provider",
            "api_endpoint",
            "dataset_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # ─── Identidade (hierarquia Provedor → API → Dataset) ────────────────────
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    api_endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(128), nullable=False)
    # White-label tenant-facing (quando aplicável). Vendor nunca vaza.
    public_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Começa sempre global (NULL). Override por tenant é evolução futura.
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<DatasetContract {self.provider}/{self.api_endpoint}/"
            f"{self.dataset_code} v{self.version} ({self.status})>"
        )


class DatasetContractActive(Base):
    """Ponteiro da versão ATIVA — 1 por (provider, api_endpoint, dataset_code, tenant)."""

    __tablename__ = "dataset_contract_active"
    __table_args__ = (
        # Global (tenant_id NULL): unicidade via índice parcial (NULLs do PG
        # não colidem em UNIQUE comum).
        Index(
            "uq_dataset_contract_active_global",
            "provider",
            "api_endpoint",
            "dataset_code",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
        Index(
            "uq_dataset_contract_active_tenant",
            "provider",
            "api_endpoint",
            "dataset_code",
            "tenant_id",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    api_endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    active_contract_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dataset_contract.id", ondelete="CASCADE"),
        nullable=False,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<DatasetContractActive {self.provider}/{self.api_endpoint}/"
            f"{self.dataset_code} -> {self.active_contract_id}>"
        )
