"""wh_pj_processo (+ parte, andamento, resumo) — processos judiciais PJ (BDC processes).

Silver canonico do dataset `processes` (PROCESSES_V1). Quatro tabelas:

- **wh_pj_processo** (1/cnpj/numero) — cabecalho do processo: tipo, assunto,
  tribunal, area, status, valor, polaridade da empresa-alvo, datas. UPSERT por
  numero (re-consulta atualiza o que muda; NUNCA apaga — `last_seen_at` marca
  se sumiu da ultima resposta). `status` e LENTE: risco = vivos; bens = tudo.
- **wh_pj_processo_parte** (N/processo) — partes nomeadas (polo + nome + doc).
  Replace por processo (snapshot da ultima consulta).
- **wh_pj_processo_andamento** (N/processo) — movimentacoes (data + conteudo).
  INCREMENTA (dedupe por numero+data+hash do conteudo) -> acumula a linha do
  tempo completa entre consultas, mesmo com processo que some/arquiva. Full-text
  (tsvector PT) pra garimpo de bens; `evento_patrimonial` flag o que cita bem.
- **wh_pj_processo_resumo** (1/cnpj) — rollup pro headline/score: qtd_ativos,
  por area, por polo, execucoes contra a empresa, credores executando, recencia.

Frescor (§14): cada processo carrega `data_last_update` da fonte ->
source_updated_at; resumo e derivado -> source_updated_at NULL.
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


def _id() -> Mapped[UUID]:
    return mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )


def _tenant() -> Mapped[UUID]:
    return mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _ua() -> Mapped[UUID | None]:
    return mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cadastros_unidade_administrativa.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )


def _raw() -> Mapped[UUID | None]:
    return mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_bdc_raw_consulta.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class PjProcesso(Auditable, Base):
    """Cabecalho de um processo judicial/administrativo da empresa-alvo."""

    __tablename__ = "wh_pj_processo"
    __table_args__ = (
        UniqueConstraint("tenant_id", "cnpj", "numero", name="uq_wh_pj_processo"),
        Index("ix_wh_pj_processo_tenant_cnpj_status", "tenant_id", "cnpj", "status"),
    )

    id: Mapped[UUID] = _id()
    tenant_id: Mapped[UUID] = _tenant()
    unidade_administrativa_id: Mapped[UUID | None] = _ua()
    raw_id: Mapped[UUID | None] = _raw()
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)

    numero: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    tipo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    assunto: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Normalizados CNJ (mais limpos que `assunto` cru) — pra agrupar/categorizar.
    assunto_cnj: Mapped[str | None] = mapped_column(String(160), nullable=True)
    assunto_cnj_amplo: Mapped[str | None] = mapped_column(String(160), nullable=True)

    tribunal: Mapped[str | None] = mapped_column(String(40), nullable=True)
    instancia: Mapped[str | None] = mapped_column(String(8), nullable=True)
    area: Mapped[str | None] = mapped_column(String(40), nullable=True)  # CourtType
    comarca: Mapped[str | None] = mapped_column(String(120), nullable=True)
    orgao_julgador: Mapped[str | None] = mapped_column(String(240), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)

    status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Derivado: status na familia de encerrados (arquivado/baixado/extinto/...).
    encerrado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    # Polaridade da EMPRESA-ALVO neste processo (ACTIVE=autor/exequente,
    # PASSIVE=reu/executado, NEUTRAL=outro). Pro sinal "quem cobra quem".
    polaridade_alvo: Mapped[str | None] = mapped_column(String(12), nullable=True)
    is_execucao: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    num_partes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_atualizacoes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idade_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)

    data_redistribuicao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_notice: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_last_movement: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_last_update: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Quando o processo apareceu pela ultima vez numa consulta (re-consulta
    # atualiza; processo que some mantem o valor antigo -> "stale").
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<PjProcesso {self.cnpj} {self.numero} status={self.status}>"


class PjProcessoParte(Auditable, Base):
    """Uma parte de um processo (polo + nome + doc). Replace por processo."""

    __tablename__ = "wh_pj_processo_parte"
    __table_args__ = (
        Index(
            "ix_wh_pj_processo_parte_tenant_cnpj_numero",
            "tenant_id",
            "cnpj",
            "numero",
        ),
        Index("ix_wh_pj_processo_parte_doc", "doc"),
    )

    id: Mapped[UUID] = _id()
    tenant_id: Mapped[UUID] = _tenant()
    unidade_administrativa_id: Mapped[UUID | None] = _ua()
    raw_id: Mapped[UUID | None] = _raw()
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)

    numero: Mapped[str] = mapped_column(String(40), nullable=False)
    polaridade: Mapped[str | None] = mapped_column(String(12), nullable=True)
    tipo_parte: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ativa: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    nome: Mapped[str | None] = mapped_column(String(240), nullable=True)
    doc: Mapped[str | None] = mapped_column(String(20), nullable=True)

    def __repr__(self) -> str:
        return f"<PjProcessoParte {self.numero} {self.polaridade} {self.nome}>"


class PjProcessoAndamento(Auditable, Base):
    """Uma movimentacao de um processo. INCREMENTA (dedupe por hash).

    Full-text (`conteudo_tsv`, portugues) + `evento_patrimonial` pro garimpo de
    bens. A unicidade (tenant, cnpj, numero, data, conteudo_hash) faz o
    insert-if-new entre consultas (ON CONFLICT DO NOTHING) — acumula a timeline.
    """

    __tablename__ = "wh_pj_processo_andamento"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "cnpj",
            "numero",
            "data",
            "conteudo_hash",
            name="uq_wh_pj_processo_andamento",
        ),
        Index(
            "ix_wh_pj_processo_andamento_tenant_cnpj_numero",
            "tenant_id",
            "cnpj",
            "numero",
        ),
        Index(
            "ix_wh_pj_processo_andamento_patrimonial",
            "tenant_id",
            "cnpj",
            "evento_patrimonial",
        ),
        # Full-text GIN sobre o tsvector (criado na migration; o ORM so declara
        # a coluna como Text porque SQLAlchemy core nao tem TSVECTOR nativo aqui).
        Index(
            "ix_wh_pj_processo_andamento_tsv",
            text("conteudo_tsv"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[UUID] = _id()
    tenant_id: Mapped[UUID] = _tenant()
    unidade_administrativa_id: Mapped[UUID | None] = _ua()
    raw_id: Mapped[UUID | None] = _raw()
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)

    numero: Mapped[str] = mapped_column(String(40), nullable=False)
    data: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    conteudo_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evento_patrimonial: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    def __repr__(self) -> str:
        return f"<PjProcessoAndamento {self.numero} {self.data}>"


class PjProcessoResumo(Auditable, Base):
    """Rollup por cnpj — headline/score. Derivado do silver -> frescor=consulta."""

    __tablename__ = "wh_pj_processo_resumo"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "cnpj", "source_type", name="uq_wh_pj_processo_resumo"
        ),
    )

    id: Mapped[UUID] = _id()
    tenant_id: Mapped[UUID] = _tenant()
    unidade_administrativa_id: Mapped[UUID | None] = _ua()
    raw_id: Mapped[UUID | None] = _raw()
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)

    qtd_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qtd_ativos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qtd_encerrados: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # {trabalhista, civel, criminal, tributaria, outros} -> {qtd, valor} (ativos).
    por_area: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    qtd_como_reu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qtd_como_autor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Execucoes onde a empresa e EXECUTADA (outro credor cobrando) + os credores.
    qtd_execucoes_contra: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credores_executando: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    qtd_recuperacao_falencia: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    valor_total_informado: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    last_30d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_90d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_365d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    primeira_data: Mapped[date | None] = mapped_column(Date, nullable=True)
    ultima_data: Mapped[date | None] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return f"<PjProcessoResumo {self.cnpj} ativos={self.qtd_ativos}>"
