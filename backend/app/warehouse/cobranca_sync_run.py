"""wh_cobranca_sync_run -- rastreamento de execucoes do sync manual de cobranca.

Cada clique no botao "Sincronizar" da pagina banco-cobrador cria uma linha aqui.
O subprocess que roda o ciclo (coleta -> decode -> project) atualiza a `fase` +
`heartbeat_at` a cada etapa (sessao curta, commit imediato -> o polling enxerga
o progresso em tempo real) e marca `finished_at`/`status` no fim.

Serve para responder, na UI:
- "esta travado?": status='running' com heartbeat_at velho = subprocess morto.
- "qual foi a ultima sync?": ultima linha por tenant (started_at/finished_at).
- progresso: `fase` corrente + contadores.

Operacional (nao usa Auditable): nao e dado de dominio ingerido de fonte, e
metadado de execucao. Proveniencia simples (started_at/finished_at).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Status do run.
SYNC_STATUS_RUNNING = "running"
SYNC_STATUS_OK = "ok"
SYNC_STATUS_ERROR = "error"

# Fase corrente (heartbeat de progresso).
SYNC_FASE_COLETA = "coleta"      # lendo a inbox -> bronze + ocorrencias
SYNC_FASE_DECODE = "decode"      # bronze -> timeline (wh_boleto_evento)
SYNC_FASE_PROJECT = "project"    # timeline -> vigente (wh_boleto_vigente)
SYNC_FASE_DONE = "done"


class CobrancaSyncRun(Base):
    """Uma execucao do sync manual de cobranca (por tenant)."""

    __tablename__ = "wh_cobranca_sync_run"
    __table_args__ = (
        Index(
            "ix_wh_cobranca_sync_run_tenant_started",
            "tenant_id",
            "started_at",
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

    status: Mapped[str] = mapped_column(String(12), nullable=False)
    fase: Mapped[str | None] = mapped_column(String(12), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Heartbeat: atualizado a cada fase. Stale (> alguns min) com status=running
    # => subprocess provavelmente morreu.
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    arquivos_vistos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arquivos_novos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    boletos_ativos: Mapped[int | None] = mapped_column(Integer, nullable=True)

    erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Quem disparou: "user:<uuid>" (botao) ou "system:scheduler" (futuro).
    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
