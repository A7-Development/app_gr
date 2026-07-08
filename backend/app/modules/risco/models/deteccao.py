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
    """Human verdict on one scored unit."""

    FRAUDE = "fraude"
    OK = "ok"


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
