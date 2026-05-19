"""EndpointDateState: state machine por (endpoint, data) — F1 do refactor de sync.

Substitui o emaranhado de 4 mecanismos legados (daily scheduler + reconciler +
watermark scanner + refresh_complete job) por 1 unico modelo: cada combinacao
de (tenant, source, env, ua, endpoint, data_referencia) tem 1 linha aqui que
representa "qual e o estado deste dia, e quando devemos tentar de novo".

Ver `project_qitech_sync_state_machine` memory pro contexto e os 5 bugs
encadeados que motivaram o refactor.

Fluxo basico:
1. Job nightly cria rows `NOT_STARTED` pros dias uteis esperados (30 retro +
   5 a frente), pulando fim-de-semana e feriado via wh_dim_dia_util.
2. Scheduler tick (1min) faz SELECT WHERE next_attempt_at <= now AND state
   NOT IN ('complete', 'in_flight', 'abandoned') ORDER BY next_attempt_at
   LIMIT N e despacha cada row.
3. Worker marca IN_FLIGHT, chama run_sync_endpoint(since=data_referencia),
   atualiza state + next_attempt_at via politica de backoff (ESPERADO 30min,
   ATRASADO 2h, SUSPEITO 12h, FURO ABANDONED).
4. COMPLETE com TTL: next_attempt_at recalculado pra detectar republicacao
   do vendor apos refresh_complete_window_business_days.
5. ABANDONED: terminal. UI permite reset manual com trilha em decision_log.

Historico de attempts NAO e armazenado aqui — sobrescreve last_* a cada
tentativa. Trilha completa fica em decision_log (1 entry por attempt).
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import Environment, SourceType


class EndpointDateState(Base):
    """1 row por (tenant, source, env, ua, endpoint, data_referencia).

    Padrao de chave segue TenantSourceEndpointConfig e BackfillJob — UA
    nullable, sem empresa_id (tech debt cobrindo todo o bounded context;
    ver memory `wh_estoque_recebivel_sem_empresa_id`).

    States:
        not_started   — row criada pelo nightly, ainda nao tentada.
                        next_attempt_at = now() (entra na fila imediato).
        in_flight     — worker pegou e esta processando. Equivale a lock.
                        Outros workers nao podem pegar (filtrado no SELECT).
        complete      — http=200 + completeness=complete. next_attempt_at
                        recalculado via refresh_complete_window_business_days
                        pra detectar republicacao do vendor.
        empty         — http=200 + completeness=empty. Pode virar complete
                        quando vendor publicar.
        partial       — http=200 + completeness=partial. Idem.
        not_published — http != 200 (caso 5 endpoints presos REALINVEST).
        abandoned     — passou give_up_business_days. Terminal.
                        next_attempt_at = NULL. UI permite reset manual.
    """

    __tablename__ = "endpoint_date_state"
    __table_args__ = (
        # Chave logica: 1 row por (tenant, source, env, ua, endpoint, data).
        # UA NULL coexiste por NULLS NOT DISTINCT (acompanha politica TSEC).
        UniqueConstraint(
            "tenant_id",
            "source_type",
            "environment",
            "unidade_administrativa_id",
            "endpoint_name",
            "data_referencia",
            name="uq_endpoint_date_state",
        ),
        CheckConstraint(
            "state IN ("
            "'not_started', 'in_flight', 'complete', 'empty', "
            "'partial', 'not_published', 'abandoned'"
            ")",
            name="ck_endpoint_date_state_state",
        ),
        CheckConstraint(
            "attempts_count >= 0",
            name="ck_endpoint_date_state_attempts_nonneg",
        ),
        CheckConstraint(
            "backoff_seconds IS NULL OR backoff_seconds >= 0",
            name="ck_endpoint_date_state_backoff_nonneg",
        ),
        # next_attempt_at NULL apenas em estados terminais. complete tem
        # next_attempt_at calculado pelo TTL; abandoned tem NULL ate reset.
        # Outros estados sempre tem next_attempt_at (mesmo que no passado,
        # significando "pega na proxima rodada").
        CheckConstraint(
            "(state = 'abandoned' AND next_attempt_at IS NULL) "
            "OR (state != 'abandoned')",
            name="ck_endpoint_date_state_terminal_next_attempt",
        ),
        # Index parcial pro scheduler tick — exclui estados que nao
        # entram na fila (complete e in_flight sao cobertos pela query
        # WHERE state NOT IN; o index parcial reduz tamanho/cost).
        # abandoned tem next_attempt_at IS NULL — naturalmente nao aparece.
        Index(
            "ix_endpoint_date_state_dispatch",
            "next_attempt_at",
            postgresql_where=(
                "state NOT IN ('complete', 'in_flight', 'abandoned')"
            ),
        ),
        # Lookup por (endpoint, data) — usado pelo job nightly pra
        # INSERT ON CONFLICT DO NOTHING e pela UI pra montar grade.
        Index(
            "ix_endpoint_date_state_endpoint_date",
            "tenant_id",
            "source_type",
            "endpoint_name",
            "data_referencia",
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
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type", native_enum=False, length=64),
        ForeignKey("source_catalog.source_type"),
        nullable=False,
    )
    environment: Mapped[Environment] = mapped_column(
        SAEnum(Environment, name="environment", native_enum=False, length=16),
        nullable=False,
        default=Environment.PRODUCTION,
        server_default=Environment.PRODUCTION.name,
    )
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
        ),
        nullable=True,
        index=True,
    )

    endpoint_name: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    data_referencia: Mapped[date] = mapped_column(
        Date, nullable=False, index=True
    )

    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="not_started"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_completeness: Mapped[str | None] = mapped_column(String(16), nullable=True)
    backoff_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
            f"<EndpointDateState tenant={self.tenant_id} "
            f"endpoint={self.endpoint_name} data={self.data_referencia} "
            f"state={self.state} attempts={self.attempts_count} "
            f"next={self.next_attempt_at}>"
        )
