"""wh_qitech_raw_relatorio -- camada raw (bronze) dos endpoints /netreport/.

Padrao raw -> canonico definido no CLAUDE.md secao 13.2. Esta tabela armazena
o **payload cru** que a QiTech devolveu pra cada combinacao
(tenant, tipo_de_mercado, data_posicao). Imutavel apos gravacao — se a fonte
re-publicar o mesmo dia, upsert pelo unique constraint atualiza o payload
mas o `payload_sha256` registra que mudou.

Uma unica tabela cobre os 23 tipos de relatorio QiTech (`outros-fundos`,
`rf`, `rf-fidc`, `conta-corrente`, ..., `mec`) — diferenciacao via coluna
`tipo_de_mercado`. Razao: schema da raw e identico (sempre {tenant, tipo,
data, payload, metadata de fetch}); explodir em 23 tabelas seria repeticao
sem ganho. Mappers canonicos especificos vivem em `adapters/admin/qitech/
mappers/<tipo>.py` e leem desta tabela quando o ETL re-mapear.

Granularidade: 1 linha por (tenant_id, tipo_de_mercado, data_posicao).
- Para tipos com sucesso (HTTP 200), `payload` e o body inteiro.
- Para tipos com "sem dados" (HTTP 400 + shape canonico), `payload` e o
  envelope vazio `{"relatórios": {}, "message": "..."}` — distincao
  feita via coluna `http_status`.

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QiTechRawRelatorio(Base):
    """Payload cru de um relatorio /netreport/ da QiTech, por dia.

    Ver `app/modules/integracoes/adapters/admin/qitech/reports.py` pro
    catalogo de `tipo_de_mercado` valido (TIPOS_DE_MERCADO_CONHECIDOS).
    """

    __tablename__ = "wh_qitech_raw_relatorio"
    __table_args__ = (
        # Idempotencia: re-rodar o ETL pro mesmo dia substitui via upsert.
        UniqueConstraint(
            "tenant_id",
            "tipo_de_mercado",
            "data_posicao",
            name="uq_wh_qitech_raw_relatorio",
        ),
        # Acesso canonico: "todas as raws de um tenant num dia / num tipo".
        Index(
            "ix_wh_qitech_raw_relatorio_tenant_tipo_data",
            "tenant_id",
            "tipo_de_mercado",
            "data_posicao",
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

    # Particao logica. Um dos 23 tipos do catalogo; mantem string (e nao
    # enum) pra nao precisar de migration toda vez que QiTech adicionar
    # endpoint novo no /netreport/.
    tipo_de_mercado: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # `data_posicao` e o param do path da QiTech (`/{aaaa-mm-dd}`), nao o
    # `dataDaPosição` interno do payload — fonte da verdade pra particionar.
    data_posicao: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Body cru exatamente como QiTech retornou. JSONB pra indexar caminhos
    # especificos depois (ex.: GIN em `payload->'relatórios'`) sem migration.
    # Pode ser NULL quando a fonte e CSV/texto puro (ai vai em payload_text).
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Para fontes que devolvem arquivo de texto (CSV, TSV) em vez de JSON
    # (ex.: relatorios assincronos /queue/scheduler/report/* da QiTech).
    # Mantemos no campo separado pra evitar overhead de JSONB com texto cru
    # e permitir LIKE/regex sem cast. Pelo menos 1 dos dois (payload OU
    # payload_text) deve estar preenchido — invariante checada na app.
    payload_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 200 OK ou 400-com-shape-canonico (envelope vazio "sem dados pra esse
    # mercado neste dia"). Ambos sao gravados; distinguir um do outro pra
    # metricas de cobertura ("quantos tipos com dados o tenant teve hoje?").
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)

    # SHA256 do payload bruto serializado canonicamente. Detecta:
    # (a) re-fetch redundante (mesmo dia, mesmo body — n bate no upsert)
    # (b) drift de dado historico ("a QiTech mudou algo no dia X retroativo?")
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Timestamp do fetch (nao do `dataDaPosição` interno, nao do
    # `ingested_at` do canonico — momento exato em que o adapter recebeu).
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Versao do adapter QiTech que rodou o fetch. Permite saber se eventual
    # bug de paginacao/parse afetou ate qual versao.
    fetched_by_version: Mapped[str] = mapped_column(String(128), nullable=False)
