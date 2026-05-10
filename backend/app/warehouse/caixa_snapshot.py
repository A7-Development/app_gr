"""wh_caixa_snapshot -- snapshot diario de saldo de conta-corrente do fundo.

Granularidade: 1 linha por (tenant, ua_id, conta_bancaria_id, data_snapshot).
Re-rodar a sync no mesmo dia upserta a mesma linha (overwrite). Historico cresce
1 linha por (conta, dia) -- volume baixo (3 UAs x ~5 contas ~= 15 linhas/dia).

Fonte: Bitfin `ContaCorrente` + `ContaBancaria` + `UnidadeAdministrativa` +
LEFT JOIN `ContaBancariaCaucao` + LEFT JOIN `ContaBancariaTrava` (estrutural,
ver §13 e §14).

Serve a metrica VOP Potencial = vop_realizado + caixa_disponivel +
liquidacoes_previstas. Filtros aplicados pelo BI service:
- `ativa = true` (conta nao cancelada)
- `eh_escrow = false` (escrow nao e caixa livre)
- `eh_caucao = false` (caucao nao e caixa livre)
- `eh_travada = false` (trava nao e caixa livre)
- UA Tipo IN (1, 2) via JOIN com `wh_dim_unidade_administrativa`

Carrega TODAS as contas (incl. UA Tipo NULL = "outras"). Filtro de tipo
estrutural fica no service para permitir analise de saldo medio /
eficiencia comercial em todas as UAs (CLAUDE.md §13).

Diferenca vs `wh_saldo_bancario_diario` (QiTech):
- `wh_saldo_bancario_diario` = saldo via QiTech /bank-account/balance/ (bureau).
- `wh_caixa_snapshot` = saldo via ERP Bitfin (`ContaCorrente.Saldo`). Fontes
  diferentes (bureau vs ERP), atualizacao diferente. Reconciliacao das duas
  fica em modulo controladoria (cf. memoria `proxima_acao_conciliacao`).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class CaixaSnapshot(Auditable, Base):
    """Snapshot diario de saldo de uma conta bancaria de UA do fundo."""

    __tablename__ = "wh_caixa_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "data_snapshot", "source_id", name="uq_wh_caixa_snapshot"
        ),
        # Acesso canonico: caixa por UA num intervalo de datas (saldo medio).
        Index(
            "ix_wh_caixa_snapshot_tenant_ua_data",
            "tenant_id",
            "unidade_administrativa_id",
            "data_snapshot",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Temporal -- particiona o historico
    data_snapshot: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Identidade da conta no Bitfin -- denormalizado para evitar JOINs em queries de BI.
    conta_bancaria_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    conta_corrente_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    numero: Mapped[str | None] = mapped_column(String(50), nullable=True)
    descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Tipo da ContaBancaria no Bitfin (enum int proprio do ERP -- preservamos cru).
    conta_bancaria_tipo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    banco_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agencia_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # UA dona da conta (FK semantica para `wh_dim_unidade_administrativa.ua_id`).
    unidade_administrativa_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Flags estruturais que classificam o caixa como "livre" ou nao.
    # `eh_escrow` vem de `ContaBancaria.Escrow` (bit). Caucao/Trava vem de
    # tabelas separadas (`ContaBancariaCaucao`, `ContaBancariaTrava`) -- a
    # presenca de linha ativa marca a flag como true no silver.
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    eh_escrow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eh_caucao: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eh_travada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Saldo (pode ser negativo -- cheque especial).
    saldo: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
