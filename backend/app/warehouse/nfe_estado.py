"""Silver do ESTADO VIVO da NF-e (fonte: SERPRO Consulta NF-e) -- situacao + eventos.

Duas tabelas canonicas, populadas EXCLUSIVAMENTE pelo adapter SERPRO
(decisao Ricardo 2026-07-10), a partir do bronze `wh_serpro_raw_nfe`:

- `wh_nfe_evento` (append-only): 1 linha por evento SEFAZ da nota
  (cancelamento, carta de correcao, manifestacoes, registros CT-e/MDF-e...).
- `wh_nfe_situacao` (1 linha por chave, reescrita a cada snapshot novo):
  o estado ATUAL derivado — situacao, manifestacao, protocolo.

REGRA DURA (Ricardo 2026-07-10): NENHUM campo do retorno e descartado.
Todos os escalares conhecidos viram colunas nomeadas E as subarvores
completas (`evento`, `retEvento`, `infProt`) sao preservadas verbatim em
colunas JSONB — campo novo/raro do vendor nunca se perde, mesmo antes de
ganhar coluna propria.

Distincao de `wh_nfe` (landing fiscal): aquela carrega o DOCUMENTO (retrato
do XML na autorizacao); estas carregam o ESTADO (que muda depois). A nota
cancelada mantem protNFe.cStat=100 — o cancelamento vive no EVENTO 110111
(validado em producao 2026-07-10; retEvento.cStat 135 ou 155).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class NfeEvento(Auditable, Base):
    """Evento SEFAZ de uma NF-e (procEventoNFe[i]) -- append-only."""

    __tablename__ = "wh_nfe_evento"
    __table_args__ = (
        # Identidade natural do evento na SEFAZ: (chave, tipo, sequencia).
        UniqueConstraint(
            "tenant_id",
            "chave_acesso",
            "tp_evento",
            "n_seq_evento",
            name="uq_wh_nfe_evento_identidade",
        ),
        Index("ix_wh_nfe_evento_tenant_chave", "tenant_id", "chave_acesso"),
        Index("ix_wh_nfe_evento_tenant_tipo", "tenant_id", "tp_evento"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Snapshot do bronze que trouxe o evento pela primeira vez.
    raw_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_serpro_raw_nfe.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chave_acesso: Mapped[str] = mapped_column(String(44), nullable=False)

    # ---- evento.infEvento (escalares) ----
    # Atributo Id do evento ("ID<tpEvento><chave><nSeq>").
    id_evento: Mapped[str | None] = mapped_column(String(60), nullable=True)
    c_orgao: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tp_amb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Autor do evento: CNPJ ou CPF (o payload traz um OU outro).
    autor_cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    autor_cpf: Mapped[str | None] = mapped_column(String(11), nullable=True)
    dh_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tp_evento: Mapped[int] = mapped_column(Integer, nullable=False)
    n_seq_evento: Mapped[int] = mapped_column(Integer, nullable=False)
    ver_evento: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # ---- evento.infEvento.detEvento (escalares comuns) ----
    desc_evento: Mapped[str | None] = mapped_column(String(120), nullable=True)
    x_just: Mapped[str | None] = mapped_column(Text, nullable=True)
    x_correcao: Mapped[str | None] = mapped_column(Text, nullable=True)
    det_n_prot: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ---- retEvento.infEvento (escalares) ----
    ret_ver_aplic: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ret_c_orgao: Mapped[str | None] = mapped_column(String(2), nullable=True)
    ret_c_stat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ret_x_motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ret_x_evento: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ret_cnpj_dest: Mapped[str | None] = mapped_column(String(14), nullable=True)
    ret_cpf_dest: Mapped[str | None] = mapped_column(String(11), nullable=True)
    ret_email_dest: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ret_dh_reg_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ret_n_prot: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ---- Subarvores VERBATIM (garantia de perda zero) ----
    evento_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ret_evento_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class NfeSituacao(Auditable, Base):
    """Estado ATUAL da NF-e por chave -- derivado do protocolo + eventos."""

    __tablename__ = "wh_nfe_situacao"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "chave_acesso", name="uq_wh_nfe_situacao_tenant_chave"
        ),
        Index("ix_wh_nfe_situacao_tenant_situacao", "tenant_id", "situacao"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Snapshot mais recente que atualizou esta linha.
    last_raw_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_serpro_raw_nfe.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chave_acesso: Mapped[str] = mapped_column(String(44), nullable=False)

    # ---- nfeProc.protNFe.infProt (escalares, TODOS) ----
    nfe_proc_versao: Mapped[str | None] = mapped_column(String(8), nullable=True)
    prot_tp_amb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prot_ver_aplic: Mapped[str | None] = mapped_column(String(30), nullable=True)
    prot_dh_recbto: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    prot_n_prot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    prot_dig_val: Mapped[str | None] = mapped_column(String(44), nullable=True)
    prot_c_stat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prot_x_motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prot_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # infProt verbatim (perda zero).
    prot_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ---- Estado DERIVADO (classificador do mapper) ----
    # autorizada | autorizada_fora_prazo | cancelada | cancelada_fora_prazo |
    # denegada | desconhecida (cStat nao mapeado — nunca falha silenciosa).
    situacao: Mapped[str] = mapped_column(String(32), nullable=False)
    cancelada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dh_cancelamento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Manifestacao do destinatario MAIS RECENTE (por dh_evento):
    # ciencia | confirmacao | desconhecimento | operacao_nao_realizada | NULL.
    manifestacao: Mapped[str | None] = mapped_column(String(24), nullable=True)
    dh_manifestacao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    qtd_eventos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dh_ultimo_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # fetched_at do snapshot que gerou esta linha (frescor da informacao).
    consultado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
