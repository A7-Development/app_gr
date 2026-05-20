"""wh_posicao_outros_ativos -- ativos que nao se encaixam em RF/RV/Fundos.

Ex.: PDD (provisao para devedores duvidosos), reservas, ajustes contabeis,
custos a apropriar. Granularidade: 1 linha por (tenant, data, codigo, cliente).

Fonte: QiTech `/v2/netreport/report/market/outros-ativos/{data}`.
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


class PosicaoOutrosAtivos(Auditable, Base):
    """Posicao em ativos diversos (PDD, reservas, etc)."""

    __tablename__ = "wh_posicao_outros_ativos"
    __table_args__ = (
        # Business key: 1 linha por (carteira, codigo) num dia.
        UniqueConstraint(
            "tenant_id",
            "data_posicao",
            "carteira_cliente_id",
            "codigo",
            name="uq_wh_posicao_outros_ativos",
        ),
        Index(
            "ix_wh_posicao_outros_ativos_tenant_data",
            "tenant_id",
            "data_posicao",
        ),
        Index(
            "ix_wh_posicao_outros_ativos_tenant_carteira",
            "tenant_id",
            "carteira_cliente_doc",
            "data_posicao",
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
    # raw_id -- FK pra wh_qitech_raw_relatorio. Nullable inicial pra permitir
    # backfill assincrono (Fase 1.6). Identifica o raw payload que originou
    # esta linha -- usado como partition key no _replace_canonical_partition
    # (Fase 1.3 do refactor "espelho fiel QiTech", 2026-05-20).
    raw_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_qitech_raw_relatorio.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    carteira_cliente_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    carteira_cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    carteira_cliente_doc: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )

    codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo_do_ativo: Mapped[str] = mapped_column(String(20), nullable=False)
    descricao_tipo_de_ativo: Mapped[str] = mapped_column(String(100), nullable=False)

    # Pode ser negativo (PDD reduz ativo).
    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    percentual_sobre_outros_ativos: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
    percentual_sobre_total: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
