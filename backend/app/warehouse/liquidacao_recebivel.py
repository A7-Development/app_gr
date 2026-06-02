"""wh_liquidacao_recebivel -- recebiveis liquidados/baixados num periodo.

Granularidade: 1 linha por MOVIMENTO de baixa de recebivel. Um `idRecebivel`
pode ter N movimentos (LIQUIDACAO PARCIAL em datas distintas + BAIXA final),
por isso a business key inclui `data_posicao` + `tipo_movimento`:
source_id = `{cnpj_fundo}|{idRecebivel}|{data_posicao}|liq`.
(Premissa antiga "1 baixa final por recebivel" era falsa — ver migration
c3f8b1d6e4a2.)

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
        # Business key: um recebivel tem N movimentos (parciais + baixa final)
        # em datas distintas. data_posicao + tipo_movimento distinguem cada um.
        UniqueConstraint(
            "tenant_id",
            "fundo_doc",
            "id_recebivel",
            "data_posicao",
            "tipo_movimento",
            name="uq_wh_liquidacao_recebivel",
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
    # NUMERIC(18,10) widen historico (2026-05-12): QiTech eventualmente
    # entrega `txAquisicao` >9999 (ex.: 201943.10 numa cessao FRICOCK de
    # 2026-04-10), provavelmente bug deles. (14,10) ja foi tentado e
    # tambem estourou. Aceitamos no DB e tratamos como outlier no consumer.
    taxa_aquisicao: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)

    # Estado
    # 'st_recebivel' aceita VENCIDOS / VINCENDOS / etc — string aberto.
    st_recebivel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # 'tipoMovimento' descreve a baixa: "BAIXA POR DEPOSITO SACADO", etc.
    tipo_movimento: Mapped[str] = mapped_column(String(80), nullable=False)
