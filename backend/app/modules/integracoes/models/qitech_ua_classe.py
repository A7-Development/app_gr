"""QiTechUaClasse: pre-registered catalog of fund cota classes per UA.

Reference/config table (NOT `Auditable` — it is not ingested external data;
it is the *expectation* the system holds about a UA's fund structure).

Each row declares one cota class of a fund administered by a UA, anchored on
the QiTech `clienteId` (the stable per-class code that is also the silver
business key `wh_mec_evolucao_cotas.carteira_cliente_id`). The catalog is the
oracle used by the QiTech completeness assessor (`adapters/admin/qitech/
completeness.py`): a `market/*` payload is `complete` only when every vigente
class expected for that endpoint is present AND value-sane.

`ativo_desde`/`ativo_ate` give each class a vigencia window. A class with
`ativo_ate` in the past is no longer expected — this resolves the
"publicacao atrasada vs. classe resgatada" ambiguity (a legitimately closed
class stops causing `partial` forever).

Owned by `integracoes` — only integracoes reads/writes this table.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class QiTechUaClasse(Base):
    """One registered cota class (clienteId + papel + vigencia) of a UA's fund."""

    __tablename__ = "qitech_ua_classe"
    __table_args__ = (
        # One row per (tenant, UA, clienteId). Re-registering a class with a
        # new vigencia window is an UPDATE, not a new row — keeps the conflict
        # target stable for upsert/seed.
        UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "cliente_id",
            name="uq_qitech_ua_classe",
        ),
        CheckConstraint(
            "papel IN ('SUBORDINADA','MEZANINO','SENIOR','UNICA')",
            name="ck_qitech_ua_classe_papel",
        ),
        # Hot read path for get_expected_classes(tenant, ua).
        Index(
            "ix_qitech_ua_classe_lookup",
            "tenant_id",
            "unidade_administrativa_id",
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
    # UA dona do fundo cujas classes este catalogo descreve. RESTRICT: nao
    # apagar UA com catalogo cadastrado sem antes limpar.
    unidade_administrativa_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cadastros_unidade_administrativa.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # QiTech `clienteId` — chave estavel por classe (ex.: "REALINVEST",
    # "REALINVEST MEZ", "REALINVEST SEN"). Mesma largura de
    # wh_mec_evolucao_cotas.carteira_cliente_id.
    cliente_id: Mapped[str] = mapped_column(String(50), nullable=False)
    cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # CNPJ do fundo (QiTech `cpfDoCliente`). Mesmo para todas as classes.
    fundo_cnpj: Mapped[str] = mapped_column(String(14), nullable=False)
    # Papel da classe — String + CheckConstraint (espelha PapelCota em
    # app/core/enums.py). Sem tipo enum nativo PG (consistente com cosif).
    papel: Mapped[str] = mapped_column(String(20), nullable=False)

    # Vigencia: classe esperada quando ativo_desde <= dia E
    # (ativo_ate IS NULL OR ativo_ate >= dia).
    ativo_desde: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    ativo_ate: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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
            f"<QiTechUaClasse ua={self.unidade_administrativa_id} "
            f"cliente_id={self.cliente_id!r} papel={self.papel} "
            f"vigente={self.ativo_ate is None}>"
        )
