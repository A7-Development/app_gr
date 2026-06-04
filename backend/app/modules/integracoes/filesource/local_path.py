"""LocalPathFileSource -- varre um diretorio no servidor (caso A7 hoje).

Config esperada (`file_source` em tenant_source_config.config):
    {
        "mode": "local_path",
        "path": "//srv/.../Conciliacao/Retorno/Bradesco",
        "glob": "*.RET"
    }

Le todos os arquivos que casam com `glob` em `path`. IO de filesystem (sync)
roda em thread pool via `asyncio.to_thread` para nao bloquear o event loop.
A deduplicacao (nao reprocessar arquivo ja visto) e feita pelo landing via
sha -- aqui devolvemos todos os candidatos.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.modules.integracoes.filesource._base import FileSource, RawFile
from app.warehouse.cnab_raw_arquivo import FILE_SOURCE_LOCAL_PATH


class LocalPathFileSource(FileSource):
    mode = FILE_SOURCE_LOCAL_PATH

    async def fetch(self, config: dict) -> list[RawFile]:
        path = config.get("path")
        glob = config.get("glob", "*")
        if not path:
            raise ValueError("local_path file_source exige 'path' na config")
        return await asyncio.to_thread(self._read_dir, path, glob)

    @staticmethod
    def _read_dir(path: str, glob: str) -> list[RawFile]:
        base = Path(path)
        if not base.is_dir():
            raise FileNotFoundError(f"Diretorio de cobranca nao encontrado: {path}")
        arquivos: list[RawFile] = []
        for fp in sorted(base.glob(glob)):
            if not fp.is_file():
                continue
            arquivos.append(
                RawFile.from_bytes(
                    fp.name, fp.read_bytes(), source_mode=FILE_SOURCE_LOCAL_PATH
                )
            )
        return arquivos
