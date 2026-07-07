"""LocalDiskStorage -- filesystem implementation (dev default; prod fallback).

Root comes from `settings.FILE_STORAGE_LOCAL_ROOT` (StateDirectory in prod,
mirroring the dossier-attachments setup). Anti path-escape guard mirrors
`credito/services/document.py::resolve_storage_path`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.shared.storage._base import (
    ObjectNotFoundError,
    StorageBackend,
    StorageError,
    StoredObject,
    validate_key,
)


class LocalDiskStorage(StorageBackend):
    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self._root / key).resolve()
        if not str(path).startswith(str(self._root)):
            raise StorageError(f"Key escapa do storage root: {key!r}")
        return path

    async def put(self, key: str, data: bytes) -> StoredObject:
        path = self._path(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)
        return StoredObject(key=key, size_bytes=len(data))

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(f"Objeto nao encontrado: {key}") from exc

    async def exists(self, key: str) -> bool:
        path = self._path(key)
        return await asyncio.to_thread(path.is_file)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)
