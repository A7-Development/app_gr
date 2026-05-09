"""wh_dim_dia_util -- calendario de dias uteis (ANBIMA-style).

Serve as analises da L2 Operacoes que dependem de "dia util" (DU):
- "Estamos X% a frente/atras do mes anterior no mesmo nº de dias uteis"
- Pace diario (VOP / DU corridos)
- Heatmap dia-da-semana x semana-do-mes
- VOP por DU medio do periodo

Fonte: Bitfin `VW_FERIADOS_NACIONAL` (apenas datas, sem nome do feriado).
Populacao: script `backend/scripts/populate_dia_util.py` faz seed inicial e
re-popula quando feriados sao adicionados.

Granularidade: 1 linha por (tenant_id, data). Cobertura recomendada: 2019-01-01
ate 2030-12-31 (~12 anos = ~4400 linhas/tenant).

Indices precomputados (vs derivar em SQL toda query):
- `dia_util_index_no_mes`: 1, 2, 3... so quando `eh_dia_util=true`. Util para
  alinhar "vs mesmo DU do mes anterior" sem subquery RANK().
- `total_dias_uteis_no_mes`: igual em todas as linhas do mesmo mes — util
  para projecao linear de fim do mes.
- `semana_do_mes`: 1..5, calculado como CEIL(day_of_month / 7) — usado no
  heatmap dow x semana.

Decisao de NAO usar Auditable: a fonte (`VW_FERIADOS_NACIONAL`) tem apenas
datas, sem timestamp de atualizacao no Bitfin. O ETL e idempotente por
`(tenant_id, data)`. `source_type` e `ingested_by_version` sao mantidos
inline para rastreabilidade minima.
"""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DimDiaUtil(Base):
    """Calendario diario com flag de dia util + indices precomputados."""

    __tablename__ = "wh_dim_dia_util"
    __table_args__ = (UniqueConstraint("tenant_id", "data", name="uq_wh_dim_dia_util"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    data: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Dia da semana (1=Segunda ... 7=Domingo, ISO 8601).
    dia_da_semana: Mapped[int] = mapped_column(Integer, nullable=False)
    dia_da_semana_nome: Mapped[str] = mapped_column(String(20), nullable=False)

    eh_fim_de_semana: Mapped[bool] = mapped_column(Boolean, nullable=False)
    eh_feriado_nacional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, index=True
    )
    eh_dia_util: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)

    # Indices precomputados.
    # `dia_util_index_no_mes`: 1..N quando eh_dia_util; NULL caso contrario.
    dia_util_index_no_mes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # `total_dias_uteis_no_mes`: contagem de DUs do mes corrente; igual em todas as
    # linhas do mesmo mes (mesmo nas que nao sao DU).
    total_dias_uteis_no_mes: Mapped[int] = mapped_column(Integer, nullable=False)
    # `semana_do_mes`: 1..5, CEIL(day_of_month / 7). Heatmap dow x semana.
    semana_do_mes: Mapped[int] = mapped_column(Integer, nullable=False)

    # Rastreabilidade minima — sem mixin Auditable (ver docstring do modulo).
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="DERIVED")
    ingested_at: Mapped["date"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ingested_by_version: Mapped[str] = mapped_column(String(128), nullable=False)
