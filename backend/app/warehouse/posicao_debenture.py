"""wh_posicao_debenture_dia -- PL diario de debentures por UA (silver).

Serie diaria do patrimonio em debentures (o passivo/funding do fundo que se
capitaliza via debentures, analogo ao `patrimonio` por classe de cota do MEC
em `wh_mec_evolucao_cotas`). 1 linha por (tenant, ua, dia).

Populada a partir do bronze `wh_bitfin_raw_debenture` (CLAUDE.md 13.2.1):

- `ancora_mensal`  -- dia de fechamento que casa com `posicao_mensal` oficial.
- `snapshot`       -- dia capturado de `valor_atualizado_dia` (valor que a
                      propria Bitfin calculou com CDI+spread naquele dia).
- `interpolado`    -- dia reconstruido por interpolacao geometrica entre duas
                      ancoras mensais consecutivas (serie e CDI+spread, entao a
                      curva intra-mes e suave; o erro de interpolacao para a
                      MEDIA mensal e negligivel). Marcado para auditabilidade.

`origem` discrimina a procedencia de cada dia -- proveniencia visivel na UI
(CLAUDE.md 14.5). PL medio do mes = AVG(pl_bruto) sobre os dias do mes.

Consumida por `controladoria/services/dre/roa.py` (denominador do ROA bruto
sobre PL debentures).
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

# Procedencia do dia (coluna `origem`).
ORIGEM_ANCORA_MENSAL = "ancora_mensal"
ORIGEM_SNAPSHOT = "snapshot"
ORIGEM_INTERPOLADO = "interpolado"


class PosicaoDebentureDia(Auditable, Base):
    """PL de debentures por UA num dia -- serie diaria para PL medio mensal."""

    __tablename__ = "wh_posicao_debenture_dia"
    __table_args__ = (
        # Business key: 1 PL por UA num dia.
        UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "data_posicao",
            name="uq_wh_posicao_debenture_dia",
        ),
        Index(
            "ix_wh_posicao_debenture_dia_tenant_ua_data",
            "tenant_id",
            "unidade_administrativa_id",
            "data_posicao",
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

    # UA Bitfin dona das escrituras de debenture (int, igual ao silver da DRE
    # e de operacoes -- nao e o UUID de cadastro). Mapeada via
    # DebentureEscritura.UnidadeAdministrativaId na fonte.
    unidade_administrativa_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )

    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # PL bruto (TotalBruto = principal + rendimento apropriado). E o numero
    # escolhido como "PL debentures" do ROA (decisao 2026-06-01: analogo ao
    # `patrimonio` do MEC, que tambem inclui valorizacao).
    pl_bruto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Principal (soma de Valor) e liquido de IR (TotalLiquido) -- mantidos para
    # analise complementar; NAO sao o denominador default do ROA.
    pl_valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    pl_liquido: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=0
    )

    quantidade_debentures: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), nullable=False, default=0
    )
    n_subscricoes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Procedencia do dia (ORIGEM_*): ancora_mensal | snapshot | interpolado.
    origem: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
