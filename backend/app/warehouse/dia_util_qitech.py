"""wh_dia_util_qitech -- catalogo de dias com publicacao QiTech por UA.

Resposta a pergunta: "para esta UA, em qual data houve snapshot publicado
pela QiTech?" — fonte unica de verdade para componentes que precisam
filtrar datas analisaveis (ex.: Calendar da pagina cota-sub).

Diferenca para `wh_dim_dia_util`:
- `wh_dim_dia_util`: calendario ANBIMA global ("e dia util de mercado?").
  Resposta independente de provider — tem feriados nacionais marcados.
- `wh_dia_util_qitech`: presenca de dado QiTech por UA. Resposta SOMENTE
  positiva quando ETL coletou snapshot da UA. Cobre fim de semana,
  feriado, falha de ETL e UA recem-cadastrada de forma uniforme.

Fonte (Fase A — backfill historico): inferida de `wh_mec_evolucao_cotas`
via migration `f9a3c2b1d8e0` (2026-05-07). MEC e a tabela-pulse (PL Sub
diario) — sua presenca implica "QiTech publicou dado pra esta UA neste
dia". Outras tabelas analiticas podem ter ausencias legitimas (fundo
sem RF, sem compromissada) que nao distorcem o conceito de dia util.

Fonte (Fase B — em vigor desde qitech_adapter_v0.2.0, 2026-05-11):
`etl.sync_all` chama `_mark_dia_util_qitech` no fim de cada sync. Mantem
a mesma regra-pulse (MEC com canonical_rows > 0 = dia 'completo') e
popula adicionalmente `relatorios_esperados` (= len(_PIPELINE)) e
`relatorios_recebidos` (= steps com raw_persisted=True). Idempotente.

Fonte (Fase C — 2026-05-13, apos Sub-fase 2A do scheduler per-endpoint):
`_mark_dia_util_qitech` virou data-driven (consulta MEC silver + raw http=200
diretamente no banco) e e chamada tanto por `etl.sync_all` quanto por
`adapter.adapter_sync_endpoint` (quando endpoint_name == 'market.mec'). Bug
corrigido: no caminho per-endpoint, o marcador nunca era acionado, deixando
dias com MEC silver presente fora do Calendar da pagina cota-sub (ex.:
2026-05-12, com 14/14 endpoints raw 200 mas wh_dia_util_qitech vazio).

Granularidade: 1 linha por (tenant_id, unidade_administrativa_id,
data_posicao, source_type).

Decisao de NAO usar Auditable: a tabela e DERIVADA de outras silver
(MEC + futuras), nao tem proveniencia upstream propria. Rastreabilidade
minima inline (`source_type`, `ingested_at`, `ingested_by_version`)
segue o padrao da `wh_dim_dia_util`.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class DiaUtilQitech(Base):
    """Marcador de dia com publicacao QiTech por UA."""

    __tablename__ = "wh_dia_util_qitech"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "data_posicao",
            "source_type",
            name="uq_wh_dia_util_qitech",
        ),
        # Indice principal de consulta: lista datas disponiveis para uma UA
        # ordenadas desc (mais recente primeiro). Filtro por status na app
        # se quiser separar 'completo' de 'parcial'.
        Index(
            "ix_wh_dia_util_qitech_busca",
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
    unidade_administrativa_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "cadastros_unidade_administrativa.id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Origem do registro. Hoje so 'admin:qitech', mas o campo permite que
    # outros providers (Bitfin, etc.) co-existam na mesma tabela com regras
    # de status proprias.
    source_type: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'admin:qitech'")
    )

    # Status do dia para esta UA:
    #   'completo' — todos os relatorios esperados foram coletados (Fase A
    #                considera todos os dias com MEC como completos).
    #   'parcial'  — algum relatorio nao chegou; analise possivel mas com
    #                lacunas (Fase B preenche conforme ETL).
    # Alargar para outros valores ('falhou', 'pendente') no futuro sem
    # migration (campo livre).
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'completo'")
    )

    # Metadados opcionais — preenchidos pelo ETL na Fase B; null no backfill.
    relatorios_esperados: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    relatorios_recebidos: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Rastreabilidade minima.
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ingested_by_version: Mapped[str] = mapped_column(
        String(128), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DiaUtilQitech ua={self.unidade_administrativa_id} "
            f"data={self.data_posicao} status={self.status}>"
        )
