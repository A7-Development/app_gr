"""CreditDossierRedFlag — centralized red flags raised across the dossie."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class CreditDossierRedFlag(Base):
    """A red flag raised by an agent or analyst during analysis."""

    __tablename__ = "credit_dossier_red_flag"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    dossier_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_dossier.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional link to which section produced the flag (matches analysis.section).
    section: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    severity: Mapped[str] = mapped_column(String(32), nullable=False)  # 'critical' | 'important' | 'informational'
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)

    raised_by_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Proveniencia estruturada (handoff esteira-credito §1) ────────────
    # A unidade-produto da esteira e a FLAG DE CRUZAMENTO com proveniencia
    # rastreavel: "qual campo, de qual fonte, divergiu". `evidence` (acima)
    # continua sendo a narrativa humana; os campos abaixo sao a trilha
    # estruturada e auditavel.

    # Nome do check deterministico que disparou a flag (ex.:
    # "capital_proportionality", "ownership_sum"). Indexado pra responder
    # "todas as flags do tipo X". NULL quando levantada por agente/analista
    # em texto livre (compat).
    check_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Objeto canonico da divergencia. Chaves:
    #   check_type:   str
    #   source:       str   ("self_declared:cadastro", "official:receita", ...)
    #   field:        str   (campo que divergiu)
    #   expected_value / actual_value: any (familia "declarado x oficial")
    #   comparisons:  list[{source, field, value}]  (familia "cross-fonte")
    #   detail:       dict  (extras especificos do check)
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Liga a flag a entrada de decision_log (RULE_EVALUATION) que registrou
    # a avaliacao do cruzamento — fecha a trilha de auditoria (§14).
    decision_log_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("decision_log.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Status by analyst: was this flag accepted, dismissed, addressed?
    analyst_resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    analyst_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<CreditDossierRedFlag severity={self.severity} title={self.title!r}>"
