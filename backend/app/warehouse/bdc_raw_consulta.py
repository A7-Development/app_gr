"""wh_bdc_raw_consulta -- camada raw (bronze) das consultas BigDataCorp.

Padrao raw -> canonico definido no CLAUDE.md secao 13.2. Esta tabela
armazena o **payload cru** que o BDC devolveu para cada consulta on-demand
(ex.: `basic_data` da API de Empresas -> enriquecimento cadastral PJ do
modulo credito). Imutavel apos gravacao — cada consulta gera linha nova
(sem unique constraint), espelhando `wh_serasa_pj_raw_relatorio`.

White-label (decisao 2026-06-04): a raw guarda `public_code` (codigo
neutro exposto ao tenant) E `provider_api` + `datasets` (identidade do
vendor) porque ela e camada interna de auditoria — o vendor nunca vaza
pra UI/API do tenant, mas a trilha precisa saber de onde veio.

NAO usa mixin `Auditable` (CLAUDE.md secao 14.1, excecao explicita): a
raw E a fonte; nao referencia outra fonte upstream. Proveniencia da raw
e direta — `fetched_at` + `fetched_by_version` + `payload_sha256`.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BdcRawConsulta(Base):
    """Payload cru de uma consulta on-demand ao BigDataCorp."""

    __tablename__ = "wh_bdc_raw_consulta"
    __table_args__ = (
        # "Ultima consulta do CNPJ X no tenant Y" — query critica para o
        # modulo credito (cache de janela) e re-mapeamento sobre raw.
        Index(
            "ix_wh_bdc_raw_consulta_tenant_cnpj_fetched",
            "tenant_id",
            "cnpj",
            text("fetched_at DESC"),
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

    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)

    # Codigo NEUTRO (white-label) que o caller pediu — ex.: "CAD-PJ". Resolve
    # pra um dataset concreto via provedor_dados_dataset.public_code.
    public_code: Mapped[str] = mapped_column(String(64), nullable=False)
    # Identidade do vendor (interna): API + dataset code do BDC. Ex.:
    # provider_api="Companies", datasets="basic_data".
    provider_api: Mapped[str] = mapped_column(String(64), nullable=False)
    datasets: Mapped[str] = mapped_column(String(255), nullable=False)

    # QueryId devolvido pelo BDC — rastreio cruzado com a fatura do vendor.
    query_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # found = `Result` veio nao-vazio. status_code = HTTP. dataset_status_code
    # = Status.<dataset>[0].Code do BDC (0 = OK; encapsula erro no payload).
    found: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dataset_status_code: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )

    # Body cru do BDC. JSONB pra indexar caminhos especificos depois sem
    # migration (GIN em payload->'Result' etc).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # SHA256 do payload bruto — detecta re-fetch redundante.
    payload_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )

    latency_ms: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 1), nullable=True
    )

    # Quem disparou — `dossie:<id>`, `user:<id>`, `system:<job>`. Texto livre.
    triggered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    fetched_by_version: Mapped[str] = mapped_column(String(128), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<BdcRawConsulta cnpj={self.cnpj} public_code={self.public_code!r} "
            f"found={self.found}>"
        )
