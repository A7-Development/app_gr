"""wh_posicao_cota_fundo — fato canonico de posicao em cota de fundo externo.

Granularidade: 1 linha por (tenant_id, data_posicao, carteira_cliente_id,
ativo_codigo). Re-ingerir o mesmo dia e idempotente via unique
(tenant_id, source_id) — padrao do warehouse.

Fonte inicial: QiTech `/v2/netreport/report/market/outros-fundos/{data}`
(adapter `admin:qitech`). Modelo projetado pra aceitar outras fontes
equivalentes (outros admins/custodiantes) no futuro sem refactor —
o mapper e especifico do vendor; a tabela e canonica.

Dimensoes:
- **Carteira (quem investe)**: `carteira_cliente_id` + `carteira_cliente_nome`
  + `carteira_cliente_doc` (CNPJ) + `carteira_cliente_sac`.
- **Ativo-investido (no que investe)**: `ativo_codigo` + `ativo_nome` +
  `ativo_instituicao`.
- **Quando**: `data_posicao`.

Fatos:
- Quantidade (livre / bloqueada).
- Valor da cota, valores monetarios (aplicacao/resgate, bruto, impostos,
  liquido) e percentuais (sobre fundos, sobre total).

Ver `docs/integracao-qitech.md` e amostra em
`qitech_samples/<tenant>/<data>/outros-fundos.json`.
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


class PosicaoCotaFundo(Auditable, Base):
    """Posicao de carteira em cota de fundo externo numa data."""

    __tablename__ = "wh_posicao_cota_fundo"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_posicao_cota_fundo"
        ),
        # Indice composto canonico para filtros de BI (por tenant + data).
        Index(
            "ix_wh_posicao_cota_fundo_tenant_data",
            "tenant_id",
            "data_posicao",
        ),
        # Drill-down "todas as posicoes de uma carteira".
        Index(
            "ix_wh_posicao_cota_fundo_tenant_carteira",
            "tenant_id",
            "carteira_cliente_doc",
            "data_posicao",
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

    # -- Quando --------------------------------------------------------------
    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # -- Carteira (quem investe) --------------------------------------------
    carteira_cliente_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    carteira_cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # CNPJ sem mascara (14 digitos). String pra preservar zeros a esquerda.
    carteira_cliente_doc: Mapped[str] = mapped_column(
        String(14), nullable=False, index=True
    )
    carteira_cliente_sac: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    # -- Ativo (no que investe) ---------------------------------------------
    # `codigo` na QiTech vai de numerico puro ("739704") ate alphanum interno
    # ("REALIAVE"). Mantem string.
    ativo_codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ativo_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    ativo_instituicao: Mapped[str] = mapped_column(String(100), nullable=False)

    # -- Fatos: quantidade --------------------------------------------------
    # Cotas podem ter muitos decimais (observado 8 em amostra: 18892619.39422062).
    quantidade: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    quantidade_bloqueada: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), nullable=False, default=0
    )

    # -- Fatos: cota e valores monetarios (R$) ------------------------------
    # valorDaCota pode ter alta precisao (cota de ETF com varios decimais).
    valor_cota: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    # "valorAplicação/resgate" — delta de movimento no dia (pode ser negativo
    # em resgate). Observado como inteiro 0 em dias sem movimento.
    valor_aplicacao_resgate: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0
    )
    valor_atual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_impostos: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0
    )
    valor_liquido: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # -- Fatos: percentuais (sempre em % — ja multiplicados, 175.64 = 175.64%)
    percentual_sobre_fundos: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
    # Pode ser > 100% quando a carteira tem passivo alavancado — nao clampar.
    percentual_sobre_total: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )

    # `source_updated_at` do Auditable carrega o timestamp do envelope da
    # QiTech (posicao do dia). Nao adicionar colunas especulativas — disciplina
    # do warehouse. Novos campos exigem migration.
