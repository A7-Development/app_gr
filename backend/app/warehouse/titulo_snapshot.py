"""wh_titulo_snapshot — snapshot diario de cada titulo na carteira.

Espelho de `ANALYTICS.elig_snapshot_titulo`. Fonte principal de:
- L2 Carteira (slice no `data_ref` mais recente)
- L2 Comportamento (serie temporal sobre `data_ref`)

Bootstrap: ingerir todo historico do ANALYTICS (~214k linhas / 3.5 meses).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class TituloSnapshot(Auditable, Base):
    """Snapshot diario de um titulo (uma linha por titulo por data_ref)."""

    __tablename__ = "wh_titulo_snapshot"
    __table_args__ = (
        UniqueConstraint("tenant_id", "data_ref", "source_id", name="uq_wh_titulo_snapshot"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Temporal
    snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    data_ref: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Dimensoes operacionais
    unidade_administrativa_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sacado_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coobrigacao: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Produto
    produto_sigla: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    produto_descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recebivel_sigla: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recebivel_descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Status
    status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    situacao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    situacao_descricao: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Cedente
    cedente_cliente_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cedente_entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    cedente_nome: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cedente_documento: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    grupo_economico_id_cedente: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grupo_economico_nome_cedente: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cedente_em_rj: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cedente_chave_cnae: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cnae_secao: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cnae_divisao: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cnae_grupo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cnae_classe: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cnae_subclasse: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cnae_denominacao: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Sacado
    sacado_entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sacado_nome: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sacado_documento: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    grupo_economico_id_sacado: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grupo_economico_nome_sacado: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sacado_em_rj: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Gerente
    gerente_nome: Mapped[str | None] = mapped_column(String(300), nullable=True)
    gerente_documento: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Group keys (ja consolidados pela view do ANALYTICS)
    cedente_grp_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cedente_grp_nome: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cedente_grp_tipo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sacado_grp_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sacado_grp_nome: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sacado_grp_tipo: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Metricas monetarias (Numeric 18,4)
    saldo_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    vencido: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    vencido_mais_5_dias: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    vencido_d0_a_d5: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    vencido_ate_d30: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    vencido_ate_d60: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    vencido_60_ate_120: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    vencido_maior_d120: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # Quantidades
    qtd_titulos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qtd_operacoes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qtd_cedentes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qtd_sacados: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Ticket / atraso
    ticket_medio: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    atraso_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    atraso_medio: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
