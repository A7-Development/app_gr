"""qitech_report_job -- estado de execucao de relatorios assincronos QiTech.

Tabela operacional (NAO warehouse). Rastreia o ciclo de vida dos jobs
criados via POST /v2/queue/scheduler/report/{tipo} (familia FIDC Estoque,
FIDC Movimentacao, etc) — desde o WAITING ate o callback que traz o link
do arquivo S3.

Por que tabela separada (nao mistura com decision_log nem com raw):
- Estado MUTAVEL (status muda WAITING -> PROCESSING -> SUCCESS) — viola
  append-only do decision_log.
- Granularidade especifica (1 job = 1 par tipo+data+cnpj_fundo) — diferente
  de raw que e por payload-bruto-em-disco.
- Anti-spoof: o `callback_token` e HMAC do jobId; receiver valida sem
  consultar banco antes (defesa em profundidade).

Fluxo:
    1. POST /queue/scheduler/report/<tipo>
       -> insert (status=WAITING, qitech_job_id=<retornado>, callback_token=hmac)
    2. QiTech processa (~10s a varios minutos)
    3. POST callback /api/v1/integracoes/webhooks/qitech/job-callback?token=...
       -> validar token (HMAC anti-spoof)
       -> lookup por qitech_job_id (404 se nao existir)
       -> idempotencia: se result_downloaded_at preenchido, ignorar
       -> baixar fileLink, salvar em raw + canonico
       -> update status=SUCCESS, completed_at, raw_payload_id
    4. Polling cron periodico: detecta jobs WAITING > timeout -> status=TIMEOUT
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.enums import Environment


class QitechJobStatus(enum.StrEnum):
    """Estados do ciclo de vida de um job QiTech.

    Valores QITech: WAITING, PROCESSING, SUCCESS, CANCELED, ERROR.
    Adicionados por nos: TIMEOUT (job que ficou WAITING > N minutos sem
    callback — provavelmente perdido na fila).
    """

    WAITING = "WAITING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    CANCELED = "CANCELED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class QitechReportJob(Base):
    """Job de relatorio assincrono QiTech (tabela operacional)."""

    __tablename__ = "qitech_report_job"
    __table_args__ = (
        UniqueConstraint(
            "qitech_job_id", name="uq_qitech_report_job_qitech_job_id"
        ),
        # 1 job em aberto por (tenant, tipo, cnpj, data) -- previne disparos
        # duplicados acidentais. Postgres partial unique nao permite WHERE
        # status IN(...), entao usamos filter na app + indice composto.
        Index(
            "ix_qitech_report_job_lookup",
            "tenant_id",
            "report_type",
            "cnpj_fundo",
            "reference_date",
            "status",
        ),
        Index(
            "ix_qitech_report_job_status_created",
            "status",
            "created_at",
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
    environment: Mapped[Environment] = mapped_column(
        SAEnum(Environment, name="environment", native_enum=False, length=16),
        nullable=False,
    )

    # ---- Identificacao do job ----
    # Tipo da familia /queue/scheduler/report/{tipo}, ex.: "fidc-estoque".
    # Mantido como string (nao enum) pra absorver novos tipos sem migration.
    report_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # CNPJ do fundo alvo (do body do POST). 14 digitos sem mascara.
    cnpj_fundo: Mapped[str] = mapped_column(String(14), nullable=False, index=True)

    # Data de referencia do relatorio (do body do POST).
    reference_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Body completo do POST -- auditoria + replay.
    request_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # ---- Identificadores QiTech ----
    # Id retornado pela QiTech no POST (vem como `jobId`) e usado no callback
    # tambem como `jobId` (no GET /queue/job aparece como `taskId` -- mesmo
    # valor, nome diferente). Padronizamos como qitech_job_id internamente.
    qitech_job_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # `webhookId` numerico vindo no callback (id interno QiTech do webhook
    # delivery, util pra rastreamento cruzado com suporte da QiTech).
    qitech_webhook_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ---- Callback (anti-spoof) ----
    callback_url_used: Mapped[str] = mapped_column(Text, nullable=False)
    # HMAC-SHA256 truncado de qitech_job_id com QITECH_WEBHOOK_SECRET.
    # Receiver valida que o token na query string da URL bate com o
    # esperado para o jobId do body — sem essa info, atacante nao
    # consegue forjar callback mesmo conhecendo a URL base.
    callback_token: Mapped[str] = mapped_column(String(64), nullable=False)

    # ---- Estado ----
    status: Mapped[QitechJobStatus] = mapped_column(
        SAEnum(
            QitechJobStatus,
            name="qitech_job_status",
            native_enum=False,
            length=16,
        ),
        nullable=False,
        default=QitechJobStatus.WAITING,
        index=True,
    )

    # ---- Resultado (preenchido no callback SUCCESS) ----
    result_file_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Presigned S3 URL tem TTL ~24h da QiTech. Calculamos expiry pra
    # o polling/cron evitar tentar baixar links expirados.
    result_file_link_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Idempotencia: marcamos quando baixamos pra evitar re-processar
    # se a QiTech entregar callback duplicado (retry).
    result_downloaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # FK pro raw que ingerimos (NULL ate processarmos o callback com sucesso).
    raw_relatorio_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_qitech_raw_relatorio.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ---- Auditoria ----
    triggered_by: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
            f"<QitechReportJob id={self.id} tipo={self.report_type} "
            f"cnpj={self.cnpj_fundo} ref={self.reference_date} "
            f"status={self.status.value}>"
        )
