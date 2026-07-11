"""serpro_nfe_monitor -- chaves de NF-e vigiadas via SERPRO Push (F3).

Tabela OPERACIONAL (nao warehouse): estado mutavel do ciclo de monitoracao
de cada chave — espelha o papel da `qitech_report_job` para o adapter
QiTech.

Escopo (decisao Ricardo 2026-07-11): toda chave em `wh_nfe` com duplicata
a vencer (`wh_nfe_duplicata.vencimento >= hoje`). O job de enrolamento
insere aqui; o push do SERPRO avisa de evento novo; a consulta atualiza
bronze+silver; alerta quando a situacao vira cancelada/denegada.

Ciclo de vida:
    enrolado (ativo, sem solicitacao)
      -> inscrito no push (solicitacao_id + expira_em ~30d)
      -> renovado a cada ~25d enquanto no escopo
      -> encerrado (ativo=false) quando vencimento passa (carencia) ou a
         nota morre (cancelada) — nao renova a inscricao.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class SerproNfeMonitor(Base):
    """Chave de NF-e sob monitoramento SERPRO (1 linha por tenant+chave)."""

    __tablename__ = "serpro_nfe_monitor"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "chave_acesso", name="uq_serpro_nfe_monitor_tenant_chave"
        ),
        # Ping do webhook chega SO com a chave — lookup global por chave.
        Index("ix_serpro_nfe_monitor_chave", "chave_acesso"),
        Index("ix_serpro_nfe_monitor_ativo_expira", "ativo", "solicitacao_expira_em"),
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
    chave_acesso: Mapped[str] = mapped_column(String(44), nullable=False)

    # Por que esta chave entrou no escopo (hoje: "duplicata_a_vencer").
    motivo: Mapped[str] = mapped_column(String(32), nullable=False)
    # Maior vencimento das duplicatas da nota — define quando SAI do escopo.
    referencia_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)

    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )

    # ---- Inscricao push vigente ----
    solicitacao_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    solicitacao_expira_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ---- Telemetria do ciclo ----
    ultima_notificacao_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ultima_consulta_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Situacao do silver na ultima consulta (denormalizada pra job/painel).
    ultima_situacao: Mapped[str | None] = mapped_column(String(32), nullable=True)
    alertado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    encerrado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # "vencida" | "nota_morta" | "manual"
    encerrado_motivo: Mapped[str | None] = mapped_column(String(32), nullable=True)

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
            f"<SerproNfeMonitor chave={self.chave_acesso} ativo={self.ativo} "
            f"situacao={self.ultima_situacao}>"
        )
