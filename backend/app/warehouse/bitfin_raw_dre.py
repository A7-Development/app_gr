"""wh_bitfin_raw_dre -- camada raw (bronze) das fontes DRE do Bitfin.

Padrao raw -> canonico definido no CLAUDE.md secao 13.2. Esta tabela armazena
o **payload cru** que o Bitfin devolveu para o DRE — em duas variantes
discriminadas por `tipo_origem`:

- `demonstrativo_resultado` -- linhas granulares de `UNLTD_A7CREDIT.dbo.
  DemonstrativoDeResultado` (1 linha por evento consolidado dentro de uma
  competencia; o Bitfin re-builda o snapshot inteiro de cada competencia).
- `vw_dre` -- linhas ja consolidadas de `ANALYTICS.dbo.vw_DRE` (mesma
  estrutura que o silver `wh_dre_mensal` consome hoje). Mantida como
  espelho para reconciliacao: "o que o Bitfin diz que e DRE" vs "o que
  nos calculamos a partir do granular".

Granularidade: 1 row de bronze = 1 fetch de competencia inteira. O
`payload` e o array JSONB de todas as linhas daquela competencia. UQ por
(tenant, tipo_origem, competencia, payload_sha256) faz dedupe de fetch
identico (no-op via ON CONFLICT DO NOTHING); fetch com conteudo alterado
cria nova row preservando o historico de snapshots.

NAO usa mixin `Auditable` (CLAUDE.md secao 14.1, excecao explicita): a raw
E a fonte; nao referencia outra fonte upstream. Proveniencia da raw e
direta — `fetched_at` + `fetched_by_version` + `payload_sha256`.
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

# Discriminator values — mantidos como string (e nao enum SQL) para evitar
# migration toda vez que adicionarmos nova fonte DRE no Bitfin. Validacao
# acontece na camada de aplicacao (`adapter`/`etl`), nao no schema.
TIPO_ORIGEM_DEMONSTRATIVO = "demonstrativo_resultado"
TIPO_ORIGEM_VW_DRE = "vw_dre"


class BitfinRawDre(Base):
    """Snapshot cru do DRE Bitfin, por (tenant, tipo_origem, competencia).

    Ver `app/modules/integracoes/adapters/erp/bitfin/etl.py::
    sync_bitfin_raw_dre_demonstrativo` e `sync_bitfin_raw_dre_vw` para os
    handlers que gravam aqui.
    """

    __tablename__ = "wh_bitfin_raw_dre"
    __table_args__ = (
        # Idempotencia: fetch identico (mesmo conteudo) e no-op via
        # ON CONFLICT. Fetch com qualquer alteracao no payload gera row
        # nova preservando historico de snapshots.
        UniqueConstraint(
            "tenant_id",
            "tipo_origem",
            "competencia",
            "payload_sha256",
            name="uq_wh_bitfin_raw_dre",
        ),
        # Acesso canonico: "ultimo snapshot por competencia/tipo do tenant".
        Index(
            "ix_wh_bitfin_raw_dre_tenant_tipo_competencia_fetched",
            "tenant_id",
            "tipo_origem",
            "competencia",
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

    # Particao logica entre as duas fontes DRE do Bitfin. String e nao enum
    # para evitar migration ao adicionar nova fonte (ex.: outra view ou
    # tabela transacional). Constantes em modulo: TIPO_ORIGEM_*.
    tipo_origem: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Competencia do snapshot. Para `demonstrativo_resultado`, derivada de
    # (Ano, Mes) na fonte -> date(Ano, Mes, 1). Para `vw_dre`, usa o campo
    # Competencia da view diretamente.
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Body cru — array JSONB com TODAS as linhas daquela competencia/tipo.
    # Cada elemento e um dict com as colunas da fonte (ja com alias snake_case).
    # Mappers de silver iteram via `jsonb_array_elements` ou Python loop.
    payload: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    # Quantidade de linhas no array. Util pra metricas/observabilidade sem
    # precisar expandir o payload (e pra detectar shrink anormal).
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # SHA256 do payload (array inteiro) serializado canonicamente
    # (sort_keys=True). Detecta:
    # (a) re-fetch redundante (bate no UQ, ON CONFLICT DO NOTHING)
    # (b) drift de dado historico (mesma competencia com payload diferente
    #     gera row nova; comparar shas mostra o que mudou)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Timestamp do fetch (nao do snapshot interno do Bitfin — para
    # `demonstrativo_resultado`, a coluna `Data` na fonte representa o
    # momento em que o Bitfin re-buildou o snapshot, NOT este fetched_at).
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Versao do adapter Bitfin que rodou o fetch. Permite saber se eventual
    # bug de extracao/mapeamento afetou ate qual versao.
    fetched_by_version: Mapped[str] = mapped_column(String(128), nullable=False)
