"""StorageBackend -- object storage abstraction for the multi-tenant landing zone.

Every externally ingested file (CNAB, operational XMLs, UI uploads) lands
behind this interface. Callers address content by *key* only; where bytes
physically live (local disk in dev, S3 bucket-per-tenant in prod) is an
implementation detail selected via `settings.FILE_STORAGE_BACKEND`.

Key convention (enforced by `validate_key`):

    <tenant_id>/<ua_id|sem-ua>/<source_label>/<yyyy>/<mm>/<sha256>

The first segment MUST be the tenant id -- the S3 implementation uses it to
resolve the per-tenant bucket, and the local implementation uses it as the
per-tenant directory. Keys are relative, forward-slash separated, and never
contain `..` (guarded here, once, for every backend).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


class StorageError(RuntimeError):
    """Storage-level failure (invalid key, missing object, backend error)."""


class ObjectNotFoundError(StorageError):
    """Requested key does not exist in the backend."""


@dataclass(frozen=True)
class StoredObject:
    """Receipt of a successful `put`."""

    key: str
    size_bytes: int


def validate_key(key: str) -> str:
    """Normalize + guard a storage key. Returns the key or raises StorageError."""
    if not key or key.startswith(("/", "\\")):
        raise StorageError(f"Storage key invalida: {key!r}")
    parts = key.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise StorageError(f"Storage key invalida (segmento vazio ou '..'): {key!r}")
    if any(("\\" in p) or (":" in p) for p in parts):
        raise StorageError(f"Storage key invalida (caractere proibido): {key!r}")
    return key


class StorageBackend(abc.ABC):
    """Async object store: put/get/exists/delete by key."""

    @abc.abstractmethod
    async def put(self, key: str, data: bytes) -> StoredObject:
        """Store `data` under `key` (idempotent overwrite)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def get(self, key: str) -> bytes:
        """Read the object; raises ObjectNotFoundError when absent."""
        raise NotImplementedError

    @abc.abstractmethod
    async def exists(self, key: str) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the object; no-op when absent."""
        raise NotImplementedError
