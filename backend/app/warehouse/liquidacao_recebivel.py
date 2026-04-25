"""wh_liquidacao_recebivel -- recebiveis liquidados/baixados num periodo.

Granularidade: 1 linha por baixa de recebivel. Como cada `idRecebivel` so
tem 1 baixa final, source_id = `{cnpj_fundo}|{idRecebivel}|liq`.

Fonte: QiTech `/v2/fidc-custodia/report/liquidados-baixados/v2/{cnpj}/{di}/{df}`.

Inconsistencias notaveis no payload (a confirmar com mais samples):
- `valorVencimento` vem como STRING com virgula BR ("12699,03")
- `ajuste` idem (string com virgula)
- `idRecebivel` aqui e str (no `aquisicao-consolidada` e int)
- Outros valores monetarios sao number puro

Mapper normaliza tudo via `parse_decimal_br` que aceita ambos formatos.
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


class LiquidacaoRecebivel(Auditable, Base):
    """Liquidacao/baixa de recebivel cedido ao FIDC."""

    __tablename__ = "wh_liquidacao_recebivel"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_liquidacao_recebivel"
        ),
        Index(
            "ix_wh_liquidacao_recebivel_tenant_fundo_data",
            "tenant_id",
            "fundo_doc",
            "data_posicao",
        ),
        Index(
            "ix_wh_liquidacao_recebivel_tenant_fundo_sacado",
            "tenant_id",
            "fundo_doc",
            "sacado_doc",
            "data_posicao",
        ),
        Index(
            "ix_wh_liquidacao_recebivel_id_recebivel",
            "id_recebivel",
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

    # `dataDaPosicao` na QiTech aqui = data da liquidacao/baixa.
    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_aquisicao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Fundo
    fundo_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    fundo_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    # Cedente / Sacado
    cedente_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    cedente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    sacado_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    sacado_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    # Recebivel
    id_recebivel: Mapped[str] = mapped_column(String(32), nullable=False)
    seu_numero: Mapped[str] = mapped_column(String(50), nullable=False)
    documento: Mapped[str] = mapped_column(String(100), nullable=False)
    numero_correspondente: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tipo_recebivel: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Fatos: valores
    valor_aquisicao: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_vencimento: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_pago: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    ajuste: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    taxa_aquisicao: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)

    # Estado
    # 'st_recebivel' aceita VENCIDOS / VINCENDOS / etc — string aberto.
    st_recebivel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # 'tipoMovimento' descreve a baixa: "BAIXA POR DEPOSITO SACADO", etc.
    tipo_movimento: Mapped[str] = mapped_column(String(80), nullable=False)
