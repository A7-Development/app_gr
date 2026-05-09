"""wh_qitech_raw_bank_account_statement -- raw (bronze) de /v2/bank-account/statement.

Padrao raw -> canonico (CLAUDE.md secao 13.2). Esta tabela armazena o payload
cru do GET /v2/bank-account/statement/{agencia}/{conta}/{inicio}/{fim} --
extrato (lancamentos) de uma conta-corrente da UA num periodo.

Granularidade: 1 linha por (tenant, ua, agencia, conta, periodo_inicio,
periodo_fim). O payload contem N lancamentos -- explosao em N linhas
canonicas acontece no mapper, NAO aqui.

Re-rodar o ETL pro mesmo (ag, conta, periodo) substitui via UQ. Periodos
sobrepostos sao gravados em linhas distintas -- responsabilidade do mapper
e dos consumidores deduplicar lancamentos pelo `source_id` canonico.

NAO usa Auditable (excecao da raw, ver CLAUDE.md 14.1).
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QiTechRawBankAccountStatement(Base):
    """Payload cru de extrato bancario, por agencia+conta, por periodo."""

    __tablename__ = "wh_qitech_raw_bank_account_statement"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "agencia",
            "conta",
            "periodo_inicio",
            "periodo_fim",
            name="uq_wh_qitech_raw_bank_account_statement",
        ),
        Index(
            "ix_wh_qitech_raw_bank_account_statement_conta_periodo",
            "tenant_id",
            "agencia",
            "conta",
            "periodo_inicio",
            "periodo_fim",
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
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
        ),
        nullable=True,
        index=True,
    )

    # -- Path da QiTech --
    agencia: Mapped[str] = mapped_column(String(20), nullable=False)
    conta: Mapped[str] = mapped_column(String(40), nullable=False)
    periodo_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    periodo_fim: Mapped[date] = mapped_column(Date, nullable=False)

    # -- Payload --
    # Costuma ser lista de lancamentos ou objeto envelope com lista dentro;
    # mapper sabe interpretar. JSONB tolera ambos via wrapper.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )

    # -- Proveniencia da raw --
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_by_version: Mapped[str] = mapped_column(String(128), nullable=False)
