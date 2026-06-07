"""TermoCanonico — glossário de termos canônicos (camada semântica).

Ver `docs/central-de-dados-arquitetura.md` §4. Um termo é um conceito de
negócio **vendor-agnóstico** (CNPJ, Razão Social, Faturamento, Score). Cada
`DatasetField` de cada provedor aponta para um termo via `termo_canonico_id` —
é o que faz "CNPJ é CNPJ venha de onde vier" e deixa o agente raciocinar em
conceitos canônicos, não em campos do vendor.

Global (sem `tenant_id`): o glossário é compartilhado.

Vocabulário de string (sem SAEnum, alinhado com `dataset_field`):
    tipo_semantico: text | number | date | bool | money | cnpj | cnae | enum | object | array
    sensibilidade:  publico | interno | pii
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TermoCanonico(Base):
    """Conceito canônico de negócio (folha semântica), vendor-agnóstico."""

    __tablename__ = "termo_canonico"
    __table_args__ = (
        UniqueConstraint("codigo", name="uq_termo_canonico_codigo"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # Código estável e legível (UPPER_SNAKE): CNPJ, RAZAO_SOCIAL, CNAE...
    codigo: Mapped[str] = mapped_column(String(64), nullable=False)
    nome_pt_br: Mapped[str] = mapped_column(String(128), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo_semantico: Mapped[str] = mapped_column(
        String(24), nullable=False, default="text", server_default="text"
    )
    sensibilidade_default: Mapped[str] = mapped_column(
        String(16), nullable=False, default="publico", server_default="publico"
    )
    # Unidade quando numérico (BRL, anos, %). NULL para não-numéricos.
    unidade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<TermoCanonico {self.codigo!r}>"
