"""File Gateway (/api/v1/filedrop/*) -- auth de agente + isolamento multi-tenant.

Cobre o checklist §10 do CLAUDE.md para o PR da landing zone:
- endpoint novo: teste de credencial ausente/invalida/revogada (401 — auth e
  por token de agente, nao ha usuario/JWT, logo nao existe cenario 403);
- service novo (`filedrop.receive_files`): isolamento — dedup e registry sao
  escopados por tenant; tenant B nunca enxerga (nem colide com) dado de A.

Storage e trocado por `LocalDiskStorage(tmp_path)` via monkeypatch no modulo
do service — nenhum teste toca S3 nem o root local configurado no .env.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.models.agent_credential import AgentCredential
from app.modules.integracoes.models.file_landing import FileLanding
from app.modules.integracoes.services import filedrop as svc
from app.shared.audit_log.decision_log import DecisionLog
from app.shared.identity.tenant import Tenant
from app.shared.storage.local_disk import LocalDiskStorage

LABEL = "cobranca_cnab"


# ---- Helpers / fixtures ------------------------------------------------------


async def _create_agent(
    tenant_id: UUID,
    *,
    labels: tuple[str, ...] = (LABEL,),
    name: str = "Agente Teste",
) -> tuple[AgentCredential, str]:
    """Cria credencial ativa e devolve (row, token plaintext)."""
    token = svc.generate_token()
    async with AsyncSessionLocal() as db:
        cred = AgentCredential(
            tenant_id=tenant_id,
            name=name,
            token_hash=svc.hash_token(token),
            watch_config={
                "scan_interval_minutes": 5,
                "watches": [
                    {"path": "C:/Retorno", "glob": "*", "source_label": label}
                    for label in labels
                ],
            },
        )
        db.add(cred)
        await db.commit()
        await db.refresh(cred)
    return cred, token


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch, tmp_path) -> LocalDiskStorage:
    """Aponta o storage do service para um diretorio temporario isolado."""
    backend = LocalDiskStorage(str(tmp_path))
    monkeypatch.setattr(svc, "get_storage_backend", lambda: backend)
    return backend


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _upload(
    client: AsyncClient,
    token: str,
    files: list[tuple[str, bytes]],
    *,
    source_label: str = LABEL,
    agent_version: str | None = None,
):
    headers = _auth(token)
    if agent_version:
        headers["X-Agent-Version"] = agent_version
    return await client.post(
        "/api/v1/filedrop/upload",
        headers=headers,
        data={"source_label": source_label},
        files=[("files", (nome, body, "application/octet-stream")) for nome, body in files],
    )


async def _landing_rows(tenant_id: UUID) -> list[FileLanding]:
    async with AsyncSessionLocal() as db:
        return list(
            (
                await db.execute(
                    select(FileLanding).where(FileLanding.tenant_id == tenant_id)
                )
            ).scalars()
        )


# ---- Auth do endpoint (checklist §10: endpoint novo) -------------------------


@pytest.mark.asyncio
async def test_upload_sem_token_retorna_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/filedrop/upload",
        data={"source_label": LABEL},
        files=[("files", ("a.ret", b"x", "text/plain"))],
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_upload_token_invalido_retorna_401(client: AsyncClient) -> None:
    r = await _upload(client, "strata_agt_token-que-nao-existe", [("a.ret", b"x")])
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_token_revogado_retorna_401(
    client: AsyncClient, tenant_a: Tenant
) -> None:
    cred, token = await _create_agent(tenant_a.id)
    async with AsyncSessionLocal() as db:
        row = await db.get(AgentCredential, cred.id)
        assert row is not None
        row.revoked_at = datetime.now(UTC)
        await db.commit()

    r = await client.get("/api/v1/filedrop/ping", headers=_auth(token))
    assert r.status_code == 401
    r = await _upload(client, token, [("a.ret", b"x")])
    assert r.status_code == 401


# ---- /ping -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ping_marca_heartbeat_e_devolve_watch_config(
    client: AsyncClient, tenant_a: Tenant
) -> None:
    cred, token = await _create_agent(tenant_a.id)
    assert cred.last_seen_at is None

    r = await client.get(
        "/api/v1/filedrop/ping",
        headers={**_auth(token), "X-Agent-Version": "1.2.3"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agent_name"] == cred.name
    assert body["watch_config"]["watches"][0]["source_label"] == LABEL
    assert body["max_file_bytes"] > 0

    async with AsyncSessionLocal() as db:
        row = await db.get(AgentCredential, cred.id)
        assert row is not None
        assert row.last_seen_at is not None
        assert row.agent_version == "1.2.3"


# ---- Upload: happy path + validacoes ------------------------------------------


@pytest.mark.asyncio
async def test_upload_grava_registry_blob_e_decision_log(
    client: AsyncClient, tenant_a: Tenant, storage: LocalDiskStorage
) -> None:
    _, token = await _create_agent(tenant_a.id)
    conteudo = b"02RETORNO01COBRANCA...trailer"

    r = await _upload(client, token, [("CB070701.RET", conteudo)], agent_version="1.0.0")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["received"] == 1
    assert body["duplicates"] == 0
    assert body["rejected"] == 0
    assert body["results"][0]["status"] == svc.STATUS_RECEIVED

    rows = await _landing_rows(tenant_a.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.source_label == LABEL
    assert row.nome_arquivo == "CB070701.RET"
    assert row.size_bytes == len(conteudo)
    assert row.agent_version == "1.0.0"
    # Key isolada por tenant: primeiro segmento e o tenant_id.
    assert row.storage_key.startswith(f"{tenant_a.id}/")
    # Blob realmente persistido no backend.
    assert await storage.get(row.storage_key) == conteudo

    async with AsyncSessionLocal() as db:
        logs = list(
            (
                await db.execute(
                    select(DecisionLog).where(
                        DecisionLog.tenant_id == tenant_a.id,
                        DecisionLog.rule_or_model == "file_gateway",
                    )
                )
            ).scalars()
        )
    assert len(logs) == 1
    assert logs[0].output["received"] == 1


@pytest.mark.asyncio
async def test_upload_dedup_por_sha_no_mesmo_tenant(
    client: AsyncClient, tenant_a: Tenant, storage: LocalDiskStorage
) -> None:
    _, token = await _create_agent(tenant_a.id)
    conteudo = b"mesmo conteudo"

    r1 = await _upload(client, token, [("a.ret", conteudo)])
    assert r1.json()["received"] == 1

    # Reenvio (retry do agente) — mesmo conteudo, nome diferente: duplicate.
    r2 = await _upload(client, token, [("b.ret", conteudo)])
    body = r2.json()
    assert body["received"] == 0
    assert body["duplicates"] == 1

    # Duplicado DENTRO do mesmo batch tambem colapsa.
    r3 = await _upload(client, token, [("c.ret", b"novo"), ("d.ret", b"novo")])
    body = r3.json()
    assert body["received"] == 1
    assert body["duplicates"] == 1

    assert len(await _landing_rows(tenant_a.id)) == 2  # conteudo + novo


@pytest.mark.asyncio
async def test_upload_source_label_fora_da_watch_config_rejeita_batch(
    client: AsyncClient, tenant_a: Tenant, storage: LocalDiskStorage
) -> None:
    _, token = await _create_agent(tenant_a.id, labels=(LABEL,))

    r = await _upload(
        client, token, [("a.xml", b"<xml/>")], source_label="bitfin_xml_operacoes"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["received"] == 0
    assert body["rejected"] == 1
    assert "nao autorizado" in body["results"][0]["motivo"]
    assert await _landing_rows(tenant_a.id) == []


@pytest.mark.asyncio
async def test_upload_arquivo_vazio_e_oversize_rejeitados(
    client: AsyncClient,
    tenant_a: Tenant,
    storage: LocalDiskStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, token = await _create_agent(tenant_a.id)
    monkeypatch.setattr(get_settings(), "FILEDROP_MAX_FILE_BYTES", 8)

    r = await _upload(
        client,
        token,
        [("vazio.ret", b""), ("grande.ret", b"123456789"), ("ok.ret", b"12345")],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["received"] == 1
    assert body["rejected"] == 2
    motivos = {res["nome_arquivo"]: res for res in body["results"]}
    assert motivos["vazio.ret"]["status"] == svc.STATUS_REJECTED
    assert "excede" in motivos["grande.ret"]["motivo"]
    assert motivos["ok.ret"]["status"] == svc.STATUS_RECEIVED


@pytest.mark.asyncio
async def test_upload_batch_acima_do_limite_retorna_413(
    client: AsyncClient,
    tenant_a: Tenant,
    storage: LocalDiskStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, token = await _create_agent(tenant_a.id)
    monkeypatch.setattr(get_settings(), "FILEDROP_MAX_FILES_PER_REQUEST", 2)

    r = await _upload(
        client, token, [("a.ret", b"a"), ("b.ret", b"b"), ("c.ret", b"c")]
    )
    assert r.status_code == 413
    assert await _landing_rows(tenant_a.id) == []


# ---- Isolamento multi-tenant (checklist §10: service novo) ---------------------


@pytest.mark.asyncio
async def test_isolamento_dedup_nao_cruza_tenants(
    client: AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    storage: LocalDiskStorage,
) -> None:
    """Mesmo conteudo + mesmo source_label em tenants diferentes: os dois
    recebem `received` — dedup e por (tenant, source_label, sha256), nunca
    global. Colapsar cross-tenant vazaria a EXISTENCIA do arquivo de A para B.
    """
    _, token_a = await _create_agent(tenant_a.id, name="Agente A")
    _, token_b = await _create_agent(tenant_b.id, name="Agente B")
    conteudo = b"retorno identico nos dois tenants"

    ra = await _upload(client, token_a, [("ret.ret", conteudo)])
    assert ra.json()["received"] == 1

    rb = await _upload(client, token_b, [("ret.ret", conteudo)])
    body_b = rb.json()
    assert body_b["received"] == 1, "dedup vazou entre tenants"
    assert body_b["duplicates"] == 0

    rows_a = await _landing_rows(tenant_a.id)
    rows_b = await _landing_rows(tenant_b.id)
    assert len(rows_a) == 1
    assert len(rows_b) == 1
    # Mesmo sha, linhas e blobs distintos, cada um no prefixo do seu tenant.
    assert rows_a[0].sha256 == rows_b[0].sha256
    assert rows_a[0].storage_key.startswith(f"{tenant_a.id}/")
    assert rows_b[0].storage_key.startswith(f"{tenant_b.id}/")
    assert rows_a[0].storage_key != rows_b[0].storage_key


@pytest.mark.asyncio
async def test_isolamento_registry_e_audit_escopados_pela_credencial(
    client: AsyncClient,
    tenant_a: Tenant,
    tenant_b: Tenant,
    storage: LocalDiskStorage,
) -> None:
    """Upload com credencial de A so cria linhas (registry + decision_log)
    de A — tenant do dado vem da credencial, nao de input do agente."""
    cred_a, token_a = await _create_agent(tenant_a.id, name="Agente A")

    r = await _upload(client, token_a, [("so-do-a.ret", b"dado do tenant A")])
    assert r.json()["received"] == 1

    assert await _landing_rows(tenant_b.id) == []
    rows_a = await _landing_rows(tenant_a.id)
    assert len(rows_a) == 1
    assert rows_a[0].agent_credential_id == cred_a.id

    async with AsyncSessionLocal() as db:
        logs_b = list(
            (
                await db.execute(
                    select(DecisionLog).where(
                        DecisionLog.tenant_id == tenant_b.id,
                        DecisionLog.rule_or_model == "file_gateway",
                    )
                )
            ).scalars()
        )
    assert logs_b == []
