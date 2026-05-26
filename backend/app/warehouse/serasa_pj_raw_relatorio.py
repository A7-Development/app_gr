"""wh_serasa_pj_raw_relatorio -- camada raw (bronze) das consultas Serasa PJ.

Padrao raw -> canonico definido no CLAUDE.md secao 13.2. Esta tabela
armazena o **payload cru** que a Serasa devolveu para cada consulta de
CNPJ. Imutavel apos gravacao — diferente das raws QiTech (que tem UQ
por dia + upsert), aqui cada consulta gera linha nova.

Granularidade: 1 linha por consulta. Sem unique constraint — duas
consultas do mesmo CNPJ no mesmo dia geram duas linhas (analista pode
querer comparar lados-a-lado, ou time-series mostra evolucao do score).

NAO usa mixin `Auditable` (CLAUDE.md secao 14.1, excecao explicita): a
raw E a fonte; nao referencia outra fonte upstream. Proveniencia da raw
e direta — `fetched_at` + `fetched_by_version` + `payload_sha256`.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import Environment


class SerasaPjRawRelatorio(Base):
    """Payload cru de uma consulta Business Information Report (PJ)."""

    __tablename__ = "wh_serasa_pj_raw_relatorio"
    __table_args__ = (
        # "Ultima consulta do CNPJ X no tenant Y" — query critica para o
        # modulo credito (cache de janela), gestao de risco (time-series).
        Index(
            "ix_wh_serasa_pj_raw_relatorio_tenant_cnpj_fetched",
            "tenant_id",
            "cnpj",
            text("fetched_at DESC"),
        ),
        # Relay Bitfin (2026-05-26): idempotencia + watermark. Composto por
        # (tenant_id, bitfin_consulta_id) porque cada UNLTD_<cliente> tem sua
        # propria sequencia de ConsultaFinanceiraId — o id sozinho colidiria
        # entre tenants. Parcial: so linhas vindas do relay (bitfin_consulta_id
        # NOT NULL); consultas diretas a Serasa ficam de fora.
        Index(
            "uq_serasa_pj_raw_bitfin_consulta",
            "tenant_id",
            "bitfin_consulta_id",
            unique=True,
            postgresql_where=text("bitfin_consulta_id IS NOT NULL"),
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

    # `requested_report` = o que pedimos no body. `actual_report_returned`
    # = o que a Serasa devolveu no `reportName`. Diferenca indica downgrade
    # de reciprocidade — silver `wh_serasa_pj_consulta.reciprocity_downgrade`
    # e flag derivada disso.
    requested_report: Mapped[str] = mapped_column(String(64), nullable=False)
    actual_report_returned: Mapped[str] = mapped_column(
        String(64), nullable=False
    )

    environment: Mapped[Environment] = mapped_column(
        SAEnum(
            Environment, name="environment", native_enum=False, length=16
        ),
        nullable=False,
    )
    status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # X-Cost-Center que mandamos pra Serasa (rastreio interno: dossie_id,
    # workflow_run_id truncado). NULL quando consulta foi disparada fora
    # de um contexto identificavel.
    cost_center: Mapped[str | None] = mapped_column(
        String(12), nullable=True
    )

    # Quem disparou a consulta — `system:scheduler`, `user:<id>`,
    # `workflow_run:<id>`, `dossie:<id>`. Texto livre, util pra debug.
    triggered_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # Body cru da Serasa. JSONB pra indexar caminhos especificos depois
    # (ex.: GIN em `payload->'scoring'`) sem migration.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # SHA256 do payload bruto. Detecta re-fetch redundante (mesmo CNPJ +
    # mesmo body — comparacao byte-perfect entre re-consultas).
    payload_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )

    # Latencia da chamada — observabilidade barata.
    latency_ms: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 1), nullable=True
    )

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    fetched_by_version: Mapped[str] = mapped_column(
        String(128), nullable=False
    )

    # Origem Bitfin relay (2026-05-26): quando a consulta veio replicada do
    # Bitfin (dbo.ConsultaFinanceira) em vez de chamada direta a Serasa,
    # guarda o ConsultaFinanceiraId de origem. NULL = consulta direta (API do
    # GR). Serve de chave de idempotencia + watermark (MAX por tenant) do relay.
    bitfin_consulta_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
