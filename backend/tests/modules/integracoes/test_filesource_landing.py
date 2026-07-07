"""LandingFileSource + consumo de file_landing pelo ETL de cobranca (§10).

Cobre o elo landing zone -> pipeline CNAB:
- pendentes sao lidos, pousam no bronze com file_source_mode="landing" e
  ganham consumed_at; re-execucao e no-op;
- zip e normalizado NA ENTRADA (magic bytes, nao hint): N documentos internos;
- duplicado no bronze (ja ingerido pelo mount legado) TAMBEM consome;
- isolamento: drenar tenant A nao toca pendencia de tenant B.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.cobranca.etl import sync_cobranca
from app.modules.integracoes.filesource import landing as landing_mod
from app.modules.integracoes.models.file_landing import FileLanding
from app.shared.identity.tenant import Tenant
from app.shared.storage.local_disk import LocalDiskStorage
from app.warehouse.cnab_raw_arquivo import CnabRawArquivo

CONFIG = {"file_source": {"mode": "landing", "source_labels": ["cobranca_cnab"]}}

# Header CNAB400-ish: classificado como retorno; banco desconhecido (bronze-only).
_CNAB = "02RETORNO01COBRANCA       00000000000000000000TESTE   999TESTBANK QA \n"


def _cnab(sufixo: str) -> bytes:
    return (_CNAB + f"1DETALHE {sufixo}\n").encode("latin-1")


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch, tmp_path) -> LocalDiskStorage:
    backend = LocalDiskStorage(str(tmp_path))
    monkeypatch.setattr(landing_mod, "get_storage_backend", lambda: backend)
    return backend


async def _seed_pending(
    storage: LocalDiskStorage,
    tenant_id: UUID,
    *,
    nome: str,
    body: bytes,
    source_label: str = "cobranca_cnab",
    consumed: bool = False,
) -> UUID:
    import hashlib

    sha = hashlib.sha256(body).hexdigest()
    key = f"{tenant_id}/sem-ua/{source_label}/2026/07/{sha}"
    await storage.put(key, body)
    async with AsyncSessionLocal() as db:
        row = FileLanding(
            tenant_id=tenant_id,
            source_label=source_label,
            nome_arquivo=nome,
            sha256=sha,
            size_bytes=len(body),
            storage_key=key,
            consumed_at=datetime.now(UTC) if consumed else None,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row.id


async def _landing_row(row_id: UUID) -> FileLanding:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(select(FileLanding).where(FileLanding.id == row_id))
        ).scalar_one()


@pytest.mark.asyncio
async def test_landing_consome_pendentes_e_marca_consumed(
    tenant_a: Tenant, storage: LocalDiskStorage
) -> None:
    id_a = await _seed_pending(storage, tenant_a.id, nome="a.ret", body=_cnab("A"))
    id_b = await _seed_pending(storage, tenant_a.id, nome="b.ret", body=_cnab("B"))
    # Ja consumido e label fora da config: nao entram no ciclo.
    id_done = await _seed_pending(
        storage, tenant_a.id, nome="done.ret", body=_cnab("D"), consumed=True
    )
    id_outro = await _seed_pending(
        storage, tenant_a.id, nome="nfe.zip", body=_cnab("X"), source_label="fiscal_nfe"
    )

    async with AsyncSessionLocal() as db:
        result = await sync_cobranca(db, tenant_id=tenant_a.id, config=CONFIG)
    assert result.arquivos_vistos == 2
    assert result.arquivos_novos == 2

    async with AsyncSessionLocal() as db:
        bronze = (
            (
                await db.execute(
                    select(CnabRawArquivo).where(
                        CnabRawArquivo.tenant_id == tenant_a.id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(bronze) == 2
    assert {b.file_source_mode for b in bronze} == {"landing"}

    assert (await _landing_row(id_a)).consumed_at is not None
    assert (await _landing_row(id_b)).consumed_at is not None
    assert (await _landing_row(id_outro)).consumed_at is None
    assert (await _landing_row(id_done)).consumed_at is not None

    # Re-execucao: nada pendente, nada novo.
    async with AsyncSessionLocal() as db:
        result2 = await sync_cobranca(db, tenant_id=tenant_a.id, config=CONFIG)
    assert result2.arquivos_vistos == 0


@pytest.mark.asyncio
async def test_zip_e_normalizado_na_entrada(
    tenant_a: Tenant, storage: LocalDiskStorage
) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dia1.ret", _cnab("Z1").decode("latin-1"))
        zf.writestr("dia2.ret", _cnab("Z2").decode("latin-1"))
        zf.writestr("vazio.txt", "")  # ignorado (0 bytes)
    row_id = await _seed_pending(
        storage, tenant_a.id, nome="LOTE.zip", body=buf.getvalue()
    )

    async with AsyncSessionLocal() as db:
        result = await sync_cobranca(db, tenant_id=tenant_a.id, config=CONFIG)
    assert result.arquivos_vistos == 2  # documentos internos, nao o container
    assert result.arquivos_novos == 2

    async with AsyncSessionLocal() as db:
        nomes = (
            (
                await db.execute(
                    select(CnabRawArquivo.nome_arquivo).where(
                        CnabRawArquivo.tenant_id == tenant_a.id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert sorted(nomes) == ["LOTE.zip/dia1.ret", "LOTE.zip/dia2.ret"]
    assert (await _landing_row(row_id)).consumed_at is not None


@pytest.mark.asyncio
async def test_duplicado_no_bronze_tambem_consome(
    tenant_a: Tenant, storage: LocalDiskStorage
) -> None:
    body = _cnab("REPETIDO")
    id_1 = await _seed_pending(storage, tenant_a.id, nome="v1.ret", body=body)
    async with AsyncSessionLocal() as db:
        await sync_cobranca(db, tenant_id=tenant_a.id, config=CONFIG)

    # Mesmo conteudo re-aparece na landing (ex.: ja ingerido pelo mount antes).
    # Dedup da landing zone e por (tenant, label, sha) — usar outro label
    # simula a colisao real de conteudo com o bronze.
    id_2 = await _seed_pending(
        storage, tenant_a.id, nome="v2.ret", body=body,
        source_label="cobranca_cnab_remessa",
    )
    config2 = {
        "file_source": {
            "mode": "landing",
            "source_labels": ["cobranca_cnab", "cobranca_cnab_remessa"],
        }
    }
    async with AsyncSessionLocal() as db:
        result = await sync_cobranca(db, tenant_id=tenant_a.id, config=config2)
    assert result.arquivos_vistos == 1
    assert result.arquivos_duplicados == 1
    assert result.arquivos_novos == 0
    assert (await _landing_row(id_1)).consumed_at is not None
    assert (await _landing_row(id_2)).consumed_at is not None, (
        "duplicado no bronze deve consumir a pendencia mesmo assim"
    )


@pytest.mark.asyncio
async def test_isolamento_drenar_a_nao_toca_pendencia_de_b(
    tenant_a: Tenant, tenant_b: Tenant, storage: LocalDiskStorage
) -> None:
    id_b = await _seed_pending(storage, tenant_b.id, nome="b.ret", body=_cnab("B1"))

    async with AsyncSessionLocal() as db:
        result = await sync_cobranca(db, tenant_id=tenant_a.id, config=CONFIG)
    assert result.arquivos_vistos == 0

    row_b = await _landing_row(id_b)
    assert row_b.consumed_at is None, "pendencia de B consumida por sync de A"
    async with AsyncSessionLocal() as db:
        bronze_b = (
            await db.execute(
                select(CnabRawArquivo).where(CnabRawArquivo.tenant_id == tenant_b.id)
            )
        ).scalars().all()
    assert bronze_b == []
