"""wh_serasa_pj_consulta -- header silver de uma consulta Serasa PJ.

Granularidade: 1 linha por consulta (1:1 com raw). Existe pra dar shape
estavel ao dossie / dashboard, com cadastrais + score + contadores
agregados de restricoes — campos mais consultados em UI, sem precisar
parsear o JSONB do raw a cada query.

Re-mapear do raw e idempotente via UQ (tenant_id, source_id), onde
source_id = str(raw_id). Bug no mapper -> corrige + re-roda mapper ->
silver atualizado sem novo round-trip pago a Serasa.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class SerasaPjConsulta(Auditable, Base):
    """Header de uma consulta Serasa PJ — cadastrais + score + contadores."""

    __tablename__ = "wh_serasa_pj_consulta"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_serasa_pj_consulta"
        ),
        # "Ultima consulta do CNPJ X" — base de dossie + risco.
        Index(
            "ix_wh_serasa_pj_consulta_tenant_cnpj_consulted",
            "tenant_id",
            "cnpj",
            text("consulted_at DESC"),
        ),
        # Partial indexes para queries de carteira / monitoramento.
        Index(
            "ix_wh_serasa_pj_consulta_tenant_has_refin",
            "tenant_id",
            "cnpj",
            postgresql_where=text("has_refin = true"),
        ),
        Index(
            "ix_wh_serasa_pj_consulta_tenant_has_pefin",
            "tenant_id",
            "cnpj",
            postgresql_where=text("has_pefin = true"),
        ),
        Index(
            "ix_wh_serasa_pj_consulta_tenant_has_falencias",
            "tenant_id",
            "cnpj",
            postgresql_where=text("has_falencias = true"),
        ),
        Index(
            "ix_wh_serasa_pj_consulta_tenant_has_acoes",
            "tenant_id",
            "cnpj",
            postgresql_where=text("has_acoes_judiciais = true"),
        ),
        # Carteira: "quais CNPJs estao sob suspeita de liminar" — base do
        # badge na ficha do cedente + sentinela (regra serasa_liminar_v1).
        Index(
            "ix_wh_serasa_pj_consulta_tenant_suspeita_liminar",
            "tenant_id",
            "cnpj",
            postgresql_where=text("suspeita_liminar = true"),
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
        ForeignKey(
            "wh_serasa_pj_raw_relatorio.id", ondelete="RESTRICT"
        ),
        nullable=False,
        index=True,
    )

    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    consulted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    requested_report: Mapped[str] = mapped_column(String(64), nullable=False)
    actual_report_returned: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    reciprocity_downgrade: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # ─── Cadastrais ────────────────────────────────────────────────────────
    razao_social: Mapped[str | None] = mapped_column(Text, nullable=True)
    nome_fantasia: Mapped[str | None] = mapped_column(Text, nullable=True)
    situacao_cadastral: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    data_constituicao: Mapped[date | None] = mapped_column(Date, nullable=True)
    capital_social: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    faturamento_presumido: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    atividade_principal_cnae: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    atividade_principal_descricao: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # ─── Cadastrais expandidos (F.1) ───────────────────────────────────────
    legal_nature_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    partnership_description: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    number_employees: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    export_sales: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    import_purchases: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    nire_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state_registration: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    company_register: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    company_register_date: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    serasa_active_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )

    # ─── Status detalhado ──────────────────────────────────────────────────
    status_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status_registration_text: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    company_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Telefone (separado pra queries por DDD) ───────────────────────────
    phone_area_code: Mapped[str | None] = mapped_column(
        String(4), nullable=True
    )
    phone_number: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    # ─── Regime tributario + filiais (F.3.1) ───────────────────────────────
    tax_option: Mapped[str | None] = mapped_column(String(32), nullable=True)
    branch_offices: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    # ─── Score ─────────────────────────────────────────────────────────────
    score_h4pj: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    score_classe: Mapped[str | None] = mapped_column(String(8), nullable=True)
    score_descricao: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Contadores (derivados das filhas) ─────────────────────────────────
    has_refin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    has_pefin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    has_protesto: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    has_cheque: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    count_refin: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    count_pefin: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    count_protesto: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    count_cheque: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    valor_total_restricoes: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )

    # ─── Supressao judicial (regra serasa_liminar_v1) ──────────────────────
    # `negative_summary_message` = valor cru de `negativeSummary.message`
    # do payload (proveniencia — o fator que disparou a conclusao).
    # `suspeita_liminar` = conclusao DERIVADA pelo Strata (nao consta no
    # bureau nem no ERP): mensagem explicita "NADA CONSTA" e o padrao de
    # supressao judicial de apontamentos. Ver adapters/bureau/serasa_pj/
    # liminar.py para a regra versionada e a evidencia da descoberta.
    negative_summary_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    suspeita_liminar: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # ─── Sumarios facts.bankrupts + facts.judgementFilings (F.1) ───────────
    has_falencias: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    count_falencias: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    valor_falencias: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    has_acoes_judiciais: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    count_acoes_judiciais: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    valor_acoes_judiciais: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
