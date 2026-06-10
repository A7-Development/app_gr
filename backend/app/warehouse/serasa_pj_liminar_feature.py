"""lab_serasa_pj_liminar_feature -- features p/ ciencia de dados (liminar).

Tese de laboratorio (2026-06-10): estudar o entorno dos CNPJs sob
supressao judicial de apontamentos (regra serasa_liminar_v1) e detectar
drift de comportamento da Serasa. 1 linha por consulta (grain = raw_id),
derivada do SILVER (CLAUDE.md 13.2.1) + classificacao da regra.

Tres blocos de colunas:
  - cross-sectional: contadores/saldos por categoria, consultas ao
    mercado, payment history, cadastrais relevantes;
  - longitudinal: deltas vs consulta anterior do MESMO CNPJ ("zerou em
    bloco" e o sinal classico de liminar: pagamento real e gradual e por
    categoria; liminar derruba tudo de uma vez);
  - label: `label_liminar` curado (hoje espelha a flag Liminar do Bitfin
    via bitfin_consulta_id; campo separado da conclusao da regra de
    proposito — label e ground truth externo, suspeita_liminar e a nossa
    inferencia).

Reconstruivel do zero (silver e a fonte) — versionada por
`extractor_version` para reprodutibilidade de analise.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
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


class SerasaPjLiminarFeature(Base):
    """Features de 1 consulta Serasa PJ para a tese de liminar."""

    __tablename__ = "lab_serasa_pj_liminar_feature"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "raw_id", name="uq_lab_serasa_pj_liminar_feature"
        ),
        # Serie temporal por CNPJ — base das features longitudinais.
        Index(
            "ix_lab_serasa_pj_liminar_feature_tenant_cnpj_at",
            "tenant_id",
            "cnpj",
            "consulted_at",
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
    raw_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_serasa_pj_raw_relatorio.id", ondelete="CASCADE"),
        nullable=False,
    )
    consulta_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_serasa_pj_consulta.id", ondelete="CASCADE"),
        nullable=False,
    )
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False)
    consulted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # "bitfin_relay" | "direta" — origem da consulta (raw.bitfin_consulta_id).
    origem: Mapped[str] = mapped_column(String(16), nullable=False)

    # ─── Regra serasa_liminar (cross-sectional) ────────────────────────────
    # Classificacao canonica da mensagem (liminar.py): ausente / vazia /
    # nada_consta / recuperacao_judicial / desconhecida.
    msg_class: Mapped[str] = mapped_column(String(24), nullable=False)
    suspeita_liminar: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # ─── Negativos (cross-sectional) ───────────────────────────────────────
    count_pefin: Mapped[int] = mapped_column(Integer, nullable=False)
    count_refin: Mapped[int] = mapped_column(Integer, nullable=False)
    count_protesto: Mapped[int] = mapped_column(Integer, nullable=False)
    count_cheque: Mapped[int] = mapped_column(Integer, nullable=False)
    count_falencias: Mapped[int] = mapped_column(Integer, nullable=False)
    count_acoes_judiciais: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    valor_total_restricoes: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )

    # ─── Mercado / consultas ao credito ────────────────────────────────────
    # Quantas consultas de outras empresas nos 90d anteriores (lista
    # detalhada) e no acumulado 12M (agregado mensal). Consultantes
    # distintos = quantos CNPJs diferentes consultaram (mercado vigiando).
    inquiries_90d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inquiries_12m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consultantes_distintos: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ─── Outros sinais ─────────────────────────────────────────────────────
    tem_payment_history: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
    idade_empresa_anos: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 1), nullable=True
    )
    rj_no_nome: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # ─── Longitudinal (vs consulta anterior do mesmo CNPJ) ─────────────────
    prev_raw_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    dias_desde_anterior: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # Soma de todas as categorias agora - antes (negativo = melhorou).
    delta_negativos: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # Quantas categorias estavam > 0 e foram a 0 nesta consulta.
    categorias_zeradas: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # >= 2 categorias zerando simultaneamente — assinatura de liminar.
    zerou_em_bloco: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # ─── Label (ground truth externo, separado da inferencia) ──────────────
    label_liminar: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )

    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False)
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
