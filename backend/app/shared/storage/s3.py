"""S3Storage -- object storage em S3 (ou compativel), bucket por tenant.

Resolucao de bucket: `settings.FILE_STORAGE_S3_BUCKET_TEMPLATE` com o
placeholder `{tenant}` substituido pelo primeiro segmento da key (tenant_id).
Template sem `{tenant}` = bucket unico fixo (util em dev/staging).

Credenciais AWS: cadeia padrao do botocore (env vars AWS_ACCESS_KEY_ID /
AWS_SECRET_ACCESS_KEY, profile, ou role). Nunca por tenant -- o agente no
cliente NAO ve AWS; so o backend Strata fala com o bucket.

Import de `aiobotocore` e lazy: instalacoes que rodam com
FILE_STORAGE_BACKEND=local nao precisam da lib.
"""

from __future__ import annotations

from typing import Any

from app.shared.storage._base import (
    ObjectNotFoundError,
    StorageBackend,
    StorageError,
    StoredObject,
    validate_key,
)

_MISSING_CODES = {"404", "NoSuchKey", "NotFound"}


class S3Storage(StorageBackend):
    def __init__(self, *, bucket_template: str, region: str) -> None:
        if not bucket_template:
            raise StorageError(
                "FILE_STORAGE_S3_BUCKET_TEMPLATE vazio com FILE_STORAGE_BACKEND=s3"
            )
        try:
            from aiobotocore.session import get_session
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise StorageError(
                "aiobotocore nao instalado (necessario para FILE_STORAGE_BACKEND=s3)"
            ) from exc
        self._session = get_session()
        self._bucket_template = bucket_template
        self._region = region

    def _bucket_for(self, key: str) -> str:
        validate_key(key)
        tenant_segment = key.split("/", 1)[0]
        return self._bucket_template.format(tenant=tenant_segment)

    def _client(self) -> Any:
        return self._session.create_client("s3", region_name=self._region)

    @staticmethod
    def _is_missing(exc: Exception) -> bool:
        code = str(
            getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        )
        return code in _MISSING_CODES

    async def put(self, key: str, data: bytes) -> StoredObject:
        bucket = self._bucket_for(key)
        async with self._client() as s3:
            await s3.put_object(Bucket=bucket, Key=key, Body=data)
        return StoredObject(key=key, size_bytes=len(data))

    async def get(self, key: str) -> bytes:
        bucket = self._bucket_for(key)
        async with self._client() as s3:
            try:
                resp = await s3.get_object(Bucket=bucket, Key=key)
            except Exception as exc:
                if self._is_missing(exc):
                    raise ObjectNotFoundError(f"Objeto nao encontrado: {key}") from exc
                raise
            async with resp["Body"] as stream:
                return await stream.read()

    async def exists(self, key: str) -> bool:
        bucket = self._bucket_for(key)
        async with self._client() as s3:
            try:
                await s3.head_object(Bucket=bucket, Key=key)
            except Exception as exc:
                if self._is_missing(exc):
                    return False
                raise
        return True

    async def delete(self, key: str) -> None:
        bucket = self._bucket_for(key)
        async with self._client() as s3:
            await s3.delete_object(Bucket=bucket, Key=key)
