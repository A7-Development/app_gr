"""DataProviderDatasetPriceHistory: append-only de mudancas de preco.

Tabela `provedor_dados_dataset_preco_historico`. Cada row e um snapshot de
preco para uma faixa especifica de um dataset, em um momento detectado pelo
sync.

Modelo append-only (CLAUDE.md §14): nunca atualiza, sempre insere. Quando o
preco de uma faixa muda, gravamos nova row com `previous_price_brl` apontando
para o valor anterior. Range query "qual era o preco em DD/MM" e indexavel
por `(dataset_id, tier_index, observed_at)`.

Tipos de evento (campo `kind`):
    - INITIAL: primeira observacao do preco daquela faixa (descoberta no 1o
      sync que viu o dataset).
    - DELTA: mudanca detectada — preco diferente do que estava registrado em
      `provedor_dados_dataset.pricing_tiers_json` quando o sync rodou.
    - MANUAL: override do mantenedor (reservado, ainda nao implementado).

Nao e gerado para datasets novos descobertos sem preco (`pricing_tiers_json`
do BDC veio NULL). Sem dado nao ha o que historizar.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.data_providers.enums import PriceChangeKind


class DataProviderDatasetPriceHistory(Base):
    """Snapshot de preco de uma faixa de um dataset, em um momento."""

    __tablename__ = "provedor_dados_dataset_preco_historico"
    __table_args__ = (
        Index(
            "ix_provedor_dados_preco_dataset_tier_observed",
            "dataset_id",
            "tier_index",
            "observed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    dataset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provedor_dados_dataset.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Indice da faixa dentro do `pricing_tiers_json` (0 = 1a faixa, 1 = 2a, ...).
    # Faixa = (up_to_quantity, price_brl). Identifica unicamente qual ponto
    # da escada esta sendo registrado.
    tier_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Limite superior da faixa (quantidade ate a qual o preco vale). NULL pra
    # faixa final aberta (ex.: "5M+" no BDC vira NULL aqui).
    up_to_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    price_brl: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=6), nullable=False
    )
    # Preco anterior — NULL pra INITIAL, preenchido pra DELTA. Permite
    # calcular delta direto sem JOIN com a row predecessora.
    previous_price_brl: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=6), nullable=True
    )

    kind: Mapped[PriceChangeKind] = mapped_column(
        SAEnum(
            PriceChangeKind,
            name="price_change_kind",
            native_enum=False,
            length=16,
        ),
        nullable=False,
    )

    # Origem da observacao. Pra INITIAL/DELTA = "bdc_pricing_api" (ou
    # equivalente do vendor). Pra MANUAL = "user:<uuid>". String aberta
    # propositalmente — futuras fontes (revisao manual, ajuste automatico
    # por moeda, etc.) entram sem migration.
    source: Mapped[str] = mapped_column(String(64), nullable=False)

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sync_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provedor_dados_sync_run.id", ondelete="SET NULL"),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PriceHistory id={self.id} dataset_id={self.dataset_id} "
            f"tier={self.tier_index} kind={self.kind.value} "
            f"price={self.price_brl}>"
        )
