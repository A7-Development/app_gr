"""Historical bank-branch registry from the BCB open-data series (wh_bcb_agencia).

The definitive agency source (decisao Ricardo 2026-07-08): the BCB monthly
"Informes de Agencias" stacked since 2007-09 (via Base dos Dados, BigQuery
`basedosdados.br_bcb_agencia.agencia`), deduplicated to the LAST known state
of every agency that ever existed — 30k branches INCLUDING the extinct ones
the live Olinda snapshot drops (e.g. Bradesco 1417/Penha-RJ, last seen
2025-10). Full address + CNPJ + IBGE municipality.

Populated by a ONE-TIME backfill (scripts/backfill_bcb_agencia.py) — extinct
agencies never come back, so there is no permanent BigQuery dependency; the
live Olinda API keeps the CURRENT month fresh in ref_bacen_agencia. This is
the 1st rung of the resolution ladder; ERP cadastro drops out.

Provenance: origin BCB, host Base dos Dados (public re-host). `ativa` = the
agency was present in the most recent published competencia.
"""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class WhBcbAgencia(Auditable, Base):
    """One agency (last known state) from the BCB historical series."""

    __tablename__ = "wh_bcb_agencia"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_bcb_agencia"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # COMPE do banco (derivado do cnpj_base quando a linha vem sem ele) +
    # codigo da agencia 5-digitos — as chaves de match contra o CNAB.
    banco_compe: Mapped[str | None] = mapped_column(String(3), nullable=True, index=True)
    agencia_codigo: Mapped[str] = mapped_column(String(5), nullable=False)
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)

    instituicao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nome_agencia: Mapped[str | None] = mapped_column(String(255), nullable=True)
    endereco: Mapped[str | None] = mapped_column(String(255), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(9), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(255), nullable=True)
    municipio_ibge: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    ddd: Mapped[str | None] = mapped_column(String(3), nullable=True)
    fone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    segmento: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_inicio: Mapped[date | None] = mapped_column(nullable=True)

    # Janela em que a agencia apareceu na serie (competencia AAAAMM).
    primeira_competencia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ultima_competencia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # True se presente na competencia mais recente publicada; False = extinta.
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return (
            f"<WhBcbAgencia {self.banco_compe}/{self.agencia_codigo} "
            f"{self.municipio}/{self.uf} ativa={self.ativa}>"
        )
