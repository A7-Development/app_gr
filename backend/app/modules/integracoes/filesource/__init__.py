"""FileSource -- transporte de arquivos da conciliacao de cobranca.

Factory `get_file_source(mode)` resolve a estrategia a partir do `mode` da
config do tenant. `api` e reconhecido (cadastravel) mas ainda nao tem handler
-- levanta `NotImplementedError` claro se alguem tentar ativar.
"""

from __future__ import annotations

from app.modules.integracoes.filesource._base import CNAB_ENCODING, FileSource, RawFile
from app.modules.integracoes.filesource.local_path import LocalPathFileSource
from app.modules.integracoes.filesource.upload import UploadFileSource
from app.warehouse.cnab_raw_arquivo import (
    FILE_SOURCE_API,
    FILE_SOURCE_LOCAL_PATH,
    FILE_SOURCE_UPLOAD,
)

_REGISTRY: dict[str, type[FileSource]] = {
    FILE_SOURCE_LOCAL_PATH: LocalPathFileSource,
    FILE_SOURCE_UPLOAD: UploadFileSource,
}


def get_file_source(mode: str) -> FileSource:
    """Instancia a FileSource para o `mode` da config do tenant."""
    if mode == FILE_SOURCE_API:
        raise NotImplementedError(
            "file_source mode 'api' aceito como cadastro mas ainda sem handler. "
            "Use 'local_path' ou 'upload' por ora."
        )
    cls = _REGISTRY.get(mode)
    if cls is None:
        raise ValueError(f"file_source mode desconhecido: {mode!r}")
    return cls()


__all__ = [
    "CNAB_ENCODING",
    "FileSource",
    "RawFile",
    "get_file_source",
]
