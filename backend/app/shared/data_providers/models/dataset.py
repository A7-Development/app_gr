"""DataProviderDataset: catalogo dinamico de datasets de um provider.

Tabela `provedor_dados_dataset`. Cada row e UM produto vendavel do vendor
(ex.: BDC `lawsuits_distribution_data` em `/empresas`, BDC `processes` em
`/empresas`, Infosimples `consulta-cnpj`). Populada automaticamente pelo
sync de catalogo (`pricing_sync.py` para BDC) — nao e seed manual.

Schema separa duas camadas:

    - **Camada do vendor (sync-managed)**: `provider_dataset_code`,
      `provider_api`, `current_cost_brl`, `pricing_tiers_json`,
      `last_synced_at`. Reescritas pelo sync.

    - **Camada A7 (curadoria do mantenedor)**: `display_name_pt_br`,
      `categoria_ui`, `description_pt_br`, `enabled_for_sale`,
      `markup_pct`. NAO sao sobrescritas pelo sync — preservadas entre runs.

Convencao de unicidade: `(provider_id, provider_dataset_code, provider_api)`.
O mesmo `code` pode existir em APIs diferentes do mesmo vendor (BDC tem
`basic_data` em `/people` e em `/empresas` como datasets distintos).
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DataProviderDataset(Base):
    """Um dataset (produto vendavel) de um provider."""

    __tablename__ = "provedor_dados_dataset"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "provider_dataset_code",
            "provider_api",
            name="uq_provedor_dados_dataset_code_api",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    provider_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provedor_dados.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ─── Camada do vendor (overwrite pelo sync) ──────────────────────────────

    # Nome tecnico do dataset (ex.: "lawsuits_distribution_data", "processes",
    # "basic_data"). Vai literal no body POST do BDC em `Datasets`.
    provider_dataset_code: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )

    # Path/API do vendor onde este dataset vive (ex.: "Companies", "People",
    # "Validations"). No BDC corresponde ao endpoint POST `/empresas`,
    # `/pessoas`, etc. Preservado como devolvido pelo /precos/.
    provider_api: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )

    # Preco da 1a faixa (mais cara). E o preco "nominal" do dataset, valor que
    # vai pra UI quando nao houver Quantity especifica. NULL quando o vendor
    # nao informa preco (raro — geralmente tem).
    current_cost_brl: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=6), nullable=True
    )

    # Escada de precos completa, formato vendor-shape:
    #   [{"up_to_quantity": 10000, "price_brl": 0.050},
    #    {"up_to_quantity": 50000, "price_brl": 0.048}, ...]
    # NULL quando o vendor nao expoe escada.
    pricing_tiers_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Carimbos do sync. last_synced_at = ultima vez que /precos/ confirmou
    # este dataset. last_diff_at = ultima vez que algum campo mudou (preco,
    # status, schema). Usados na UI pra mostrar "atualizado ha X" e
    # "estavel ha Y".
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_diff_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Status reportado pelo vendor (ex.: "active", "deprecated"). Texto livre
    # — vendor define o vocabulario.
    provider_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ─── Camada A7 (curadoria do mantenedor — preservada entre syncs) ────────

    # Codigo NEUTRO (white-label) exposto ao TENANT no lugar do vendor — evita
    # engenharia reversa do provedor (decisao 2026-06-04). O tenant-facing ve
    # SO public_code + display_name; provider_slug/provider_dataset_code NUNCA
    # vazam pra UI/API do tenant. Mantenedor define (ex.: "CAD-PJ", "PEP-PF").
    public_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )

    # Nome TECNICO do dataset na QUERY (campo `Datasets` do POST /empresas).
    # Difere do `provider_dataset_code` (que vem do /precos como CODIGO de
    # billing, ex.: "BASIC_DATA_V1") — a query usa o nome tecnico minusculo
    # (ex.: "basic_data"). Curado pelo mantenedor (preservado entre syncs).
    # Quando NULL, o caller cai em `provider_dataset_code`.
    provider_query_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    # Label pt-BR pra UI. NULL na descoberta (1o sync) — mantenedor preenche
    # depois. UI cai em `provider_dataset_code` quando NULL.
    display_name_pt_br: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # Categoria de UI: "empresas" / "pessoas" / "veiculos" / "processos" /
    # "validacoes" / etc. Texto livre — agrupa visualmente, nao constraint.
    categoria_ui: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description_pt_br: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Switch mestre A7 — controla se este dataset e revendido. Default false
    # na descoberta: dataset novo do vendor nao aparece pra venda ate o
    # mantenedor revisar e habilitar.
    enabled_for_sale: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    # Multiplicador sobre `current_cost_brl` para calcular preco de venda
    # (sell_price_brl = cost_brl * (1 + markup_pct / 100)). Ex.: markup_pct
    # = 50.0 vira "50% de margem". NULL = sem markup definido (cobra cost).
    markup_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=6, scale=2), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<DataProviderDataset id={self.id} provider_id={self.provider_id} "
            f"code={self.provider_dataset_code!r} api={self.provider_api!r} "
            f"enabled_for_sale={self.enabled_for_sale}>"
        )
