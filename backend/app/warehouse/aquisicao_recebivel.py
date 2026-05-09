"""wh_aquisicao_recebivel -- aquisicoes (cessoes) realizadas no FIDC num periodo.

Granularidade: 1 linha por (tenant, source_id) com source_id derivado de
`idRecebivel` (id estavel na QiTech). Multiplas chamadas com periodos
sobrepostos retornam o mesmo recebivel; UQ garante idempotencia.

Fonte: QiTech `/v2/fidc-custodia/report/aquisicao-consolidada/{cnpj}/{di}/{df}`.
Granularidade da consulta: PERIODO (data_inicial..data_final), mas a linha
canonica reflete a aquisicao individual.

Note: schema da QiTech tem inconsistencias entre endpoints da familia
custodia (fundoCnpj as vezes int, as vezes str; idRecebivel idem) — nosso
mapper normaliza tudo pra string aqui.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class AquisicaoRecebivel(Auditable, Base):
    """Aquisicao individual de recebivel pelo FIDC."""

    __tablename__ = "wh_aquisicao_recebivel"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_aquisicao_recebivel"
        ),
        Index(
            "ix_wh_aquisicao_recebivel_tenant_fundo_data",
            "tenant_id",
            "fundo_doc",
            "data_aquisicao",
        ),
        Index(
            "ix_wh_aquisicao_recebivel_tenant_fundo_cedente",
            "tenant_id",
            "fundo_doc",
            "cedente_doc",
            "data_aquisicao",
        ),
        Index(
            "ix_wh_aquisicao_recebivel_tenant_fundo_sacado",
            "tenant_id",
            "fundo_doc",
            "sacado_doc",
            "data_aquisicao",
        ),
        Index(
            "ix_wh_aquisicao_recebivel_id_recebivel",
            "id_recebivel",
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
    # UA dona da credencial que produziu esta linha (multi-UA, Phase F).
    # Nullable apenas para retrocompat com linhas legacy ingeridas antes
    # da introducao de multi-UA. Toda nova linha gravada pelo adapter
    # informa explicitamente.
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "cadastros_unidade_administrativa.id", ondelete="RESTRICT"
        ),
        nullable=True,
        index=True,
    )

    # ---- Quando ----
    # Data da aquisicao (= dataDaPosicao na QiTech, que aqui significa
    # data em que o FIDC adquiriu o recebivel — confuso mas consistente).
    data_aquisicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ---- Fundo (FIDC) ----
    fundo_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    fundo_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    # ---- Cedente / Sacado ----
    cedente_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    cedente_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    sacado_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    sacado_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    # ---- Recebivel ----
    # `idRecebivel` da QiTech -- normalizado pra string mesmo quando vem int.
    id_recebivel: Mapped[str] = mapped_column(String(32), nullable=False)
    seu_numero: Mapped[str] = mapped_column(String(50), nullable=False)
    numero_documento: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo_recebivel: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # ---- Fatos ----
    valor_compra: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_vencimento: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    prazo_recebivel: Mapped[int] = mapped_column(Integer, nullable=False)
    taxa_aquisicao: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
