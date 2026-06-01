"""CreditPolicy — tenant-scoped, versioned credit eligibility policy.

The credit policy is what the *manager* parametrizes for a fund: which
sectors (CNAE) are forbidden, the minimum capital social, and other
eligibility knobs. It is **separate from the analysis** (CLAUDE.md handoff
§8): analysis answers "is this credit good and real?"; the policy answers
"is this credit *allowed* by this fund?".

Mirrors the `ai_prompt` / `ai_prompt_active` governance model (§19.4):
each `(tenant_id, name, version)` is immutable once created; editing creates
a new version; `credit_policy_active` points at the version in production so
a manager can roll forward / roll back in one click without a deploy. The
trava (eligibility gate) records which policy version vetoed an entry, so
"why was this cedente refused in March?" has an auditable answer.

Multi-tenant (§10): every row carries `tenant_id`; the active pointer is
keyed per `(tenant_id, name)`.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class CreditPolicy(Base):
    """One immutable version of a fund's credit eligibility policy.

    `name` groups versions for a tenant — ex.: tenant X has policy 'default'
    with v1, v2, v3. The active version per `(tenant_id, name)` lives in
    `credit_policy_active`.
    """

    __tablename__ = "credit_policy"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", "version", name="uq_credit_policy_tenant_name_version"
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    version: Mapped[str] = mapped_column(String(32), nullable=False)

    # ── Eligibility knobs (MVP) ──────────────────────────────────────────
    # CNAEs vetados pelo fundo. Lista de codigos (string), ex.: ["12.20-4-99"].
    # Comparacao por prefixo/igualdade fica a cargo do check (ver
    # app/agentic/tools/credito/checks). Default: nada vetado.
    forbidden_cnae: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # Capital social minimo exigido (BRL). NULL = sem corte de capital.
    min_capital_social: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True
    )
    # Idade minima da empresa em anos (tempo de fundacao). Regra inicial da
    # politica (2026-06-01): so cedentes com > N anos de fundacao. NULL = sem
    # corte de idade. Lido pelo check `company_founding_age`.
    min_company_age_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Escape hatch tipado-fraco pra knobs futuros sem nova migration
    # (ex.: limites de concentracao, razao capital/limite minima, cortes de
    # faturamento). Cada check le as chaves que conhece.
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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

    # Soft-delete: versao nao-ativavel, historico preservado. Versao ativa
    # nao pode ser arquivada (enforced no service, espelha ai_prompt).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def full_id(self) -> str:
        """Identifier used in audit (`decision_log.rule_or_model_version`)."""
        return f"credit_policy:{self.name}@{self.version}"

    def __repr__(self) -> str:
        return f"<CreditPolicy {self.full_id} tenant={self.tenant_id}>"


class CreditPolicyActive(Base):
    """Points to the active version of each policy name, per tenant.

    One row per `(tenant_id, name)`. The eligibility gate resolves the active
    policy through this table; flipping `active_version` is the 1-click
    rollback (no deploy), mirroring `ai_prompt_active`.
    """

    __tablename__ = "credit_policy_active"

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    active_version: Mapped[str] = mapped_column(String(32), nullable=False)

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    changed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<CreditPolicyActive tenant={self.tenant_id} name={self.name!r} "
            f"version={self.active_version!r}>"
        )
