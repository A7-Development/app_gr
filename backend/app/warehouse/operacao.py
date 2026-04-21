"""wh_operacao + wh_operacao_item — fatos de operacoes (da Bitfin).

Fonte: `Operacao` + `OperacaoResultado` + `OperacaoItem` do Bitfin.

Serve:
- L2 Operacoes (Volume, Taxa, Prazo, Ticket, Receita contratada)
- L2 Receitas (pelo menos a parte "receita contratada" = TotalDeJuros + tarifas)
- Ficha (drill-down operacoes de um cedente)
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
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


class Operacao(Auditable, Base):
    """Operacao efetivada (contrato de cessao) com metricas de resultado."""

    __tablename__ = "wh_operacao"
    __table_args__ = (UniqueConstraint("tenant_id", "source_id", name="uq_wh_operacao"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identificacao
    operacao_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    data_de_cadastro: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_de_efetivacao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    efetivada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    quantidade_de_titulos: Mapped[int] = mapped_column(Integer, nullable=False)
    origem: Mapped[int] = mapped_column(Integer, nullable=False)
    modalidade: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    coobrigacao: Mapped[bool] = mapped_column(Boolean, nullable=False)
    codigo_de_registro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contrato_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Contas/unidades
    conta_operacional_id: Mapped[int] = mapped_column(Integer, nullable=False)
    unidade_administrativa_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # OperacaoResultado — metricas consolidadas
    prazo_medio_real: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    prazo_medio_cobrado: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    total_bruto: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total_liquido: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total_de_juros: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total_de_ad_valorem: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total_de_iof: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total_de_imposto: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total_de_rebate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    valor_medio_dos_titulos: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )
    valor_medio_por_sacado: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    quantidade_de_sacados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    taxa_de_juros: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    taxa_de_ad_valorem: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    taxa_de_iof: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    taxa_de_imposto: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    taxa_de_rebate: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    spread: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    fator_de_desconto_cobrado: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0
    )
    fator_de_desconto_real: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0
    )
    floating_para_prazo: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)

    # Tarifas (somatorias)
    total_das_consultas_financeiras: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )
    total_dos_registros_bancarios: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )
    total_das_consultas_fiscais: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )
    total_dos_comunicados_de_cessao: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )
    total_dos_documentos_digitais: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )
    total_dos_descontos_ou_abatimentos: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )

    data_do_ultimo_vencimento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OperacaoItem(Auditable, Base):
    """Item (titulo) dentro de uma operacao (granularidade maxima)."""

    __tablename__ = "wh_operacao_item"
    __table_args__ = (UniqueConstraint("tenant_id", "source_id", name="uq_wh_operacao_item"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_da_operacao_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    operacao_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    titulo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    valor_base: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valor_liquido: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valor_presente: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valor_de_juros: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    valor_do_ad_valorem: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    valor_do_iof: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    valor_do_rebate: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    saldo_devedor: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)

    prazo_real: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    prazo_cobrado: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)

    data_de_vencimento_original: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sugerido_para_exclusao: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
