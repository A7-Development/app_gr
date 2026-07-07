"""LocalPathFileSource -- varre diretorio(s) no servidor (caso A7 hoje).

Config esperada (`file_source` em tenant_source_config.config), duas formas:

    # 1 diretorio (forma classica):
    { "mode": "local_path", "path": "/srv/.../Retorno/Processado", "glob": "*" }

    # varios diretorios (ex.: Retorno + Remessa na mesma inbox):
    { "mode": "local_path", "roots": [
        { "path": "/srv/.../Retorno/Processado", "glob": "*" },
        { "path": "/srv/.../Remessa/Enviado",    "glob": "*" }
    ] }

Le todos os arquivos que casam com `glob` em cada `path`. O sync classifica
cada arquivo (retorno/remessa) pelo header CNAB, entao misturar as pastas numa
so fetch e exatamente o esperado. IO de filesystem (sync) roda em thread pool
via `asyncio.to_thread`. Dedup (nao reprocessar arquivo ja visto) e do landing
via sha -- aqui devolvemos todos os candidatos.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.filesource._base import FileSource, RawFile
from app.warehouse.cnab_raw_arquivo import FILE_SOURCE_LOCAL_PATH


class LocalPathFileSource(FileSource):
    mode = FILE_SOURCE_LOCAL_PATH

    async def fetch(
        self,
        config: dict,
        *,
        db: AsyncSession | None = None,  # ignorado (fonte pura)
        tenant_id: UUID | None = None,  # ignorado (fonte pura)
    ) -> list[RawFile]:
        roots = self._roots(config)
        return await asyncio.to_thread(self._read_roots, roots)

    @staticmethod
    def _roots(config: dict) -> list[tuple[str, str]]:
        """(path, glob) por raiz. Aceita `roots: [...]` ou `path`+`glob` solo."""
        raw_roots = config.get("roots")
        if raw_roots:
            roots: list[tuple[str, str]] = []
            for r in raw_roots:
                path = r.get("path")
                if not path:
                    raise ValueError("local_path root exige 'path' na config")
                roots.append((path, r.get("glob", "*")))
            return roots
        path = config.get("path")
        if not path:
            raise ValueError(
                "local_path file_source exige 'path' ou 'roots' na config"
            )
        return [(path, config.get("glob", "*"))]

    @classmethod
    def _read_roots(cls, roots: list[tuple[str, str]]) -> list[RawFile]:
        arquivos: list[RawFile] = []
        for path, glob in roots:
            arquivos.extend(cls._read_dir(path, glob))
        return arquivos

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
