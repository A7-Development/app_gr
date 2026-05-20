"""wh_extrato_bancario -- lancamentos da conta-corrente bancaria.

Granularidade: 1 linha por lancamento. Cada lancamento tem `source_id`
unico construido pelo mapper (tipicamente `bank_account_statement:{ua}:
{agencia}:{conta}:{data_lancamento}:{sha16(campos canonicos)}`) -- re-fetch
do mesmo periodo nao duplica via UQ (tenant_id, source_id).

Fonte inicial: QiTech `/v2/bank-account/statement/{agencia}/{conta}/{ini}/{fim}`
(adapter `admin:qitech`, familia bank-account). CNPJ titular vem da UA dona
da credencial.

Quando o mapper enxergar payload real da QiTech, campos opcionais
(contrapartida, documento, etc.) ganham populacao. Campos criticos (data,
valor, tipo) sao not-null -- mapper levanta erro se ausente.

Uso pretendido (pos-MVP):
- Reconciliacao Bitfin x QiTech: cruzar lancamentos por (data, valor, tipo)
- Auditoria de fluxo de caixa
- Composicao de DRE caixa quando contabilidade reativar
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


class ExtratoBancario(Auditable, Base):
    """Lancamento individual da conta-corrente."""

    __tablename__ = "wh_extrato_bancario"
    __table_args__ = (
        # Business key: 1 linha por lancamento (data + valor + tipo + descricao
        # + contrapartida) numa conta. Colisao se 2 lancamentos byte-iguais
        # aparecerem no mesmo dia — raro, aceito (dupla legitima).
        UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "agencia",
            "conta",
            "data_lancamento",
            "valor",
            "tipo",
            "descricao",
            "contrapartida_doc",
            name="uq_wh_extrato_bancario",
        ),
        Index(
            "ix_wh_extrato_bancario_tenant_conta_data",
            "tenant_id",
            "agencia",
            "conta",
            "data_lancamento",
        ),
        Index(
            "ix_wh_extrato_bancario_tenant_data",
            "tenant_id",
            "data_lancamento",
        ),
        # Para conciliacao por (valor, data) com Bitfin -- consulta tipica.
        Index(
            "ix_wh_extrato_bancario_tenant_data_valor",
            "tenant_id",
            "data_lancamento",
            "valor",
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
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
        ),
        nullable=True,
        index=True,
    )
    # raw_id -- FK pra wh_qitech_raw_bank_account_statement. Nullable inicial pra permitir
    # backfill assincrono (Fase 1.6). Identifica o raw payload que originou
    # esta linha -- usado como partition key no _replace_canonical_partition
    # (Fase 1.3 do refactor "espelho fiel QiTech", 2026-05-20).
    raw_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_qitech_raw_bank_account_statement.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # -- Conta --
    agencia: Mapped[str] = mapped_column(String(20), nullable=False)
    conta: Mapped[str] = mapped_column(String(40), nullable=False)
    banco_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    banco_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    moeda: Mapped[str] = mapped_column(
        String(3), nullable=False, default="BRL", server_default=text("'BRL'")
    )

    # -- Quando --
    # `data_lancamento` = data efetiva contabil do lancamento (a "data" que
    # importa pra conciliacao). `data_movimento` = data de evento bancario
    # quando QiTech distinguir (ex.: TED enviada hoje, lancada amanha).
    data_lancamento: Mapped[date] = mapped_column(
        Date, nullable=False, index=True
    )
    data_movimento: Mapped[date | None] = mapped_column(Date, nullable=True)

    # -- Lancamento --
    # Valor SEMPRE positivo. Tipo (DEBITO|CREDITO) carrega o sinal conceitual.
    # Convencao consistente com Bitfin (que tambem grava valor abs + tipo).
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # 'D' = debito (saida), 'C' = credito (entrada). String curta pra
    # tolerar variacoes do payload da QiTech sem migration imediata.
    tipo: Mapped[str] = mapped_column(String(1), nullable=False)

    # -- Descritivo --
    historico: Mapped[str | None] = mapped_column(String(255), nullable=True)
    descricao: Mapped[str | None] = mapped_column(String(500), nullable=True)
    documento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Contraparte (nome + doc + agencia/conta da outra ponta), quando QiTech
    # entrega. Util pra reconciliacao com sacados/cedentes.
    contrapartida_nome: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    contrapartida_doc: Mapped[str | None] = mapped_column(
        String(14), nullable=True
    )
