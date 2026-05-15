"""TenantSourceEndpointConfig: per-tenant cadence for ONE endpoint of a source.

Granularidade fina introduzida em 2026-05-05 (ver
`docs/cadencia-por-endpoint.md` ou plano em
`C:\\Users\\RicardoPimenta\\.claude\\plans\\starry-moseying-phoenix.md`).

Modelo paralelo a `TenantSourceConfig`:
    - TSC  (tenant_source_config)         → credenciais + flag enabled global
    - TSEC (tenant_source_endpoint_config) → cadencia por endpoint

Uma linha em TSEC representa "tenant T configurou o endpoint E do source S no
ambiente Env e UA U para rodar com kind/value". Catalogo de endpoints validos
vive em codigo (`<adapter>/endpoint_catalog.py`); este modelo so persiste
overrides + state de execucao (last_sync_*).

`schedule_kind`/`schedule_value` semanticas:
    - `interval` + value = "60"   → roda a cada 60 minutos
    - `daily_at` + value = "07:00" → roda diariamente as 07:00 SP
    - `on_demand` + value = NULL  → nao entra no scheduler dispatcher

Ver `app/shared/endpoint_catalog.py::ScheduleKind` para o enum canonico.

Owned by `integracoes` module. Outros modulos consultam via
`integracoes.public.list_enabled_endpoint_configs()`.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import Environment, SourceType


class TenantSourceEndpointConfig(Base):
    """Per-tenant cadence configuration for a single endpoint of a source.

    Chave logica: (tenant_id, source_type, environment, unidade_administrativa_id,
    endpoint_name). Cada linha representa "como o tenant quer que ESTE endpoint
    seja sincronizado".

    Estado de execucao: `last_sync_started_at`/`last_sync_finished_at`/
    `last_sync_status`/`last_sync_error` carimbados pelo `run_sync_endpoint`
    em sync_runner. Substitui o `last_sync_started_at` que vivia em
    `tenant_source_config` (granular demais).
    """

    __tablename__ = "tenant_source_endpoint_config"
    __table_args__ = (
        # Mesma chave de TSC + endpoint_name. UA NULL coexiste por NULLS NOT
        # DISTINCT (acompanha politica do tenant_source_config).
        UniqueConstraint(
            "tenant_id",
            "source_type",
            "environment",
            "unidade_administrativa_id",
            "endpoint_name",
            name="uq_tenant_source_env_ua_endpoint",
        ),
        # Validacao do par (schedule_kind, schedule_value). Espelha o enum
        # ScheduleKind + range INTERVAL e formato DAILY_AT. Mesmo regex que a
        # validacao Pydantic na API + EndpointSpec.__post_init__ (defesa em
        # profundidade).
        CheckConstraint(
            "("
            "  schedule_kind = 'interval' "
            "  AND schedule_value ~ '^[0-9]+$' "
            "  AND schedule_value::int BETWEEN 15 AND 1440"
            ") OR ("
            "  schedule_kind = 'daily_at' "
            "  AND schedule_value ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'"
            ") OR ("
            "  schedule_kind = 'on_demand' "
            "  AND schedule_value IS NULL"
            ")",
            name="ck_tsec_schedule_value_format",
        ),
        # last_sync_status, quando preenchido, deve ser um dos tres valores
        # usuais — espelha o vocabulario usado em decision_log.explanation.
        CheckConstraint(
            "last_sync_status IS NULL OR "
            "last_sync_status IN ('ok', 'erro', 'em_progresso')",
            name="ck_tsec_last_sync_status",
        ),
        # Tolerance window monotonicity: quando os 3 overrides estao
        # preenchidos, expected <= tolerance <= give_up. NULL em qualquer
        # campo relaxa a comparacao correspondente (semantica: "segue default
        # do catalogo nesse lado").
        CheckConstraint(
            "("
            "  expected_lag_business_days_override IS NULL OR "
            "  expected_lag_business_days_override >= 0"
            ") AND ("
            "  expected_lag_business_days_override IS NULL OR "
            "  tolerance_business_days_override IS NULL OR "
            "  tolerance_business_days_override >= expected_lag_business_days_override"
            ") AND ("
            "  tolerance_business_days_override IS NULL OR "
            "  give_up_business_days_override IS NULL OR "
            "  give_up_business_days_override >= tolerance_business_days_override"
            ")",
            name="ck_tsec_tolerance_window_monotonic",
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

    # Identidade do endpoint dentro do source — convencao "<area>.<snake_case>"
    # (ex.: "market.outros_fundos", "bank_account.balance"). Validado contra o
    # catalogo declarativo em runtime (API rejeita PUT pra endpoint inexistente).
    endpoint_name: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )

    # Switch independente do TSC.enabled (toggle global da credencial). Mesmo
    # com credencial habilitada, operador pode desligar endpoint individual.
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )

    # Vide doc de modulo para semantica.
    schedule_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )
    schedule_value: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    # Estado de execucao — mantido aqui (e nao em decision_log) para consulta
    # rapida pela UI sem precisar fazer JOIN/agregacao por endpoint a cada
    # render do EndpointsTab.
    last_sync_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tolerance window overrides — NULL = "segue default do catalogo
    # (EndpointSpec)". Quando preenchido, sobrepoe o default sem mexer no
    # catalogo. Usado pelo compute_publication_state (services/coverage.py)
    # pra classificar cada (data, endpoint) em ESPERADO/ATRASADO/SUSPEITO/
    # FURO_DEFINITIVO. Reconciler le esse estado pra decidir cadencia de
    # retry. Ver migration `e8a2b9c4d167_tsec_tolerance_window.py`.
    expected_lag_business_days_override: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    tolerance_business_days_override: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    give_up_business_days_override: Mapped[int | None] = mapped_column(
        Integer, nullable=True
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
            f"<TenantSourceEndpointConfig tenant={self.tenant_id} "
            f"source={self.source_type.value} endpoint={self.endpoint_name} "
            f"kind={self.schedule_kind} value={self.schedule_value}>"
        )
