"""wh_pj_kyc (+ ocorrencias) -- KYC/compliance canonico de uma PJ e seus socios.

Silver vendor-neutro do pacote KYC, alimentado pelo BDC (`kyc` = sujeito-empresa
e `owners_kyc` = cada socio). Duas tabelas:

- **wh_pj_kyc** (header, 1 linha por sujeito) — flags + contadores + buckets de
  recencia. Representa o "nada consta" (sujeito checado, sem hits) de forma
  explicita. Dataset COMPUTADO -> `source_updated_at` NULL (idade = consulta).
- **wh_pj_kyc_ocorrencia** (1 linha por hit de sancao/PEP) — carrega `match_rate`
  (o BDC casa por NOME e devolve % de match — SEM threshold enche de ruido) e o
  frescor POR REGISTRO: `source_updated_at` = `LastUpdateDate` da ocorrencia.

`cnpj` = a PJ consultada (a raiz do dossie). `subject_documento` = de QUEM e o
dado (a propria empresa no `kyc`; o CPF do socio no `owners_kyc`).
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class PjKyc(Auditable, Base):
    """Header KYC de um sujeito (empresa ou socio): flags + contadores."""

    __tablename__ = "wh_pj_kyc"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "cnpj", "subject_documento", "source_type",
            name="uq_wh_pj_kyc",
        ),
        Index("ix_wh_pj_kyc_tenant_cnpj", "tenant_id", "cnpj"),
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
    subject_documento: Mapped[str] = mapped_column(String(14), nullable=False)
    subject_tipo: Mapped[str | None] = mapped_column(String(2), nullable=True)  # PF/PJ
    subject_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_currently_pep: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_currently_sanctioned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    was_previously_sanctioned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    count_sanctions: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    count_peps: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    last_30_days_sanctions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_90_days_sanctions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_180_days_sanctions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_365_days_sanctions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PjKyc cnpj={self.cnpj} subject={self.subject_documento} "
            f"pep={self.is_currently_pep} sanc={self.is_currently_sanctioned}>"
        )


class PjKycOcorrencia(Auditable, Base):
    """Uma ocorrencia de sancao/PEP, com match_rate e frescor por registro."""

    __tablename__ = "wh_pj_kyc_ocorrencia"
    __table_args__ = (
        Index("ix_wh_pj_kyc_ocorrencia_tenant_cnpj", "tenant_id", "cnpj"),
        Index(
            "ix_wh_pj_kyc_ocorrencia_tenant_subject",
            "tenant_id",
            "subject_documento",
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
    subject_documento: Mapped[str] = mapped_column(String(14), nullable=False)
    subject_tipo: Mapped[str | None] = mapped_column(String(2), nullable=True)
    subject_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # SANCTION | PEP
    categoria: Mapped[str] = mapped_column(String(16), nullable=False)
    fonte: Mapped[str | None] = mapped_column(String(64), nullable=True)  # interpol, ...
    tipo: Mapped[str | None] = mapped_column(String(128), nullable=True)  # StandardizedSanctionType
    # % de match do nome (0-100). Filtro DURO contra falso-positivo.
    match_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    name_uniqueness_score: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    nome_original: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nome_sancao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Details cru preservado (charges, nationalities, image, ...).
    detalhe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PjKycOcorrencia subject={self.subject_documento} "
            f"{self.categoria}/{self.fonte} match={self.match_rate}>"
        )
