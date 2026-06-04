"""UploadFileSource -- arquivos subidos em lote pela UI (fallback de onboarding).

Para clientes onde nao temos acesso ao filesystem do banco/servidor, o
operador sobe os arquivos de retorno em lote. O backend os deposita numa area
de staging por tenant; esta FileSource le de la.

Config esperada (`file_source`):
    {
        "mode": "upload",
        "staging_path": "/var/lib/strata/cobranca_upload/<tenant>"
    }

Mesma mecanica do `local_path` (le todos os arquivos da pasta de staging),
mas semanticamente distinta: a origem e um upload manual, registrado como
`file_source_mode = upload` no bronze. O consumo do staging (mover/limpar
apos pousar) e responsabilidade do landing/limpeza, nao desta classe.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.modules.integracoes.filesource._base import FileSource, RawFile
from app.warehouse.cnab_raw_arquivo import FILE_SOURCE_UPLOAD


class UploadFileSource(FileSource):
    mode = FILE_SOURCE_UPLOAD

    async def fetch(self, config: dict) -> list[RawFile]:
        staging = config.get("staging_path")
        glob = config.get("glob", "*")
        if not staging:
            raise ValueError("upload file_source exige 'staging_path' na config")
        return await asyncio.to_thread(self._read_dir, staging, glob)

    @staticmethod
    def _read_dir(staging: str, glob: str) -> list[RawFile]:
        base = Path(staging)
        if not base.is_dir():
            # Staging vazio/inexistente = nada subido ainda (nao e erro).
            return []
        arquivos: list[RawFile] = []
        for fp in sorted(base.glob(glob)):
            if not fp.is_file():
                continue
            arquivos.append(
                RawFile.from_bytes(
                    fp.name, fp.read_bytes(), source_mode=FILE_SOURCE_UPLOAD
                )
            )
        return arquivos
