"""Copiloto (Strata AI) — guard 403/402, isolamento de tenant e filtro surface.

CLAUDE.md §10.4: endpoint novo tem teste de 403; service novo que toca tabela
multi-tenant tem teste de isolamento (tenant A nao ve dado de tenant B).
Nenhum teste aqui chama LLM — os cenarios param antes da credencial.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import AICapability
from app.core.security import hash_password
from app.core.tenant_middleware import RequestPrincipal
from app.shared.ai.models.conversation import AIConversation
from app.shared.ai.models.permission import UserAIPermission
from app.shared.ai.models.subscription import TenantAISubscription
from app.shared.ai.services.copiloto import stream_copiloto_response
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User


async def _login(client: AsyncClient, email: str, password: str = "test-password") -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _enable_ai_subscription(tenant_id) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            TenantAISubscription(
                tenant_id=tenant_id, enabled=True, monthly_credit_quota=1000
            )
        )
        await db.commit()


async def _grant_ai_permission(user_id, capability: AICapability) -> None:
    async with AsyncSessionLocal() as db:
        db.add(UserAIPermission(user_id=user_id, permission=capability))
        await db.commit()


# ─── Guard: 402 (sem subscription) e 403 (sem permissao) ─────────────────


@pytest.mark.asyncio
async def test_copiloto_chat_402_sem_subscription(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    """Tenant sem tenant_ai_subscription -> 402 no guard require_ai."""
    token = await _login(client, user_in_tenant_a.email)
    r = await client.post(
        "/api/v1/copiloto/chat",
        json={"message": "oi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 402, r.text


@pytest.mark.asyncio
async def test_copiloto_chat_403_sem_permissao_ai(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    """Tenant assinante mas user sem user_ai_permission -> 403."""
    await _enable_ai_subscription(user_in_tenant_a.tenant_id)
    token = await _login(client, user_in_tenant_a.email)
    r = await client.post(
        "/api/v1/copiloto/chat",
        json={"message": "oi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


# ─── Isolamento: conversa de tenant B nao abre para user de tenant A ─────


@pytest.mark.asyncio
async def test_copiloto_stream_nao_abre_conversa_de_outro_tenant(
    user_in_tenant_a: User, tenant_b: Tenant
) -> None:
    """stream_copiloto_response com conversation_id alheio -> frame de erro
    not_found, antes de qualquer chamada externa."""
    async with AsyncSessionLocal() as db:
        user_b = User(
            tenant_id=tenant_b.id,
            email=f"user-b-{uuid4().hex[:8]}@example.com",
            name="User B",
            password_hash=hash_password("test-password"),
            ativo=True,
        )
        db.add(user_b)
        await db.flush()
        conv_b = AIConversation(
            tenant_id=tenant_b.id, user_id=user_b.id, surface="copiloto"
        )
        db.add(conv_b)
        await db.commit()
        conv_b_id = conv_b.id

    principal_a = RequestPrincipal(
        user_id=user_in_tenant_a.id,
        tenant_id=user_in_tenant_a.tenant_id,
        email=user_in_tenant_a.email,
    )
    async with AsyncSessionLocal() as db:
        frames = [
            f
            async for f in stream_copiloto_response(
                db=db,
                principal=principal_a,
                user_message="mostra essa conversa",
                conversation_id=conv_b_id,
            )
        ]

    assert frames, "stream nao emitiu nenhum frame"
    error_frames = [f for f in frames if f["type"] == "error"]
    assert error_frames and error_frames[0]["status"] == "not_found"
    # Nada da conversa alheia vazou em nenhum frame.
    assert all(str(conv_b_id) != f.get("conversation_id") for f in frames)


# ─── Surface: rails nao misturam historico (spec §6.5) ───────────────────


@pytest.mark.asyncio
async def test_lista_conversas_filtra_por_surface(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    await _enable_ai_subscription(user_in_tenant_a.tenant_id)
    await _grant_ai_permission(user_in_tenant_a.id, AICapability.READ)

    async with AsyncSessionLocal() as db:
        db.add(
            AIConversation(
                tenant_id=user_in_tenant_a.tenant_id,
                user_id=user_in_tenant_a.id,
                surface="aipanel",
                title="conversa do painel",
            )
        )
        copiloto_conv = AIConversation(
            tenant_id=user_in_tenant_a.tenant_id,
            user_id=user_in_tenant_a.id,
            surface="copiloto",
            title="conversa do copiloto",
        )
        db.add(copiloto_conv)
        await db.commit()
        copiloto_id = str(copiloto_conv.id)

    token = await _login(client, user_in_tenant_a.email)
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/v1/ai/conversations?surface=copiloto", headers=headers)
    assert r.status_code == 200, r.text
    ids = [c["id"] for c in r.json()]
    assert ids == [copiloto_id]

    # Sem filtro continua retornando tudo (backward compatible).
    r_all = await client.get("/api/v1/ai/conversations", headers=headers)
    assert r_all.status_code == 200
    assert len(r_all.json()) == 2
