"""wh_pj_cadastro -- cadastro canônico de uma PJ (terceiro analisado).

Silver canônico, **vendor-neutro**, do produto de dado CAD-PJ. Alimentado hoje
pelo BDC (basic_data) e, futuramente, pelo Serasa — ambos mapeiam para as mesmas
colunas canônicas. Ver `docs/central-de-dados-arquitetura.md` §5/§5.2.

Nomeado pela ENTIDADE (uma PJ), não pelo uso (crédito) nem pelo vendor (bdc) —
prefixo `wh_pj_*` agrupa todo dado de referência de PJ-terceiro (cadastro,
restrição, sócio, score…).

Grão: 1 linha por (tenant, cnpj) = estado atual/última consulta. O histórico de
reconsultas vive no raw; série temporal, se precisar, nasce em `wh_pj_cadastro_hist`.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class PjCadastro(Auditable, Base):
    """Cadastro canônico de uma PJ (CNPJ), vendor-neutro."""

    __tablename__ = "wh_pj_cadastro"
    __table_args__ = (
        # Business key: 1 linha por CNPJ por tenant (estado atual).
        UniqueConstraint("tenant_id", "cnpj", name="uq_wh_pj_cadastro"),
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
    # UA dona da credencial que produziu a consulta (multi-UA). Nullable p/
    # retrocompat, como nas demais silver.
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cadastros_unidade_administrativa.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # Lineage: payload raw que originou esta linha (silver-only no consumo).
    raw_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_bdc_raw_consulta.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Identidade ──
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    razao_social: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nome_fantasia: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Fatos cadastrais (campos promovidos do contrato CAD-PJ) ──
    situacao_cadastral: Mapped[str | None] = mapped_column(String(40), nullable=True)
    data_fundacao: Mapped[date | None] = mapped_column(Date, nullable=True)
    capital_social: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    cnae_principal: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Lista de CNAEs (código+descrição) como veio normalizada do mapper.
    cnaes: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Campos promovidos do basic_data (seleção Ricardo 2026-06-17) ──
    regime_tributario: Mapped[str | None] = mapped_column(String(64), nullable=True)
    porte: Mapped[str | None] = mapped_column(String(32), nullable=True)
    optante_simples: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    natureza_juridica_codigo: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    natureza_juridica: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # SpecialSituation — "RECUPERAÇÃO JUDICIAL"/"FALIDA" quando preenchido.
    situacao_especial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    situacao_cadastral_desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_inicio_atividade: Mapped[date | None] = mapped_column(Date, nullable=True)
    origem_cadastral: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mudou_nome: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mudou_regime: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # [{valor, desde, ate}] — evolução do nome fantasia.
    historico_nomes: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Resumo de relacionamentos (do dataset `relationships`) ──
    qtd_socios: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qtd_empresas_possuidas: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    empresa_familiar: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    operada_pela_familia: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )

    def __repr__(self) -> str:
        return f"<PjCadastro tenant={self.tenant_id} cnpj={self.cnpj!r}>"
