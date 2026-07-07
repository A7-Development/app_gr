"""LandingFileSource -- le pendentes da landing zone (Strata Collector).

Fonte que consome o registry `file_landing` (arquivos empurrados pelo agente
no servidor do cliente para o File Gateway) em vez de filesystem/mount. E o
elo landing zone -> pipeline: devolve `RawFile`s com `landing_id` preenchido,
e o ETL marca `file_landing.consumed_at` apos processar.

Normalizacao de container NA ENTRADA (decisao 2026-07-07): cada blob e
farejado pelos magic bytes — comeca com `PK\\x03\\x04` = zip, e cada arquivo
interno vira um `RawFile` proprio (cliente que zipa por dia); caso contrario
o blob e o proprio documento. O hint `container` da watch_config e
expectativa, nao verdade: cliente que mistura solto+zip na mesma pasta
funciona igual.

Config (`tenant_source_config.config.file_source`):
    {"mode": "landing", "source_labels": ["cobranca_cnab", "cobranca_cnab_remessa"]}
    (aceita tambem "source_label" singular; `limit` opcional por ciclo)
"""

from __future__ import annotations

import io
import logging
import zipfile
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.filesource._base import FileSource, RawFile
from app.modules.integracoes.models.file_landing import FileLanding
from app.shared.storage import ObjectNotFoundError, get_storage_backend
from app.warehouse.cnab_raw_arquivo import FILE_SOURCE_LANDING

logger = logging.getLogger(__name__)

_ZIP_MAGIC = b"PK\x03\x04"


def _labels(config: dict) -> list[str]:
    labels = config.get("source_labels")
    if not labels:
        single = config.get("source_label")
        labels = [single] if single else []
    if not labels:
        raise ValueError(
            "landing file_source exige 'source_labels' (ou 'source_label') na config"
        )
    return list(labels)


class LandingFileSource(FileSource):
    mode = FILE_SOURCE_LANDING

    async def fetch(
        self,
        config: dict,
        *,
        db: AsyncSession | None = None,
        tenant_id: UUID | None = None,
    ) -> list[RawFile]:
        if db is None or tenant_id is None:
            raise ValueError(
                "landing file_source exige db e tenant_id (indice de pendencia "
                "mora em file_landing)"
            )
        labels = _labels(config)
        stmt = (
            select(FileLanding)
            .where(
                FileLanding.tenant_id == tenant_id,
                FileLanding.source_label.in_(labels),
                FileLanding.consumed_at.is_(None),
            )
            .order_by(FileLanding.received_at)
        )
        limit = config.get("limit")
        if limit:
            stmt = stmt.limit(int(limit))
        pending = (await db.execute(stmt)).scalars().all()

        storage = get_storage_backend()
        out: list[RawFile] = []
        for row in pending:
            try:
                blob = await storage.get(row.storage_key)
            except ObjectNotFoundError:
                # Registro sem blob = inconsistencia operacional; fica pendente
                # (visivel) e loga — nao some em silencio.
                logger.error(
                    "file_landing %s sem blob no storage (key=%s) — pulado",
                    row.id,
                    row.storage_key,
                )
                continue
            out.extend(_explode(row, blob))
        return out


def _explode(row: FileLanding, blob: bytes) -> list[RawFile]:
    """Normaliza container: zip vira N documentos, solto vira 1."""
    if not blob.startswith(_ZIP_MAGIC):
        return [
            RawFile.from_bytes(
                row.nome_arquivo, blob,
                source_mode=FILE_SOURCE_LANDING, landing_id=row.id,
            )
        ]
    out: list[RawFile] = []
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for info in zf.infolist():
                if info.is_dir() or info.file_size == 0:
                    continue
                data = zf.read(info)
                out.append(
                    RawFile.from_bytes(
                        f"{row.nome_arquivo}/{info.filename}", data,
                        source_mode=FILE_SOURCE_LANDING, landing_id=row.id,
                    )
                )
    except zipfile.BadZipFile:
        logger.warning(
            "file_landing %s parece zip (magic PK) mas nao abre — tratado como "
            "documento solto",
            row.id,
        )
        return [
            RawFile.from_bytes(
                row.nome_arquivo, blob,
                source_mode=FILE_SOURCE_LANDING, landing_id=row.id,
            )
        ]
    return out
