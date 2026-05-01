"""wh_qitech_raw_bank_account_balance -- raw (bronze) de /v2/bank-account/balance.

Padrao raw -> canonico (CLAUDE.md secao 13.2). Esta tabela armazena o payload
cru do GET /v2/bank-account/balance/{agencia}/{conta}/{data} -- saldo de
fechamento do dia para uma conta-corrente da UA na Singulare.

Granularidade: 1 linha por (tenant, ua, agencia, conta, data_posicao).
Re-rodar o ETL pro mesmo (ag, conta, dia) substitui via UQ.

NAO usa Auditable (CLAUDE.md secao 14.1, excecao explicita): a raw E a fonte;
proveniencia direta via fetched_at + fetched_by_version + payload_sha256.

Schema do payload e modelado no mapper correspondente em
`app/modules/integracoes/adapters/admin/qitech/mappers/bank_account_balance.py`.
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


class QiTechRawBankAccountBalance(Base):
    """Payload cru de saldo bancario diario, por agencia+conta, por dia."""

    __tablename__ = "wh_qitech_raw_bank_account_balance"
    __table_args__ = (
        # Idempotencia: re-fetch do mesmo (ua, ag, conta, dia) substitui via upsert.
        UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "agencia",
            "conta",
            "data_posicao",
            name="uq_wh_qitech_raw_bank_account_balance",
        ),
        # Acesso canonico: "todos os saldos de uma conta num intervalo de datas".
        Index(
            "ix_wh_qitech_raw_bank_account_balance_conta_data",
            "tenant_id",
            "agencia",
            "conta",
            "data_posicao",
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
    # UA e parte da chave de UQ porque CNPJ titular vem implicitamente dela
    # (UA -> tenant_source_config QiTech -> bank_accounts dessa UA). Toda
    # linha gravada pelo adapter informa explicitamente; nullable apenas
    # para retrocompat se algum dia tiver linha legacy.
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
    # Data do path (`/{aaaa-mm-dd}`). Nao confundir com qualquer data interna
    # do payload -- esta e a fonte da verdade pra particionar.
    data_posicao: Mapped[date] = mapped_column(Date, nullable=False)

    # -- Payload --
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
