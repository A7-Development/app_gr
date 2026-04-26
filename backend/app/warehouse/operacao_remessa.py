"""wh_operacao_remessa -- operacoes de remessa CNAB enviadas ao FIDC.

Diferente das tabelas wh_aquisicao_recebivel / wh_liquidacao_recebivel /
wh_estoque_recebivel — aqui granularidade NAO e por recebivel individual,
e sim por **lote/operacao de remessa** (cada arquivo .rem que o cedente
sobe agrega varios recebiveis e vira 1 linha de operacao).

Fonte: QiTech `/v2/fidc-custodia/report/fundo/{cnpj}/data/{data}` —
"Detalhes de Operacoes FIDC por Data de Importacao". `idOperacaoRecebivel`
e o id estavel do lote.

Util pra:
- Reconciliar arquivos enviados pela cedente vs cessoes processadas
- Auditoria operacional do FIDC (quantas remessas por dia, valores totais)
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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


class OperacaoRemessa(Auditable, Base):
    """1 lote de cessao (arquivo CNAB .rem) processado pelo FIDC num dia."""

    __tablename__ = "wh_operacao_remessa"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_operacao_remessa"
        ),
        Index(
            "ix_wh_operacao_remessa_tenant_fundo_data",
            "tenant_id",
            "fundo_doc",
            "data_importacao",
        ),
        Index(
            "ix_wh_operacao_remessa_tenant_fundo_cedente",
            "tenant_id",
            "fundo_doc",
            "cedente_doc",
            "data_importacao",
        ),
        Index(
            "ix_wh_operacao_remessa_id_operacao",
            "id_operacao_recebivel",
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

    # ---- Quando ----
    # `data` no payload = data de importacao do arquivo no FIDC.
    data_importacao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # ---- Fundo ----
    fundo_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    fundo_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    # ---- Gestor (= UA primaria do tenant geralmente) ----
    gestor_doc: Mapped[str] = mapped_column(String(14), nullable=False)
    gestor_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    # ---- Cedente ----
    cedente_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    cedente_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    # ---- Operacao / arquivo CNAB ----
    id_operacao_recebivel: Mapped[str] = mapped_column(String(32), nullable=False)
    nome_arquivo: Mapped[str] = mapped_column(String(100), nullable=False)
    nome_arquivo_entrada: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo_recebivel: Mapped[str] = mapped_column(String(50), nullable=False)

    # ---- Fatos: valores R$ ----
    remessa: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reembolso: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    recompra: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    coobrigacao: Mapped[bool] = mapped_column(Boolean, nullable=False)
