"""wh_pj_evolucao (+ mensal) -- evolucao temporal de uma PJ (BDC company_evolution).

Silver canonico do dataset `company_evolution` (COMPANY_EVOLUTION_V1). Duas
tabelas:

- **wh_pj_evolucao** (header, 1/cnpj) — agregados + trajetoria: funcionarios
  (atual/max/min/media/distintos + media 1/3/5 anos atras), status de
  crescimento YoY, faturamento atual (faixa), socios (idem), nivel de atividade,
  flag de mudanca de QSA.
- **wh_pj_evolucao_mensal** (serie, 1/cnpj/mes) — a CURVA: funcionarios e faixa
  de faturamento mes a mes. E aqui que mora o sinal de porte/faturamento ao
  longo do tempo (so existe na serie).

Dataset DERIVADO/computado -> `source_updated_at` NULL (idade = consulta).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class PjEvolucao(Auditable, Base):
    """Header da evolucao temporal de uma PJ: agregados + trajetoria."""

    __tablename__ = "wh_pj_evolucao"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "cnpj", "source_type", name="uq_wh_pj_evolucao"
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
        ForeignKey("cadastros_unidade_administrativa.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    raw_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_bdc_raw_consulta.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)

    # ── Funcionarios ──
    funcionarios_atual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    funcionarios_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    funcionarios_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    funcionarios_media: Mapped[int | None] = mapped_column(Integer, nullable=True)
    funcionarios_distintos: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    funcionarios_media_1a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    funcionarios_media_3a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    funcionarios_media_5a: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Crescimento (YoY status: GROW UP / STABLE / SHRINK ...) ──
    crescimento_yoy_1a: Mapped[str | None] = mapped_column(String(32), nullable=True)
    crescimento_yoy_3a: Mapped[str | None] = mapped_column(String(32), nullable=True)
    crescimento_yoy_5a: Mapped[str | None] = mapped_column(String(32), nullable=True)
    qsa_mudou: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ── Faturamento (faixa do ultimo ponto) ──
    faturamento_faixa_atual: Mapped[str | None] = mapped_column(
        String(48), nullable=True
    )

    # ── Socios (QSA) ──
    socios_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    socios_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    socios_media: Mapped[int | None] = mapped_column(Integer, nullable=True)
    socios_distintos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    socios_media_1a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    socios_media_3a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    socios_media_5a: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Nivel de atividade ──
    atividade_max: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    atividade_min: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    atividade_media: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<PjEvolucao {self.cnpj} func_atual={self.funcionarios_atual} "
            f"yoy5a={self.crescimento_yoy_5a}>"
        )


class PjEvolucaoMensal(Auditable, Base):
    """Ponto mensal da serie de evolucao: funcionarios + faixa de faturamento."""

    __tablename__ = "wh_pj_evolucao_mensal"
    __table_args__ = (
        Index("ix_wh_pj_evolucao_mensal_tenant_cnpj_mes", "tenant_id", "cnpj", "mes"),
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
        ForeignKey("cadastros_unidade_administrativa.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    raw_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_bdc_raw_consulta.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)

    mes: Mapped[date] = mapped_column(Date, nullable=False)
    funcionarios: Mapped[int | None] = mapped_column(Integer, nullable=True)
    faturamento_faixa: Mapped[str | None] = mapped_column(String(48), nullable=True)

    def __repr__(self) -> str:
        return f"<PjEvolucaoMensal {self.cnpj} {self.mes} func={self.funcionarios}>"
