"""E2E tests for the evidence endpoints (attachments, notes, links, draft).

Coverage:
- Attachment: CRUD basico + tenant isolation + size limit + sha256 dedup
- Note:       CRUD basico + autor-only edit/delete + tenant isolation
- Link:       CRUD basico + tenant isolation
- Listing:    DossierListItem retorna progress + next_action populados
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.enums import DossierStatus, Module, Permission
from app.core.security import hash_password
from app.modules.credito.models.dossier import CreditDossier
from app.modules.credito.models.dossier_attachment import DossierAttachment
from app.modules.credito.models.dossier_step_link import DossierStepLink
from app.modules.credito.models.dossier_step_note import DossierStepNote
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission
from app.agentic.playbooks.models.definition import PlaybookDefinition

API_BASE = "/api/v1/credito"


# ─── Helpers ────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, email: str, password: str = "test-password") -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_DEMO_GRAPH = {
    "nodes": [
        {"id": "trigger", "type": "trigger", "label": "Inicio", "config": {}},
        {"id": "human_a", "type": "human_input", "label": "Coleta", "config": {}},
        {"id": "agent_b", "type": "specialist_agent", "label": "Analise", "config": {}},
    ],
    "edges": [
        {"id": "e1", "source": "trigger", "target": "human_a", "condition": None},
        {"id": "e2", "source": "human_a", "target": "agent_b", "condition": None},
    ],
}


async def _create_workflow_definition(tenant_id) -> PlaybookDefinition:
    """Cria uma PlaybookDefinition minima para amarrar dossies em testes."""
    async with AsyncSessionLocal() as db:
        wf = PlaybookDefinition(
            tenant_id=tenant_id,
            name=f"test.workflow.{uuid4().hex[:6]}",
            version=1,
            category="credit",
            graph=_DEMO_GRAPH,
        )
        db.add(wf)
        await db.commit()
        await db.refresh(wf)
    return wf


async def _create_dossier(
    tenant_id,
    *,
    workflow_definition_id,
    target_name: str | None = "TEST DOSSIE",
    status: DossierStatus = DossierStatus.DRAFT,
) -> CreditDossier:
    """Cria um CreditDossier minimo (sem disparar workflow engine)."""
    async with AsyncSessionLocal() as db:
        d = CreditDossier(
            tenant_id=tenant_id,
            target_name=target_name,
            workflow_definition_id=workflow_definition_id,
            status=status,
        )
        db.add(d)
        await db.commit()
        await db.refresh(d)
    return d


@pytest.fixture
async def user_b_admin(tenant_b: Tenant) -> User:
    """User no tenant B com ADMIN em todos os modulos."""
    email = f"user-b-{uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as db:
        u = User(
            tenant_id=tenant_b.id,
            email=email,
            name="User B",
            password_hash=hash_password("test-password"),
            ativo=True,
        )
        db.add(u)
        await db.flush()
        for m in Module:
            db.add(UserModulePermission(user_id=u.id, module=m, permission=Permission.ADMIN))
        await db.commit()
        await db.refresh(u)
    return u


@pytest.fixture
async def user_a_alt(tenant_a: Tenant) -> User:
    """Segundo user no tenant A com WRITE em CREDITO. Usado em testes de
    autoria de notas."""
    email = f"user-a-alt-{uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as db:
        u = User(
            tenant_id=tenant_a.id,
            email=email,
            name="User A Alt",
            password_hash=hash_password("test-password"),
            ativo=True,
        )
        db.add(u)
        await db.flush()
        for m in Module:
            # Apenas WRITE — nao admin. Permite criar/editar proprias mas
            # nao deletar de outros.
            db.add(UserModulePermission(user_id=u.id, module=m, permission=Permission.WRITE))
        await db.commit()
        await db.refresh(u)
    return u


@pytest.fixture(autouse=True)
def _clean_storage_root():
    """Limpa o diretorio de storage entre tests para nao acumular blobs."""
    root = Path(get_settings().DOSSIER_STORAGE_ROOT).resolve()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    yield
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


# ─── Attachments ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_attachment_upload_and_list(
    client: AsyncClient, user_in_tenant_a: User
):
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    payload = b"fake DRE content " * 50  # ~850 bytes
    r = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/attachments",
        headers=_auth(token),
        files={"file": ("DRE_2024.pdf", io.BytesIO(payload), "application/pdf")},
        data={"node_id": "human_a", "description": "DRE 2024 do cedente"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filename"] == "DRE_2024.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["size_bytes"] == len(payload)
    assert body["node_id"] == "human_a"
    assert body["description"] == "DRE 2024 do cedente"
    assert body["uploaded_by"] == str(user_in_tenant_a.id)

    # Confirma blob no FS.
    storage_root = Path(get_settings().DOSSIER_STORAGE_ROOT).resolve()
    sha = body["sha256"]
    blob_path = (
        storage_root
        / str(user_in_tenant_a.tenant_id)
        / str(dossier.id)
        / sha[:2]
        / sha
    )
    assert blob_path.exists(), f"Blob nao foi salvo em {blob_path}"

    # List.
    r2 = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/attachments",
        headers=_auth(token),
    )
    assert r2.status_code == 200
    rows = r2.json()
    assert len(rows) == 1
    assert rows[0]["id"] == body["id"]

    # Filter by node_id.
    r3 = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/attachments?node_id=human_a",
        headers=_auth(token),
    )
    assert r3.status_code == 200
    assert len(r3.json()) == 1

    r4 = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/attachments?node_id=outro_node",
        headers=_auth(token),
    )
    assert r4.status_code == 200
    assert r4.json() == []


@pytest.mark.asyncio
async def test_attachment_download_streams_blob(
    client: AsyncClient, user_in_tenant_a: User
):
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )
    payload = b"sentinel-content-12345"

    r = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/attachments",
        headers=_auth(token),
        files={"file": ("note.txt", io.BytesIO(payload), "text/plain")},
    )
    assert r.status_code == 201
    att_id = r.json()["id"]

    r2 = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/attachments/{att_id}/download",
        headers=_auth(token),
    )
    assert r2.status_code == 200
    assert r2.content == payload
    assert "attachment" in r2.headers.get("content-disposition", "").lower()


@pytest.mark.asyncio
async def test_attachment_size_limit_rejected(
    client: AsyncClient, user_in_tenant_a: User
):
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    # Default max e 25 MB. Cria payload acima do limite.
    max_bytes = get_settings().DOSSIER_ATTACHMENT_MAX_BYTES
    big = b"x" * (max_bytes + 1)
    r = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/attachments",
        headers=_auth(token),
        files={"file": ("huge.bin", io.BytesIO(big), "application/octet-stream")},
    )
    assert r.status_code == 413, r.text


@pytest.mark.asyncio
async def test_attachment_sha256_dedup(client: AsyncClient, user_in_tenant_a: User):
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )
    payload = b"identical-content-for-dedup-test"

    # Upload 1
    r1 = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/attachments",
        headers=_auth(token),
        files={"file": ("dre_jan.pdf", io.BytesIO(payload), "application/pdf")},
    )
    # Upload 2 — mesmo conteudo, filename diferente
    r2 = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/attachments",
        headers=_auth(token),
        files={"file": ("dre_fev.pdf", io.BytesIO(payload), "application/pdf")},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    sha1 = r1.json()["sha256"]
    sha2 = r2.json()["sha256"]
    assert sha1 == sha2, "Mesmo conteudo deve gerar mesmo hash"
    assert r1.json()["id"] != r2.json()["id"], "Devem ser linhas distintas"

    # 1 blob no FS.
    storage_root = Path(get_settings().DOSSIER_STORAGE_ROOT).resolve()
    blob_path = (
        storage_root
        / str(user_in_tenant_a.tenant_id)
        / str(dossier.id)
        / sha1[:2]
        / sha1
    )
    assert blob_path.exists()

    # Lista retorna 2 attachments.
    rl = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/attachments",
        headers=_auth(token),
    )
    assert rl.status_code == 200
    assert len(rl.json()) == 2


@pytest.mark.asyncio
async def test_attachment_tenant_isolation(
    client: AsyncClient,
    user_in_tenant_a: User,
    user_b_admin: User,
):
    """Tenant B nao pode listar nem baixar attachment de dossier do tenant A."""
    token_a = await _login(client, user_in_tenant_a.email)
    token_b = await _login(client, user_b_admin.email)

    wf_a = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier_a = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf_a.id
    )
    r = await client.post(
        f"{API_BASE}/dossies/{dossier_a.id}/attachments",
        headers=_auth(token_a),
        files={"file": ("secret.pdf", io.BytesIO(b"top-secret"), "application/pdf")},
    )
    assert r.status_code == 201
    att_id = r.json()["id"]

    # Tenant B tenta listar — backend nao acha o dossier no escopo de B, devolve 404.
    rb = await client.get(
        f"{API_BASE}/dossies/{dossier_a.id}/attachments",
        headers=_auth(token_b),
    )
    assert rb.status_code in (403, 404), rb.text

    # Tenant B tenta baixar.
    rb2 = await client.get(
        f"{API_BASE}/dossies/{dossier_a.id}/attachments/{att_id}/download",
        headers=_auth(token_b),
    )
    assert rb2.status_code in (403, 404), rb2.text

    # Tenant B tenta deletar.
    rb3 = await client.delete(
        f"{API_BASE}/dossies/{dossier_a.id}/attachments/{att_id}",
        headers=_auth(token_b),
    )
    assert rb3.status_code in (403, 404), rb3.text


@pytest.mark.asyncio
async def test_attachment_delete_removes_row(
    client: AsyncClient, user_in_tenant_a: User
):
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    r = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/attachments",
        headers=_auth(token),
        files={"file": ("a.pdf", io.BytesIO(b"hello"), "application/pdf")},
    )
    att_id = r.json()["id"]

    rd = await client.delete(
        f"{API_BASE}/dossies/{dossier.id}/attachments/{att_id}",
        headers=_auth(token),
    )
    assert rd.status_code == 204

    rl = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/attachments",
        headers=_auth(token),
    )
    assert rl.status_code == 200
    assert rl.json() == []


# ─── Notes ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_note_create_and_list(client: AsyncClient, user_in_tenant_a: User):
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    r = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/notes",
        headers=_auth(token),
        json={
            "node_id": "human_a",
            "body_md": "**Conferir** concentracao bancaria",
            "pinned": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["node_id"] == "human_a"
    assert body["pinned"] is True
    assert body["author_id"] == str(user_in_tenant_a.id)

    # List.
    rl = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/notes",
        headers=_auth(token),
    )
    assert rl.status_code == 200
    rows = rl.json()
    assert len(rows) == 1
    assert rows[0]["id"] == body["id"]

    # Filter by node_id.
    rf = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/notes?node_id=human_a",
        headers=_auth(token),
    )
    assert rf.status_code == 200
    assert len(rf.json()) == 1


@pytest.mark.asyncio
async def test_note_update_author_only(
    client: AsyncClient,
    user_in_tenant_a: User,
    user_a_alt: User,
):
    """user_a_alt (WRITE) tenta editar nota criada por user_in_tenant_a (ADMIN). Bloqueado."""
    token_owner = await _login(client, user_in_tenant_a.email)
    token_other = await _login(client, user_a_alt.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    r = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/notes",
        headers=_auth(token_owner),
        json={"node_id": "human_a", "body_md": "Nota original"},
    )
    note_id = r.json()["id"]

    # Outro user (mesmo tenant) tenta editar.
    re = await client.patch(
        f"{API_BASE}/dossies/{dossier.id}/notes/{note_id}",
        headers=_auth(token_other),
        json={"body_md": "Editado por intruder"},
    )
    assert re.status_code == 403

    # Autor edita — OK.
    re2 = await client.patch(
        f"{API_BASE}/dossies/{dossier.id}/notes/{note_id}",
        headers=_auth(token_owner),
        json={"body_md": "Editado pelo autor"},
    )
    assert re2.status_code == 200
    assert re2.json()["body_md"] == "Editado pelo autor"


@pytest.mark.asyncio
async def test_note_tenant_isolation(
    client: AsyncClient,
    user_in_tenant_a: User,
    user_b_admin: User,
):
    token_a = await _login(client, user_in_tenant_a.email)
    token_b = await _login(client, user_b_admin.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    r = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/notes",
        headers=_auth(token_a),
        json={"node_id": "human_a", "body_md": "Visivel apenas pra A"},
    )
    note_id = r.json()["id"]

    # B tenta listar.
    rl = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/notes",
        headers=_auth(token_b),
    )
    assert rl.status_code in (403, 404)

    # B tenta deletar.
    rd = await client.delete(
        f"{API_BASE}/dossies/{dossier.id}/notes/{note_id}",
        headers=_auth(token_b),
    )
    assert rd.status_code in (403, 404)


@pytest.mark.asyncio
async def test_note_body_length_validation(
    client: AsyncClient, user_in_tenant_a: User
):
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    # Body vazio rejeitado pelo schema (min_length=1).
    r0 = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/notes",
        headers=_auth(token),
        json={"node_id": "human_a", "body_md": ""},
    )
    assert r0.status_code == 422

    # Body acima do limite (10000 chars) tambem rejeitado.
    big = "a" * 10001
    r1 = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/notes",
        headers=_auth(token),
        json={"node_id": "human_a", "body_md": big},
    )
    assert r1.status_code == 422


# ─── Links ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_link_create_and_list(client: AsyncClient, user_in_tenant_a: User):
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    r = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/links",
        headers=_auth(token),
        json={
            "node_id": "human_a",
            "url": "https://servicos.receita.fazenda.gov.br/abc",
            "title": "CNPJ na Receita",
            "description": "Cadastro publico do cedente",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["url"].startswith("https://servicos.receita.fazenda.gov.br/")
    assert body["title"] == "CNPJ na Receita"
    assert body["added_by"] == str(user_in_tenant_a.id)

    rl = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/links",
        headers=_auth(token),
    )
    assert rl.status_code == 200
    assert len(rl.json()) == 1


@pytest.mark.asyncio
async def test_link_url_validation(client: AsyncClient, user_in_tenant_a: User):
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    # URL invalida rejeitada pelo HttpUrl.
    r = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/links",
        headers=_auth(token),
        json={"url": "isto-nao-e-uma-url"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_link_tenant_isolation(
    client: AsyncClient,
    user_in_tenant_a: User,
    user_b_admin: User,
):
    token_a = await _login(client, user_in_tenant_a.email)
    token_b = await _login(client, user_b_admin.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    r = await client.post(
        f"{API_BASE}/dossies/{dossier.id}/links",
        headers=_auth(token_a),
        json={"url": "https://example.com/a"},
    )
    link_id = r.json()["id"]

    rl = await client.get(
        f"{API_BASE}/dossies/{dossier.id}/links",
        headers=_auth(token_b),
    )
    assert rl.status_code in (403, 404)

    rd = await client.delete(
        f"{API_BASE}/dossies/{dossier.id}/links/{link_id}",
        headers=_auth(token_b),
    )
    assert rd.status_code in (403, 404)


# ─── Listing — DossierListItem.progress ──────────────────────────────────────


@pytest.mark.asyncio
async def test_dossier_list_returns_progress_fields(
    client: AsyncClient, user_in_tenant_a: User
):
    """GET /dossies retorna completed_steps/total_steps/next_action_*."""
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    r = await client.get(f"{API_BASE}/dossies", headers=_auth(token))
    assert r.status_code == 200
    rows = r.json()
    found = next((row for row in rows if row["id"] == str(dossier.id)), None)
    assert found is not None, "Dossier criado deve aparecer na listagem"
    # Sem PlaybookRun amarrado: 0 completed, total_steps vem do graph (3 nodes).
    assert found["completed_steps"] == 0
    assert found["total_steps"] == 3
    # Sem run e status DRAFT — nao e human_input nem agent_running.
    assert found["next_action_kind"] in {"blocked"}
    assert isinstance(found["next_action_label"], str)


@pytest.mark.asyncio
async def test_dossier_list_finalized_returns_finalized_kind(
    client: AsyncClient, user_in_tenant_a: User
):
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id,
        workflow_definition_id=wf.id,
        status=DossierStatus.FINALIZED,
    )

    r = await client.get(f"{API_BASE}/dossies", headers=_auth(token))
    found = next(row for row in r.json() if row["id"] == str(dossier.id))
    assert found["next_action_kind"] == "finalized"
    assert found["next_action_label"] == "Finalizado"
    assert found["next_node_id"] is None


# ─── Cleanup helpers (exposed for explicit assertions) ──────────────────────


async def _count_in_db(model_cls, tenant_id) -> int:
    from sqlalchemy import func, select

    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(func.count(model_cls.id)).where(model_cls.tenant_id == tenant_id)
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_attachments_notes_links_share_tenant_scope(
    client: AsyncClient, user_in_tenant_a: User
):
    """Sanity: depois das mutacoes, contagens batem por tenant."""
    token = await _login(client, user_in_tenant_a.email)
    wf = await _create_workflow_definition(user_in_tenant_a.tenant_id)
    dossier = await _create_dossier(
        user_in_tenant_a.tenant_id, workflow_definition_id=wf.id
    )

    await client.post(
        f"{API_BASE}/dossies/{dossier.id}/attachments",
        headers=_auth(token),
        files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")},
    )
    await client.post(
        f"{API_BASE}/dossies/{dossier.id}/notes",
        headers=_auth(token),
        json={"node_id": "human_a", "body_md": "n"},
    )
    await client.post(
        f"{API_BASE}/dossies/{dossier.id}/links",
        headers=_auth(token),
        json={"url": "https://example.com"},
    )

    assert await _count_in_db(DossierAttachment, user_in_tenant_a.tenant_id) == 1
    assert await _count_in_db(DossierStepNote, user_in_tenant_a.tenant_id) == 1
    assert await _count_in_db(DossierStepLink, user_in_tenant_a.tenant_id) == 1
