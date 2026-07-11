"""Detection-model spine: catalog, immutable versions, scores and curation tags.

Multi-model backbone of the anti-fraud program (handoff 2026-07-08, memoria
project_deteccao_anomalias_liquidacao). The boleto-liquidation model is the
FIRST row of the catalog, not a table of its own — Benford, taxa x
inadimplencia and the graph models join the same spine later.

Design decisions (aligned with Ricardo before code):
    - `deteccao_modelo` is a GLOBAL catalog (no tenant_id — like
      source_catalog): it defines WHAT a model is, not what it learned.
    - `deteccao_modelo_versao` is TENANT-scoped and immutable: coefficients
      are learned from tenant data. For logistic regression the coefficients
      ARE the model — stored as auditable JSONB, no pickle, no artifact
      store (MLflow deliberately rejected for v1).
    - Activation is an explicit act (`deteccao_modelo_ativo` pointer, 1-click
      rollback, ai_prompt_active pattern). A freshly trained version is
      born INACTIVE. This intentionally diverges from the contract's
      "highest version wins": training must never self-promote.
    - `curadoria_tag` is APPEND-ONLY (no UPDATE/DELETE — hard handoff rule):
      tags are human verdicts (IA opina, humano homologa); the latest tag
      per (modelo, liquidacao) wins for training. System suggestions are
      NEVER written here — they live in scores/flags.
    - `deteccao_score` keeps ONE row per (tenant, modelo, liquidacao),
      overwritten on re-score by a newer active version; scoring runs are
      logged in decision_log for history.
"""

import enum
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TipoModeloDeteccao(enum.StrEnum):
    """Nature of a detection model (mixed natures share the spine)."""

    SUPERVISIONADO = "supervisionado"
    REGRA = "regra"
    NAO_SUPERVISIONADO = "nao_supervisionado"


class CuradoriaTagValor(enum.StrEnum):
    """Human verdict on one scored unit.

    NEUTRO is a first-class verdict, not an absence: append-only means a tag
    is never deleted, so "un-marking" is a NEW row valued NEUTRO that becomes
    the vigente — the row returns to neutral WITHOUT losing the audit trail
    of who marked/unmarked and when (feedback Ricardo 2026-07-08). NEUTRO as
    the latest tag = the event behaves as untagged (not fraude, not ok).
    """

    FRAUDE = "fraude"
    OK = "ok"
    NEUTRO = "neutro"


