"""wh_boleto_vigente -- estado vigente do boleto (silver), projecao da timeline.

O "saldo" do "extrato": 1 linha por boleto (banco, UA, nosso_numero) com o
estado corrente derivado do fold de `wh_boleto_evento`. NAO e digitado -- e
recalculado da timeline (projecao). Re-rodar o fold reescreve.

Regra de fold (deterministica, validada em prod a 99,91% do Saldo Atual do
banco): o estado vigente vem do evento de estado (efeito abre/fecha/rejeita)
mais recente; em empate de data, o terminal (fecha/rejeita) vence o abre
(entrada + baixa no mesmo dia = fechado). Aberto <=> esse evento e 'abre'.

E a tabela que a conciliacao le (lado banco) no lugar do antigo `wh_boleto`
por data_ref: a carteira de cobranca ATUAL, sem data-base. `estado=ativo` =
boletos em aberto que cruzam com `wh_titulo`.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Estado vigente (resultado do fold).
ESTADO_ATIVO = "ativo"  # em aberto no banco (cruza com a carteira)
ESTADO_LIQUIDADO = "liquidado"
ESTADO_BAIXADO = "baixado"
ESTADO_REJEITADO = "rejeitado"  # entrada rejeitada (nunca virou boleto)


class BoletoVigente(Base):
    """Estado corrente de um boleto (projecao do fold da timeline)."""

    __tablename__ = "wh_boleto_vigente"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "banco_origem",
            "nosso_numero",
            name="uq_wh_boleto_vigente",
        ),
        # Conciliacao: boletos ativos por numero (cruzamento com wh_titulo).
        Index(
            "ix_wh_boleto_vigente_cruzamento",
            "tenant_id",
            "banco_origem",
            "estado",
            "numero_documento",
        ),
        # Escopo por UA + estado.
        Index(
            "ix_wh_boleto_vigente_ua_estado",
            "tenant_id",
            "ua_id",
            "estado",
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

    banco_origem: Mapped[str] = mapped_column(String(20), nullable=False)
    ua_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ua_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)

    nosso_numero: Mapped[str] = mapped_column(String(50), nullable=False)
    numero_documento: Mapped[str] = mapped_column(String(50), nullable=False)

    sacado_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sacado_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)

    estado: Mapped[str] = mapped_column(String(12), nullable=False)
    valor_atual: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Evento de estado vigente (o que decidiu o estado) + frescor.
    tipo_evento_vigente: Mapped[str] = mapped_column(String(40), nullable=False)
    codigo_ocorrencia_vigente: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    data_ocorrencia_vigente: Mapped[date] = mapped_column(Date, nullable=False)
    primeiro_evento_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    n_eventos: Mapped[int] = mapped_column(Integer, nullable=False)

    projected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    projected_by_version: Mapped[str] = mapped_column(String(128), nullable=False)
