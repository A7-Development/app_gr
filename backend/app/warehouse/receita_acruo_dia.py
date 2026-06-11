"""wh_receita_acruo_dia -- METODO ACRUO: apropriacao diaria do desagio.

Segundo dos TRES metodos de apuracao de receita (decisao 2026-06-11):
caixa (wh_receita_operacional) · ACRUO (esta tabela) · competencia (futuro).
Nenhum elimina o outro.

Uma linha = a cota diaria que a curva de UM titulo apropriou em UM dia util
(sistematica do fundo, validada na wh_estoque_recebivel da QiTech):

    VP_d = PV x f^d, com f = (face/PV)^(1/n_DU)
    cota_d = VP_d - VP_{d-1}; comeca D+1 da efetivacao, so dia util
    (wh_dim_dia_util), PARA no vencimento ORIGINAL (VP congela na face --
    confirmado empiricamente: prorrogacao NAO estende a curva; juros de
    prorrogacao sao receita-evento a parte).

Eventos:
    acruo             -- cota diaria normal da curva
    acruo_antecipacao -- residual INTEIRO no dia em que o titulo saiu antes
                         do vencimento (liquidacao antecipada ou recompra)

Componentes (cota aberta na proporcao de cada um no desagio total):
    desagio_total = face - valor_presente   (PV = ancora; o rateio de
                    tarifas da operacao JA esta embutido no PV -- "nao
                    replicar regra", validado QiTech valor_compra == PV)
    valor_desagio = parte juros   (OperacaoItem.ValorDeJuros)
    valor_adval   = parte ad valorem (ValorDoAdValorem)
    valor_tarifas = residuo (desagio_total - juros - adval - IOF)
    IOF fica FORA (repasse de imposto, nao receita).

Invariante por titulo: Σ cotas (todas as linhas) == desagio_total - IOF,
centavo a centavo (residuo de arredondamento fecha na ultima linha).

Derivada 100% de silver (source_type='derived'); rebuild idempotente por
titulo (delete+insert do conjunto do titulo). Mora/prorrogacao/recompra/
tarifas de servico NAO vivem aqui -- no metodo acruo elas sao iguais ao
caixa (leitura = uniao desta tabela com as familias-evento do
wh_receita_operacional).
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

EVENTO_ACRUO = "acruo"
EVENTO_ACRUO_ANTECIPACAO = "acruo_antecipacao"


class ReceitaAcruoDia(Auditable, Base):
    """Cota diaria da curva de desagio de um titulo (metodo acruo)."""

    __tablename__ = "wh_receita_acruo_dia"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_receita_acruo_dia_source"
        ),
        Index("ix_wh_receita_acruo_dia_tenant_comp", "tenant_id", "competencia"),
        Index("ix_wh_receita_acruo_dia_tenant_data", "tenant_id", "data"),
        Index("ix_wh_receita_acruo_dia_tenant_titulo", "tenant_id", "titulo_id"),
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

    # Componentes da cota (abertos na proporcao do desagio total do titulo).
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
