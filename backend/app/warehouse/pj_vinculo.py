"""wh_pj_vinculo -- vinculos societarios/relacionais de uma PJ (grafo).

Silver canonico **vendor-neutro** do Quadro Societario. Cada linha e UMA
ARESTA do grafo: do CNPJ consultado para uma entidade relacionada (socio,
administrador, representante legal, empresa possuida, funcionario). Alimenta
hoje pelo BDC (`relationships` + `dynamic_qsa_data`) e, futuramente, pode
receber arestas de outra fonte (Serasa devolve socios) — por isso a
reconciliacao e por `(tenant, cnpj, source_type)`, nunca apagando o que veio
de outra fonte. Ver `docs/central-de-dados-arquitetura.md` §5.

Nomeado pela ENTIDADE (PJ) + relacao, nao pelo vendor. Prefixo `wh_pj_*`
agrupa todo dado de referencia de PJ-terceiro (cadastro, vinculo, grupo...).

Grao: 1 linha por aresta = ultimo snapshot da consulta. O historico de
re-consultas vive no raw (`wh_bdc_raw_consulta`); a evolucao temporal do
proprio vinculo (entrou/saiu) vive nas colunas `data_inicio`/`data_fim`/
`ativo` da propria aresta, que o BDC ja entrega.

Frescor (idade da informacao, §14): `source_updated_at` (do Auditable) =
`LastUpdateDate` da aresta na fonte. Vinculo e dataset de EVENTO -> tem data
propria por registro. Quando preenchido, a idade e a da fonte; se NULL, cai
para `ingested_at` (data da consulta).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class PjVinculo(Auditable, Base):
    """Uma aresta do grafo societario/relacional de uma PJ, vendor-neutro."""

    __tablename__ = "wh_pj_vinculo"
    __table_args__ = (
        # Reverse lookup: "em quais empresas o documento X aparece como socio".
        Index(
            "ix_wh_pj_vinculo_tenant_relacionado",
            "tenant_id",
            "documento_relacionado",
        ),
        # Grafo a partir do CNPJ consultado (organograma, "quem controla").
        Index("ix_wh_pj_vinculo_tenant_cnpj", "tenant_id", "cnpj"),
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
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cadastros_unidade_administrativa.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    raw_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_bdc_raw_consulta.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Origem da aresta (a PJ consultada) ──
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)

    # ── Destino da aresta (entidade relacionada) ──
    # documento = CPF (11) ou CNPJ (14); tipo_pessoa discrimina.
    documento_relacionado: Mapped[str | None] = mapped_column(
        String(14), nullable=True
    )
    tipo_pessoa: Mapped[str | None] = mapped_column(String(2), nullable=True)  # PF/PJ
    nome: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Natureza do vinculo ──
    # relationship_type: QSA / Ownership / Employee / RepresentanteLegal.
    relationship_type: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )
    # relationship_name: SOCIO-ADMINISTRADOR / SOCIO / ADMINISTRADOR / ... .
    relationship_name: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    # % de participacao societaria. BDC `relationships`/QSA NAO traz (so o
    # dataset ONDEMAND de participacao, fora do v1) -> nullable, hoje sempre NULL.
    percentual: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 4), nullable=True
    )

    # ── Vigencia (o churn de controle, direto da fonte) ──
    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_fim: Mapped[date | None] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PjVinculo {self.cnpj} -> {self.documento_relacionado} "
            f"({self.relationship_name}) ativo={self.ativo}>"
        )
