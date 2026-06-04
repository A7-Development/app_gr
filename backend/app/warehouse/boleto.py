"""wh_boleto -- canonico (silver) do lado COBRANCA da conciliacao.

Contrato source-agnostic do boleto bancario. O motor de conciliacao cruza
`wh_boleto` (lado banco) x `wh_titulo` (lado carteira) e nao conhece nem o
banco cobrador nem o layout CNAB -- toda a especificidade fica no adapter por
banco que popula esta tabela (CLAUDE.md secao 13).

Granularidade: snapshot diario de boleto ATIVO/conhecido por
`(tenant, banco_origem, numero_documento, data_ref)`. Cada conciliacao roda
contra a `data_ref` do dia; o historico por dia fica preservado (suporta o
controle de divergencia "recorrente" do documento de conciliacao). O estado
ja vem com a vigencia resolvida (ultima instrucao por titulo) pelo mapper --
`wh_boleto` nao guarda o historico de instrucoes, so o estado vigente do dia.

Chave de cruzamento com a carteira: `numero_documento` <-> `wh_titulo.numero`
(a normalizacao de mascara/parcela acontece no servico de conciliacao, nos
dois lados). `sacado_documento` serve de confirmacao do vinculo.

Carrega `Auditable`: `source_type` = COBRANCA_<BANCO>, `source_id` aponta o
boleto na origem (nosso_numero quando houver). Lineage ao bronze via
`arquivo_id`.
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
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable

# Estado vigente do boleto (vigencia ja resolvida pelo mapper a partir do
# codigo de ocorrencia CNAB de cada banco). String, nao enum SQL.
ESTADO_ATIVO = "ativo"  # boleto em aberto (entrada vigente)
ESTADO_BAIXADO = "baixado"  # baixa/cancelamento vigente
ESTADO_LIQUIDADO = "liquidado"  # pago/liquidado


class Boleto(Auditable, Base):
    """Boleto bancario canonico (estado vigente do dia)."""

    __tablename__ = "wh_boleto"
    __table_args__ = (
        # Um boleto vigente por (banco, numero_documento) por data-base.
        UniqueConstraint(
            "tenant_id",
            "banco_origem",
            "numero_documento",
            "data_ref",
            name="uq_wh_boleto",
        ),
        # Cruzamento com a carteira: boletos ativos do dia por numero.
        Index(
            "ix_wh_boleto_tenant_data_estado_numero",
            "tenant_id",
            "data_ref",
            "estado",
            "numero_documento",
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

    # Banco cobrador de origem (BANCO_* em cnab_raw_arquivo).
    banco_origem: Mapped[str] = mapped_column(String(20), nullable=False)

    # Numero do documento/titulo no banco -- CHAVE de cruzamento com
    # wh_titulo.numero.
    numero_documento: Mapped[str] = mapped_column(String(50), nullable=False)
    # Identificador do boleto no banco (nosso numero) -- 2a chave/confirmacao.
    nosso_numero: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Sacado (confirmacao do vinculo com o titulo).
    sacado_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sacado_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Valor do boleto (= wh_titulo.valor_liquido no cruzamento).
    valor_boleto: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # Valor efetivamente pago (quando liquidado).
    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    data_vencimento: Mapped[date] = mapped_column(Date, nullable=False)
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Estado vigente (ESTADO_*) -- vigencia ja resolvida pelo mapper.
    estado: Mapped[str] = mapped_column(String(12), nullable=False)

    # Codigo de ocorrencia CNAB cru da instrucao vigente + sua data. Mantidos
    # para auditoria e enriquecimento de Obs. (ex.: explicar divergencia).
    codigo_ocorrencia: Mapped[str | None] = mapped_column(String(10), nullable=True)
    data_ocorrencia: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Data-base do snapshot (qual retorno/dia este estado representa).
    data_ref: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Lineage ao arquivo CNAB bronze que originou este estado.
    arquivo_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_cnab_raw_arquivo.id", ondelete="SET NULL"),
        nullable=True,
    )
