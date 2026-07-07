"""wh_cnab_raw_arquivo -- camada raw (bronze) dos arquivos CNAB de cobranca.

Padrao raw -> canonico (CLAUDE.md secao 13.2). Esta tabela guarda o ARQUIVO
CNAB **cru** (remessa ou retorno) exatamente como chegou do banco cobrador,
antes de qualquer parsing semantico. O conteudo fixed-width fica em `conteudo`
(texto), e a proveniencia do transporte (de onde veio: path local, upload,
API) fica em `file_source_mode`.

Granularidade: 1 row = 1 arquivo. `UNIQUE(tenant_id, sha256)` garante
idempotencia -- reprocessar o mesmo arquivo (mesmo conteudo) e no-op via
ON CONFLICT DO NOTHING; arquivo com qualquer alteracao gera row nova,
preservando o historico.

NAO usa mixin `Auditable` (CLAUDE.md secao 14.1, excecao explicita): a raw E
a fonte; nao referencia outra fonte upstream. Proveniencia direta --
`fetched_at` + `fetched_by_version` + `sha256` + `file_source_mode`.

O parsing CNAB (registros de detalhe -> `wh_cnab_raw_ocorrencia`) e a
normalizacao semantica (ocorrencia -> estado de boleto em `wh_boleto`)
acontecem em camadas acima, no adapter por banco. Ver
`app/modules/integracoes/adapters/cobranca/<banco>/`.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Banco cobrador -- valor armazenado (string, nao enum SQL, para evitar
# migration ao adicionar banco novo; validacao na camada de aplicacao).
# Espelha os SourceType COBRANCA_* sem o prefixo "cobranca:".
BANCO_BRADESCO = "bradesco"
BANCO_ITAU = "itau"
# BaaS/cobradores antes rotulados (errado) como "grafeno". O header CNAB declara
# a identidade REAL: codigo 274 + nome "BMP" (Money Plus) e codigo 310 + nome
# "VORTX DTVM" (Vortx). Grafeno usou BMP como cobrador e depois migrou p/ Vortx
# -- por isso 2 codigos. Usamos os nomes do emissor real (bmp/vortx).
BANCO_BMP = "bmp"
BANCO_VORTX = "vortx"
# Arquivo cujo banco nao foi reconhecido pelo header (pousa no bronze mesmo
# assim -- bronze-now -- para investigacao).
BANCO_DESCONHECIDO = "desconhecido"

# Tipo do arquivo CNAB.
TIPO_ARQUIVO_RETORNO = "retorno"  # banco -> nos (estado dos boletos)
TIPO_ARQUIVO_REMESSA = "remessa"  # nos -> banco (instrucoes enviadas)

# Modo de transporte que produziu o arquivo (espelha config.file_source.mode
# em `tenant_source_config`). `api` aceito mas inerte ate o handler existir.
FILE_SOURCE_LOCAL_PATH = "local_path"
FILE_SOURCE_UPLOAD = "upload"
# Landing zone multi-tenant (file_landing + StorageBackend), alimentada
# pelo Strata Collector no servidor do cliente.
FILE_SOURCE_LANDING = "landing"
FILE_SOURCE_API = "api"


class CnabRawArquivo(Base):
    """Arquivo CNAB cru (remessa/retorno) de um banco cobrador."""

    __tablename__ = "wh_cnab_raw_arquivo"
    __table_args__ = (
        # Idempotencia: arquivo identico (mesmo sha) e no-op via ON CONFLICT.
        UniqueConstraint("tenant_id", "sha256", name="uq_wh_cnab_raw_arquivo"),
        # Acesso canonico: "arquivos de retorno do Bradesco em D-1 do tenant".
        Index(
            "ix_wh_cnab_raw_arquivo_tenant_banco_tipo_data",
            "tenant_id",
            "banco",
            "tipo_arquivo",
            "data_ref",
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

    # Banco cobrador (BANCO_*). String e nao enum -- ver constantes acima.
    banco: Mapped[str] = mapped_column(String(20), nullable=False)
    # Remessa ou retorno (TIPO_ARQUIVO_*).
    tipo_arquivo: Mapped[str] = mapped_column(String(10), nullable=False)

    # Nome original do arquivo (ex.: "CB250603.RET"). Informativo/auditoria.
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    # Conteudo cru do arquivo (CNAB e fixed-width texto). Imutavel.
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    # SHA256 do conteudo -- idempotencia (UQ) + deteccao de drift.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Layout que se aplica a este arquivo (ex.: "cnab400_bradesco"). Diz ao
    # parser qual decoder usar. Vem de `tenant_source_config.config.layout`.
    layout: Mapped[str] = mapped_column(String(40), nullable=False)

    # Data-base do arquivo (data de geracao/competencia), inferida do header
    # CNAB ou do nome. Nullable ate o parser preencher.
    data_ref: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # Como o arquivo chegou (FILE_SOURCE_*) -- proveniencia do transporte.
    file_source_mode: Mapped[str] = mapped_column(String(20), nullable=False)

    # Quando foi capturado (nao a data interna do arquivo).
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Versao do FileSource/adapter que capturou.
    fetched_by_version: Mapped[str] = mapped_column(String(128), nullable=False)

    # Quando o arquivo foi mapeado para silver (NULL = ainda nao processado).
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
