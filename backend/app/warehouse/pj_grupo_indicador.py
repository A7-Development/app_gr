"""wh_pj_grupo_indicador -- indicadores agregados do grupo economico de uma PJ.

Silver canonico **vendor-neutro** do pacote Quadro Societario. Cada linha e o
ROLLUP do grupo economico de 1o nivel do CNPJ consultado: contadores de
empresas, pessoas, e os sinais de risco que importam pra credito
(`total_sanctioned`, `total_lawsuits`, `total_peps`). Alimentado pelo BDC
(`economic_group_first_level`).

Grao: 1 linha por (tenant, cnpj). Reconciliacao por `(tenant, cnpj,
source_type)` (upsert) — re-consulta sobrescreve, fonte diferente nao colide.

Frescor (§14): este e dataset DERIVADO/COMPUTADO — o BDC recalcula o agregado
a cada consulta e NAO devolve `LastUpdateDate`. Logo `source_updated_at` fica
**NULL** e a idade da informacao e a da consulta (`ingested_at`). As datas de
passagem (`first/last_passage_date`) sao recencia de ATIVIDADE do grupo, nao
data de atualizacao do dado — guardadas como sinal, nao como frescor.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
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


class PjGrupoIndicador(Auditable, Base):
    """Indicadores agregados do grupo economico de 1o nivel de uma PJ."""

    __tablename__ = "wh_pj_grupo_indicador"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "cnpj",
            "source_type",
            name="uq_wh_pj_grupo_indicador",
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

    # ── Composicao do grupo ──
    total_companies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_active: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_inactive: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_people: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_owners: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Sinais de risco (o que credito olha primeiro) ──
    total_sanctioned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_peps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_lawsuits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_bad_passages: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Atividade / maturidade ──
    avg_activity_level: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    min_company_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_company_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_company_age: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Recencia de atividade (passages) — sinal, NAO frescor do dado ──
    first_passage_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_passage_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_12m_passages: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PjGrupoIndicador {self.cnpj} companies={self.total_companies} "
            f"sanctioned={self.total_sanctioned} lawsuits={self.total_lawsuits}>"
        )
