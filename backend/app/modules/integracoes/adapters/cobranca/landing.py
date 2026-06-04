"""Landing -- pousa um RawFile capturado no bronze (wh_cnab_raw_arquivo).

Idempotente por `sha256` (UNIQUE tenant+sha). Reprocessar o mesmo arquivo e
no-op: retorna a row existente com `created=False`, sinalizando ao caller que
nao ha o que reparsear. Arquivo com conteudo alterado gera row nova.

NAO parseia o conteudo -- so guarda o cru. O parsing por banco (registros de
detalhe -> wh_cnab_raw_ocorrencia) e o mapeamento para `wh_boleto` sao
camadas acima.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.cobranca.version import ADAPTER_VERSION
from app.modules.integracoes.filesource import RawFile
from app.warehouse.cnab_raw_arquivo import CnabRawArquivo


async def land_cnab_arquivo(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    banco: str,
    tipo_arquivo: str,
    layout: str,
    raw: RawFile,
    fetched_at: datetime | None = None,
) -> tuple[CnabRawArquivo, bool]:
    """Insere o arquivo cru no bronze (ON CONFLICT por sha = no-op).

    Returns:
        (arquivo, created) -- `created=True` quando a row foi inserida agora
        (deve ser parseada); `False` quando ja existia (skip).
    """
    fetched_at = fetched_at or datetime.now(UTC)

    stmt = (
        pg_insert(CnabRawArquivo)
        .values(
            id=uuid4(),
            tenant_id=tenant_id,
            banco=banco,
            tipo_arquivo=tipo_arquivo,
            nome_arquivo=raw.nome_arquivo,
            conteudo=raw.conteudo,
            sha256=raw.sha256,
            layout=layout,
            file_source_mode=raw.source_mode,
            fetched_at=fetched_at,
            fetched_by_version=ADAPTER_VERSION,
        )
        .on_conflict_do_nothing(constraint="uq_wh_cnab_raw_arquivo")
        .returning(CnabRawArquivo.id)
    )
    new_id = (await db.execute(stmt)).scalar_one_or_none()

    if new_id is not None:
        row = (
            await db.execute(
                select(CnabRawArquivo).where(CnabRawArquivo.id == new_id)
            )
        ).scalar_one()
        return row, True

    # Conflito: arquivo identico ja pousado antes.
    existing = (
        await db.execute(
            select(CnabRawArquivo).where(
                CnabRawArquivo.tenant_id == tenant_id,
                CnabRawArquivo.sha256 == raw.sha256,
            )
        )
    ).scalar_one()
    return existing, False
