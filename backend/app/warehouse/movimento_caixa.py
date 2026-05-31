"""wh_movimento_caixa -- demonstrativo de caixa (entradas/saidas/saldo).

Granularidade: 1 linha por (tenant, raw_id, seq_no) -- replace-by-partition
no scope do raw payload (`_replace_canonical_partition`). `seq_no` e a
posicao do item no snapshot; QiTech NAO devolve id estavel e pode repetir
lancamentos byte-iguais no mesmo dia (ex.: 2 resgates do mesmo fundo), entao
o seq_no desambigua. Re-fetch do mesmo dia gera o mesmo raw_id (UQ do raw
bate -> UPDATE in-place) -> os mesmos seq_no sao re-avaliados; rows que
sumiram do snapshot viram orfas e sao deletadas.

Historico (ate 2026-05-30, migration f4a2c9d8e1b7): a UQ era
(tenant, source_id) com source_id=sha16(item). O `saldo` corrente (volatil)
entrava no hash -> drift entre re-fetches -> acumulava duplicata por sync.
Trocado por raw_id+seq_no; `source_id` virou proveniencia pura.

Fonte: QiTech `/v2/netreport/report/market/demonstrativo-caixa/{data}`.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class MovimentoCaixa(Auditable, Base):
    """Movimento de caixa (entrada/saida/saldo) num dia."""

    __tablename__ = "wh_movimento_caixa"
    __table_args__ = (
        # Business key da partition (replace-by-partition, _replace_canonical_
        # partition). `seq_no` (posicao no snapshot) desambigua lancamentos
        # byte-iguais legitimos (ex.: 2 resgates identicos no mesmo dia).
        # Linhas legacy (raw_id NULL) ficam isentas — NULLs distintos no PG.
        # `source_id` deixou de ser unico: virou proveniencia pura (o `saldo`
        # corrente volatil entrava no sha16 e drifta entre re-fetches).
        UniqueConstraint(
            "tenant_id", "raw_id", "seq_no", name="uq_wh_movimento_caixa_raw_seq"
        ),
        Index(
            "ix_wh_movimento_caixa_tenant_data",
            "tenant_id",
            "data_liquidacao",
        ),
        Index(
            "ix_wh_movimento_caixa_tenant_carteira",
            "tenant_id",
            "carteira_cliente_doc",
            "data_liquidacao",
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

    # `data_liquidacao` vem do `dataLiquidação` da QiTech. Pode diferir do
    # dia da fetch (ex.: pre-aviso de movimento futuro).
    data_liquidacao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    carteira_cliente_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    carteira_cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    carteira_cliente_doc: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )

    # Tipo de registro QiTech: 1=movimento, 2=saldo de fechamento, ...
    tipo_de_registro: Mapped[int] = mapped_column(Integer, nullable=False)
    # Descricao pode ser longa ("Aplicação no Fundo X [Y] a pagar em DD/MM/YYYY").
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    historico_traduzido: Mapped[str] = mapped_column(Text, nullable=False)

    # Dados bancarios (geralmente null em demonstrativo de caixa do FIDC).
    banco: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agencia: Mapped[str | None] = mapped_column(String(20), nullable=True)
    conta_corrente: Mapped[str | None] = mapped_column(String(30), nullable=True)
    digito: Mapped[str | None] = mapped_column(String(5), nullable=True)
    id_conta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conta_investimento: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Fluxo. Saidas vem negativas da QiTech.
    entradas: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    saidas: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # `saldo` e corrente/acumulado (volatil entre re-fetches) — por isso NAO
    # entra na business key; e so dado, atualizado in-place pelo replace.
    saldo: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # raw_id -- FK pra wh_qitech_raw_relatorio. Partition key do
    # _replace_canonical_partition. Nullable pra retrocompat com linhas
    # legacy ingeridas antes desta migration (f4a2c9d8e1b7, 2026-05-30).
    raw_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_qitech_raw_relatorio.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # seq_no -- posicao do item no snapshot do demonstrativo. Desambigua
    # lancamentos byte-iguais legitimos dentro de um mesmo raw (ex.: 2
    # resgates identicos no mesmo dia). Nullable em linhas legacy.
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
