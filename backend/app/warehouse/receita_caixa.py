"""wh_receita_caixa -- METODO CAIXA: desagio apropriado na SAIDA do titulo.

Terceiro dos TRES metodos de apuracao (decisao Ricardo 2026-06-11/12):

    CAIXA       -> desagio + tarifas do titulo apropriam QUANDO O TITULO
                   LIQUIDA (o dinheiro voltou; resultado realizado).
                   Esta tabela.
    COMPETENCIA -> integral na efetivacao da operacao
                   (= bloco 'operacao' do wh_receita_operacional).
    ACRUO       -> curva diaria D+1 DU (wh_receita_acruo_dia).

Uma linha = UM titulo (uma vida, no caso re-operado) com o desagio TOTAL
apropriado na data da saida. Recompra pelo VN cheio + encargos (padrao
Bitfin, validado: recomprado 150.000 + juros 700 + multa 4.500 = pagamento
155.200) -> desagio inteiro apropria na recompra tambem — "recomprado em
dinheiro ou com outro titulo nao muda a logica" (Ricardo). Titulo em
aberto/vencido sem pagar: NADA (ainda nao virou dinheiro).

Componentes identicos ao acruo (mesma funcao `componentes_titulo`):
juros/adval/tarifas capados no desagio observavel (face - PV - IOF).

Eventos: liquidacao (situacao 1) | baixa (2) | recompra (5) |
reoperacao (vida i de titulo re-operado termina na efetivacao da vida i+1).

Mora/prorrogacao/recompra-encargos/tarifas de servico NAO vivem aqui (sao
"quando recebidas" nos 3 metodos — leitura do caixa = uniao desta tabela
com as familias-evento do wh_receita_operacional). Derivada 100% de silver
(source_type='derived').
"""

from __future__ import annotations

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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable

EVENTO_CAIXA_LIQUIDACAO = "liquidacao"
EVENTO_CAIXA_BAIXA = "baixa"
EVENTO_CAIXA_RECOMPRA = "recompra"
EVENTO_CAIXA_REOPERACAO = "reoperacao"


class ReceitaCaixa(Auditable, Base):
    """Desagio total de um titulo apropriado na data da saida (metodo caixa)."""

    __tablename__ = "wh_receita_caixa"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_receita_caixa_source"
        ),
        Index("ix_wh_receita_caixa_tenant_comp", "tenant_id", "competencia"),
        Index("ix_wh_receita_caixa_tenant_data", "tenant_id", "data"),
        Index("ix_wh_receita_caixa_tenant_titulo", "tenant_id", "titulo_id"),
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

    data: Mapped[date] = mapped_column(Date, nullable=False)
    competencia: Mapped[date] = mapped_column(Date, nullable=False)
    evento: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    titulo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    operacao_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    documento: Mapped[str | None] = mapped_column(String(40), nullable=True)

    valor_desagio: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_adval: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_tarifas: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    unidade_administrativa_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    cedente_entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cedente_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cedente_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
