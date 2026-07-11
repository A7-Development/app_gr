"""Canonical liquidation-outcome events per title (wh_liquidacao).

One row per DECLARED outcome event of a title — the F3 primitive of the
anti-fraud program (memoria project_f3_wh_liquidacao). Today populated by
the Bitfin adapter (`bitfin.liquidacoes`); future sources of liquidation at
the same grain join the SAME table with their own `source_type` (canonical
silver — the vendor lives in the row provenance, not in the table name).

NOT to be confused with `wh_liquidacao_recebivel` (QiTech/fund view of
receivable positions) — different grain, different source.

Channels (canal):
    bancaria             money arrived through the bank rail (occurrence 36
                         Liquidacao Normal / 37 Liquidacao em Cartorio, the
                         only codes that carry ValorPago). Carries the
                         DECLARED payment place (praca bits, agencia).
    recompra             cedente bought the title back — RecompraItem of an
                         effectuated Recompra, or TituloTransferencia with
                         Motivo='Recompra' (the path the Bitfin eligibility
                         view misses). Legit; control group for
                         "recompra disfarcada".
    baixa_manual         title liquidated in the ERP (Situacao 1/2) with NO
                         bank liquidation event. `evidencia` qualifies:
                         baixa_confirmada  boleto was registered and then
                                           written off by instruction
                                           (occurrence 05) — STRONG signal
                                           (the MFL pattern);
                         sem_registro      never had a registered boleto —
                                           direct deposit plausible
                                           (CMS/DMS products);
                         sem_ocorrencia    registered but no occurrence at
                                           all — weak (CNAB coverage gap or
                                           silent manual write-off).
    baixa_administrativa Situacao 3 (Baixado) without a recompra transfer —
                         title left the portfolio without money coming in.
    perda                Situacao 9 — accounting write-off.

Situacao 7 (Recuperacao de Credito) is a state move, not a liquidation —
out of v1 on purpose.
"""

from datetime import datetime
from decimal import Decimal
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
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class Liquidacao(Auditable, Base):
    """Declared outcome event of one title (append-per-event, upsert by key).

    Business key = (tenant_id, source_id); source_id is prefixed by event
    kind so distinct events of the same title coexist:
        liq:<tituloId>                    bank liquidation (max 1 per title)
        rec:<recompraId>:<tituloId>       recompra item (title can repeat)
        rcs:<tituloId>                    recompra declared only by the title
                                          stamp (Situacao 5 without
                                          RecompraItem — legacy recompras)
        tra:<tituloId>:<operacaoDestino>  recompra via transfer
        man:<tituloId>                    manual write-off (synthesized)
        bxa:<tituloId>                    administrative write-off
        per:<tituloId>                    loss
    """

    __tablename__ = "wh_liquidacao"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_liquidacao"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    titulo_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    operacao_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    unidade_administrativa_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )

    canal: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # Qualifies the canal (see module docstring): baixa_confirmada /
    # sem_registro / sem_ocorrencia (baixa_manual); recompra_efetivada /
    # situacao / transferencia (recompra). NULL for bancaria/baixa_administrativa/perda.
    evidencia: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    # Declared occurrence code of the bank event ('36' | '37').
    meio_codigo: Mapped[str | None] = mapped_column(String(4), nullable=True)

    data_evento: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    data_credito: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    valor_titulo: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    juros: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # Declared payment place of the bank event (raw as the ERP declared it;
    # praca-real vs eletronica refinement belongs to the signal engine +
    # RefBacen resolver, not to this silver).
    agencia_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    local_pagamento: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pago_fora_praca_sacado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pago_na_praca_cliente: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pago_na_agencia_cliente: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pago_na_agencia_sacado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pago_em_banco_digital: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Boleto context (ProcedimentoDeCobranca) — NULL when the title never
    # entered bank collection.
    registrado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    carteira_bancaria_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    recompra_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Snapshot of Titulo.Situacao at sync time (dicionario: 1 Liq Normal,
    # 2 Liq em Cartorio, 3 Baixado, 5 Recomprado, 7 Recuperacao, 9 Perda).
    situacao_titulo: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<Liquidacao titulo={self.titulo_id} canal={self.canal!r} "
            f"tenant={self.tenant_id}>"
        )