class DeteccaoModelo(Base):
    """Catalog of detection models (GLOBAL table — no tenant_id on purpose)."""

    __tablename__ = "deteccao_modelo"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # Stable machine name referenced by decision_log rule_or_model
    # (e.g. 'liquidacao_boleto', 'lastro_inconsistente').
    nome: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    alvo: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[TipoModeloDeteccao] = mapped_column(
        SAEnum(TipoModeloDeteccao, native_enum=False, length=24), nullable=False
    )
    # Module tag (RBAC/billing grouping — CLAUDE.md §11.1), not a folder.
    modulo: Mapped[str] = mapped_column(String(24), nullable=False, default="risco")
    # Grain the model scores ('wh_liquidacao' for the boleto model).
    unidade: Mapped[str] = mapped_column(String(64), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<DeteccaoModelo {self.nome!r} tipo={self.tipo}>"


class DeteccaoModeloVersao(Base):
    """One immutable trained version of a model for one tenant.

    `coeficientes` payload for a logistic model:
        {"intercept": float,
         "features": {"<nome>": {"coef": float, "media": float, "desvio": float}},
         "engine": "sklearn.LogisticRegression", "engine_version": "..."}
    Standardization params travel WITH the version so scoring is
    self-contained and reproducible.
    """

    __tablename__ = "deteccao_modelo_versao"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "modelo_id", "versao", name="uq_deteccao_modelo_versao"
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    modelo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("deteccao_modelo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False)

    coeficientes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    # Out-of-time evaluation: {"gini": ..., "ks": ..., "precision_at_20": ...,
    #  "janela_treino": [ini, fim], "janela_teste": [ini, fim]}
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    n_amostras: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_positivos: Mapped[int | None] = mapped_column(Integer, nullable=True)

    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    trained_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    notas: Mapped[str | None] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        return f"<DeteccaoModeloVersao modelo={self.modelo_id} v={self.versao}>"


class DeteccaoModeloAtivo(Base):
    """Active-version pointer per (tenant, modelo) — 1-click rollback."""

    __tablename__ = "deteccao_modelo_ativo"
    __table_args__ = (
        UniqueConstraint("tenant_id", "modelo_id", name="uq_deteccao_modelo_ativo"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    modelo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("deteccao_modelo.id", ondelete="CASCADE"),
        nullable=False,
    )
    versao_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("deteccao_modelo_versao.id", ondelete="RESTRICT"),
        nullable=False,
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    activated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<DeteccaoModeloAtivo modelo={self.modelo_id} versao={self.versao_id}>"


class DeteccaoScore(Base):
    """Latest score of one unit by one model (re-scored in place).

    `fatores` = top contributions for explainability (CLAUDE.md §14.3):
        [{"feature": "pago_na_agencia_do_cedente", "contrib": 2.31}, ...]
    `features` = the full input vector snapshot (audit + reproducible
    training set without re-deriving history).
    """

    __tablename__ = "deteccao_score"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "modelo_id", "liquidacao_id", name="uq_deteccao_score_unidade"
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    modelo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("deteccao_modelo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    versao_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("deteccao_modelo_versao.id", ondelete="SET NULL"),
        nullable=True,
    )
    liquidacao_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_liquidacao.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # NULL score with regra_dura=true = deterministic rule fired before any
    # trained version exists (rules never wait for training).
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    fatores: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    features: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    regra_dura: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regra_dura_motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<DeteccaoScore liq={self.liquidacao_id} score={self.score}>"


class CuradoriaTag(Base):
    """Human verdict on one liquidation for one model — APPEND-ONLY.

    Hard handoff rule: rows are never updated nor deleted; a re-tag is a new
    row and the most recent one wins for training. `autor` is NOT NULL —
    an anonymous verdict is worthless for audit.
    """

    __tablename__ = "curadoria_tag"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    modelo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("deteccao_modelo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    liquidacao_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_liquidacao.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tag: Mapped[CuradoriaTagValor] = mapped_column(
        SAEnum(CuradoriaTagValor, native_enum=False, length=16), nullable=False
    )
    nota: Mapped[str | None] = mapped_column(String(512), nullable=True)
    autor: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<CuradoriaTag liq={self.liquidacao_id} tag={self.tag}>"


class SeveridadeSinal(enum.StrEnum):
    """Severity scale of the deterministic signal catalog (framework
    2026-07-10). CRITICA floors the future liquidation rating on its own
    (the retired "regra dura" concept lives here now)."""

    CRITICA = "critica"
    # Critico PENDENTE de curadoria: sinal ambiguo trava a nota ate um humano
    # liberar (tag OK) ou confirmar (tag FRAUDE) — decisao Ricardo 2026-07-11.
    PENDENTE = "pendente"
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class StatusSinal(enum.StrEnum):
    """Lifecycle of a catalog signal. REFUTADO is kept on purpose (audit
    trail of dead ends — prevents reintroduction)."""

    ATIVO = "ativo"
    PLANEJADO = "planejado"
    REFUTADO = "refutado"


class DeteccaoSinal(Base):
    """Canonical catalog of deterministic liquidation signals (one stable
    code per atomic/composite fact — PRC-01, CNV-90...).

    GLOBAL like `deteccao_modelo` (no tenant_id): defines WHAT a signal is.
    `feature_name` maps the code to the persisted feature vector of
    `deteccao_score.features` when a 1:1 mapping exists; composite or
    not-yet-implemented signals carry NULL and explain themselves in
    `definicao`. Severity/threshold VALUES are parameters — they live in
    `deteccao_parametro`, never hardcoded (decisao Ricardo 2026-07-10).
    """

    __tablename__ = "deteccao_sinal"

    codigo: Mapped[str] = mapped_column(String(12), primary_key=True)
    familia: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    definicao: Mapped[str] = mapped_column(String(600), nullable=False)
    severidade: Mapped[SeveridadeSinal] = mapped_column(
        SAEnum(SeveridadeSinal, native_enum=False, length=8), nullable=False
    )
    status: Mapped[StatusSinal] = mapped_column(
        SAEnum(StatusSinal, native_enum=False, length=10), nullable=False
    )
    feature_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<DeteccaoSinal {self.codigo} sev={self.severidade}>"


class DeteccaoParametro(Base):
    """Versioned parameters of the detection engine (premise_set pattern:
    APPEND-ONLY, active = highest version per name — no UPDATE, 1-row
    rollback by inserting the old value as a new version).

    Kills the hardcoded constants (decisao Ricardo 2026-07-10): thresholds,
    windows and structural rules live here with author + reason. GLOBAL
    (no tenant_id — engine configuration, like deteccao_sinal).
    """

    __tablename__ = "deteccao_parametro"
    __table_args__ = (
        UniqueConstraint("nome", "version", name="uq_deteccao_parametro_nome_version"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    nome: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    # JSONB: numero, string ou estrutura ({"codigo": "00001"}) — o loader
    # devolve o valor cru; quem consome sabe o tipo que espera.
    valor: Mapped[Any] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<DeteccaoParametro {self.nome}@v{self.version}>"
