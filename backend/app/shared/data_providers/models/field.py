"""DatasetField — um campo do Contrato de Dados (com roteamento p/ 5 superfícies).

Ver `docs/contratos-de-dados-fontes-externas.md` (seção 7.2). Cada registro
descreve UM campo do dataset e decide o destino dele:

    to_silver  → promove a coluna canônica? (silver_target = nome da coluna)
    on_screen  → exibe na tela? (screen_order)
    to_tool    → entra no output da read-tool?
    to_agent   → entra no contexto do agente? (default = to_tool)
    to_check   → usado por check determinístico? (IMPLICA to_silver)

`field_path` (convenção 7.4): ponto p/ objeto aninhado (`LegalNature.Activity`),
`[]` p/ array (`Activities[].Code`).

Valores de string controlados (sem SAEnum):
    semantic_type: text | number | date | bool | money | cnpj | cnae | enum | object | array
    sensibilidade: publico | interno | pii
    eh_fato:       fato_deterministico | contexto
    status:        curado | novo_nao_classificado
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


class DatasetField(Base):
    """Um campo do contrato + seu roteamento para as superfícies."""

    __tablename__ = "dataset_field"
    __table_args__ = (
        UniqueConstraint(
            "contract_id", "field_path", name="uq_dataset_field_path"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    contract_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dataset_contract.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    field_path: Mapped[str] = mapped_column(String(255), nullable=False)

    # ─── Camada semântica: liga o campo ao termo canônico (glossário) ────────
    # Ver central-de-dados-arquitetura.md §4. NULL = ainda não mapeado.
    termo_canonico_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("termo_canonico.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ─── Metadado (curado pelo usuário) ──────────────────────────────────────
    public_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default="text", server_default="text"
    )
    categoria_ui: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sensibilidade: Mapped[str] = mapped_column(
        String(16), nullable=False, default="publico", server_default="publico"
    )
    eh_fato: Mapped[str] = mapped_column(
        String(24), nullable=False, default="contexto", server_default="contexto"
    )

    # ─── Roteamento para as 5 superfícies ────────────────────────────────────
    to_silver: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    silver_target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    on_screen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    screen_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_tool: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    to_agent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    to_check: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # ─── Governança / curadoria ──────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="curado", server_default="curado"
    )
    classified_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    classified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<DatasetField {self.field_path!r} contract={self.contract_id}>"
