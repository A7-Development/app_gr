"""wh_bitfin_raw_debenture -- camada raw (bronze) da posicao de debentures.

Padrao raw -> canonico (CLAUDE.md secao 13.2). Armazena o **payload cru** que
o Bitfin (UNLTD_<cliente>) devolveu para a posicao de debentures, em duas
variantes discriminadas por `tipo_origem`:

- `posicao_mensal` -- fechamento mensal oficial de `dbo.PosicaoHistoricaDebenture`
  (1 linha por subscricao num (Ano, Mes)). E a **ancora** autoritativa: o
  Bitfin ja aplicou a correcao CDI+spread ate o fechamento. Granularidade do
  fetch: 1 row de bronze = 1 competencia inteira (array de todas as subscricoes).
  Retencao curta na fonte (observado ~4 meses) -> ingerir cedo.

- `valor_atualizado_dia` -- snapshot diario de `dbo.DebentureSerie.ValorAtualizado`
  x `dbo.DebentureSubscricao.QuantidadeDeDebenturesAtual` por subscricao ativa.
  Capturado going-forward (a Bitfin sobrescreve `ValorAtualizado` todo dia com
  a conta CDI+spread dela; nos so fotografamos). Granularidade: 1 row de bronze
  = 1 dia (array de todas as subscricoes ativas naquele dia).

Por que duas variantes: a serie e **CDI + spread** (nao prefixada), entao a
diaria nao sai de formula fechada nossa. A ancora mensal cobre o historico
(interpolacao geometrica entre fechamentos); o snapshot diario cobre o
presente/futuro com o valor que a propria Bitfin calcula. O silver
`wh_posicao_debenture_dia` consolida os dois numa serie diaria por UA.

NAO usa mixin `Auditable` (CLAUDE.md secao 14.1, excecao raw): a raw E a fonte.
Proveniencia direta -- `fetched_at` + `fetched_by_version` + `payload_sha256`.
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Discriminator values -- string (nao enum SQL) para evitar migration ao
# adicionar nova variante. Validacao na camada de aplicacao (adapter/etl).
TIPO_ORIGEM_POSICAO_MENSAL = "posicao_mensal"
TIPO_ORIGEM_VALOR_ATUALIZADO_DIA = "valor_atualizado_dia"


class BitfinRawDebenture(Base):
    """Snapshot cru da posicao de debentures Bitfin.

    Chave logica: (tenant, tipo_origem, data_referencia). Para `posicao_mensal`,
    `data_referencia` = date(Ano, Mes, 1). Para `valor_atualizado_dia`,
    `data_referencia` = o dia do snapshot.
    """

    __tablename__ = "wh_bitfin_raw_debenture"
    __table_args__ = (
        # Idempotencia: fetch identico (mesmo conteudo) e no-op via ON CONFLICT.
        # Fetch com payload alterado gera row nova preservando historico.
        UniqueConstraint(
            "tenant_id",
            "tipo_origem",
            "data_referencia",
            "payload_sha256",
            name="uq_wh_bitfin_raw_debenture",
        ),
        # Acesso canonico: "ultimo snapshot por (tipo, data) do tenant".
        Index(
            "ix_wh_bitfin_raw_debenture_tenant_tipo_data_fetched",
            "tenant_id",
            "tipo_origem",
            "data_referencia",
            "fetched_at",
        ),
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

    # Particao logica entre as duas fontes (TIPO_ORIGEM_*).
    tipo_origem: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Para posicao_mensal: 1o dia da competencia (Ano, Mes). Para
    # valor_atualizado_dia: o proprio dia do snapshot.
    data_referencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Body cru -- array JSONB com 1 elemento por subscricao. Cada dict carrega
    # as colunas da fonte (subscricao_id, serie_id, ua_id, quantidade,
    # valor_unitario/valor_atualizado, total_bruto, total_liquido, etc).
    payload: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    # Quantidade de subscricoes no array (observabilidade sem expandir payload).
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # SHA256 do payload serializado canonicamente (sort_keys=True). Dedupe de
    # re-fetch + deteccao de drift historico.
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Timestamp do fetch (nao do snapshot interno do Bitfin).
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Versao do adapter Bitfin que rodou o fetch.
    fetched_by_version: Mapped[str] = mapped_column(String(128), nullable=False)
