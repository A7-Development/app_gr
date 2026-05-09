"""wh_movimento_aberto -- snapshot de cessoes em aberto (pendentes) do FIDC.

Granularidade: 1 linha por (tenant, snapshot_em, cessao). Cada execucao
do ETL gera N linhas (1 por cessao em aberto naquela data). Como e
snapshot diario, source_id inclui `data_referencia` (data da fetch) — re-rodar
o mesmo dia substitui via UQ; rodar D+1 cria novas linhas distintas.

Fonte: QiTech `/v2/fidc-custodia/report/movimento-aberto/{cnpj-fundo}/`
(sem data no path — snapshot atual).

Schema validado com formato esperado QiTech (sample real veio vazio em
2026-04-25 — REALINVEST nao tinha cessoes pendentes; schema baseado em
spec passada pelo user em 2026-04-25). Quando aparecer dado real,
validar tipos contra o sample.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class MovimentoAberto(Auditable, Base):
    """Cessao em aberto (pendente de liquidacao) num snapshot."""

    __tablename__ = "wh_movimento_aberto"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_movimento_aberto"
        ),
        Index(
            "ix_wh_movimento_aberto_tenant_fundo_ref",
            "tenant_id",
            "fundo_doc",
            "data_referencia",
        ),
        Index(
            "ix_wh_movimento_aberto_tenant_fundo_venc",
            "tenant_id",
            "fundo_doc",
            "data_vencimento",
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
    # UA dona da credencial que produziu esta linha (multi-UA, Phase F).
    # Nullable apenas para retrocompat com linhas legacy ingeridas antes
    # da introducao de multi-UA. Toda nova linha gravada pelo adapter
    # informa explicitamente.
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
        ),
        nullable=True,
        index=True,
    )

    # ---- Snapshot ----
    # Data da fetch (= snapshot). Diferente de data_movimento (data interna
    # do recebivel na QiTech). source_id inclui data_referencia.
    data_referencia: Mapped[date] = mapped_column(
        Date, nullable=False, index=True
    )

    # ---- Datas do recebivel ----
    data_movimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ---- Fundo ----
    fundo_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    fundo_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    # ---- Recebivel ----
    # `seuNumero` vem como integer no spec — normalizamos pra string
    # pra consistencia com outras tabelas.
    seu_numero: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    numero_documento: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo_movimento: Mapped[str] = mapped_column(String(80), nullable=False)

    # ---- Fatos ----
    valor_aquisicao: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # `valorNominal` no spec e `integer` mas armazenamos Numeric pra
    # absorver caso vire decimal no futuro.
    valor_nominal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_movimentacao: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )
