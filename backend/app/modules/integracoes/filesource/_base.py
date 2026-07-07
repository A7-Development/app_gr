"""FileSource -- camada de transporte de arquivos (CLAUDE.md secao 13).

Abstrai *de onde vem o arquivo* da conciliacao de cobranca. A localizacao e o
modo de transporte sao **config de tenant** (`tenant_source_config.config.
file_source`), nunca codigo. O que varia por cliente (onde mora o arquivo)
fica isolado aqui; o que varia por banco (layout CNAB) fica no parser; o
canonico (`wh_boleto`) e invariante.

Modos suportados (espelham `cnab_raw_arquivo.FILE_SOURCE_*`):
- `local_path` -- varre um path no servidor + glob (caso A7 legado)
- `upload`     -- le arquivos subidos em lote pela UI (staging por tenant)
- `landing`    -- le pendentes da landing zone (`file_landing` + storage),
                  alimentada pelo Strata Collector no servidor do cliente
- `api`        -- futuro; aceito como cadastro mas sem handler ainda

FileSources de filesystem NAO tocam o banco -- so devolvem `RawFile`s. O modo
`landing` e a excecao deliberada: seu indice de pendencia E uma tabela
(`file_landing`), por isso `fetch` aceita `db`/`tenant_id` opcionais (os
modos puros ignoram). A deduplicacao por sha acontece no landing do bronze
(`adapters/cobranca/landing.py`), via UNIQUE.
"""

from __future__ import annotations

import abc
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# CNAB e fixed-width em encoding latin-1 (cp1252) na pratica brasileira.
# Decodificamos com latin-1 (nunca falha em byte algum) e guardamos como texto.
CNAB_ENCODING = "latin-1"


@dataclass(frozen=True)
class RawFile:
    """Um arquivo capturado, antes de pousar no bronze."""

    nome_arquivo: str
    conteudo: str  # texto decodificado (latin-1)
    sha256: str
    source_mode: str  # FILE_SOURCE_* que produziu este arquivo
    # Ponteiro pro registro da landing zone que originou este arquivo (modo
    # `landing`): o ETL marca `file_landing.consumed_at` apos processar.
    # None nos modos de filesystem. Um zip da landing gera N RawFiles com o
    # MESMO landing_id (marcado uma vez; idempotente).
    landing_id: UUID | None = None

    @classmethod
    def from_bytes(
        cls,
        nome: str,
        data: bytes,
        *,
        source_mode: str,
        landing_id: UUID | None = None,
    ) -> RawFile:
        texto = data.decode(CNAB_ENCODING)
        sha = hashlib.sha256(data).hexdigest()
        return cls(
            nome_arquivo=nome,
            conteudo=texto,
            sha256=sha,
            source_mode=source_mode,
            landing_id=landing_id,
        )


class FileSource(abc.ABC):
    """Estrategia de captura de arquivos. Uma implementacao por modo."""

    #: identificador do modo (FILE_SOURCE_*)
    mode: str

    @abc.abstractmethod
    async def fetch(
        self,
        config: dict,
        *,
        db: AsyncSession | None = None,
        tenant_id: UUID | None = None,
    ) -> list[RawFile]:
        """Captura os arquivos disponiveis conforme a config do tenant.

        `config` e o bloco `file_source` de `tenant_source_config.config`
        (ja descriptografado quando houver credencial). Retorna todos os
        arquivos candidatos; a deduplicacao por sha e do landing.

        `db`/`tenant_id` sao usados apenas pelo modo `landing` (indice de
        pendencia em tabela); os modos de filesystem ignoram.
        """
        raise NotImplementedError
