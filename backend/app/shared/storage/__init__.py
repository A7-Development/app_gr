"""Landing zone de arquivos multi-tenant -- ver docs do plano Strata Collector.

`get_storage_backend()` e o unico ponto de instancia: implementacao escolhida
por `settings.FILE_STORAGE_BACKEND` (`local` | `s3`).
"""

from functools import lru_cache

from app.core.config import get_settings
from app.shared.storage._base import (
    ObjectNotFoundError,
    StorageBackend,
    StorageError,
    StoredObject,
    validate_key,
)
from app.shared.storage.local_disk import LocalDiskStorage
from app.shared.storage.s3 import S3Storage

__all__ = [
    "LocalDiskStorage",
    "ObjectNotFoundError",
    "S3Storage",
    "StorageBackend",
    "StorageError",
    "StoredObject",
    "get_storage_backend",
    "validate_key",
]


@lru_cache
def get_storage_backend() -> StorageBackend:
    settings = get_settings()
    backend = settings.FILE_STORAGE_BACKEND.lower()
    if backend == "local":
        return LocalDiskStorage(settings.FILE_STORAGE_LOCAL_ROOT)
    if backend == "s3":
        return S3Storage(
            bucket_template=settings.FILE_STORAGE_S3_BUCKET_TEMPLATE,
            region=settings.FILE_STORAGE_S3_REGION,
        )
    raise StorageError(f"FILE_STORAGE_BACKEND desconhecido: {backend!r}")
