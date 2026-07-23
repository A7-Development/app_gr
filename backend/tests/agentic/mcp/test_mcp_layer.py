"""Camada MCP — wrapper (allowlist/caps/truncamento), registry (RBAC) e resolver.

Unit com fakes (sem rede, sem custo); integracao de registry/resolver
contra o DB de teste. O transporte real e coberto pelo probe (spec §14.3b).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agentic._scope import ScopedContext
from app.agentic.mcp.client import McpSessionPool, McpToolCallError, McpToolDef
from app.agentic.mcp.models import McpServer, McpServerActive
from app.agentic.mcp.registry import McpRegistry
from app.agentic.mcp.resolver import McpConnection, McpCredentialError, resolve_connection
from app.agentic.mcp.tools import McpTurnBudget, McpWrappedTool, wrap_server_tools
from app.core.database import AsyncSessionLocal
from app.core.enums import Module, Permission
from app.shared.crypto import encrypt_envelope
from app.shared.data_providers.enums import DataProviderSlug
from app.shared.data_providers.models.credential import DataProviderCredential
from app.shared.data_providers.models.provider import DataProvider
from app.shared.identity.tenant import Tenant


async def _get_or_create_bdc_provider(db) -> DataProvider:
    from sqlalchemy import select

    existing = (
        await db.execute(
            select(DataProvider).where(
                DataProvider.slug == DataProviderSlug.BIGDATACORP
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    provider = DataProvider(
        slug=DataProviderSlug.BIGDATACORP,
        name="BigDataCorp (teste)",
        base_url="https://plataforma.bigdatacorp.com.br",
    )
    db.add(provider)
    await db.flush()
    return provider


class _FakePool(McpSessionPool):
    """Pool que devolve payload fixo sem tocar rede."""

    def __init__(self, payload: str = "resultado") -> None:
        super().__init__()
        self.calls: list[tuple[str, dict]] = []
        self.payload = payload

    async def call_tool(self, conn, tool_name, args):  # type: ignore[override]
        self.calls.append((tool_name, args))
        return self.payload


def _fake_server(**overrides) -> McpServer:
    defaults = {
        "id": uuid4(),
        "tenant_id": None,
        "name": "fake",
        "version": 1,
        "url": "http://localhost/mcp",
        "module": None,
        "allowed_tools": ["tool_a", "tool_b"],
        "max_calls_per_turn": 2,
        "tool_result_max_chars": 50,
        "cost_hint": "expensive",
    }
    defaults.update(overrides)
    return McpServer(**defaults)


_TOOL_DEFS = [
    McpToolDef(name="tool_a", description="a", input_schema={"type": "object"}),
    McpToolDef(name="tool_b", description="b", input_schema={"type": "object"}),
    McpToolDef(name="tool_c", description="c", input_schema={"type": "object"}),
]


def test_wrap_filtra_allowlist_do_servidor_e_prefixa_nome() -> None:
    server = _fake_server()
    wrapped = wrap_server_tools(
        server=server,
        conn=McpConnection(server_id="s", name="fake", url="u", headers={}),
        tool_defs=_TOOL_DEFS,
        toolset_allowlist=None,
        pool=_FakePool(),
    )
    # tool_c esta fora da allowlist do servidor.
    assert [t.name for t in wrapped] == ["mcp__fake__tool_a", "mcp__fake__tool_b"]


def test_wrap_intersecta_allowlist_do_toolset_do_agente() -> None:
    server = _fake_server()
    wrapped = wrap_server_tools(
        server=server,
        conn=McpConnection(server_id="s", name="fake", url="u", headers={}),
        tool_defs=_TOOL_DEFS,
        toolset_allowlist=["tool_b", "tool_c"],  # ∩ servidor = so tool_b
        pool=_FakePool(),
    )
    assert [t.name for t in wrapped] == ["mcp__fake__tool_b"]


@pytest.mark.asyncio
async def test_cap_de_chamadas_por_turno_e_por_servidor() -> None:
    server = _fake_server(max_calls_per_turn=2)
    pool = _FakePool()
    wrapped = wrap_server_tools(
        server=server,
        conn=McpConnection(server_id="s", name="fake", url="u", headers={}),
        tool_defs=_TOOL_DEFS,
        toolset_allowlist=None,
        pool=pool,
    )
    a, b = wrapped
    await a.execute({})
    await b.execute({})  # budget e compartilhado entre tools do servidor
    with pytest.raises(McpToolCallError, match="Limite de consultas externas"):
        await a.execute({})
    assert len(pool.calls) == 2  # a 3a nem tocou o pool


@pytest.mark.asyncio
async def test_truncamento_com_marcador_explicito() -> None:
    pool = _FakePool(payload="x" * 200)
    tool = McpWrappedTool(
        name="mcp__fake__tool_a",
        description="a",
        input_schema={"type": "object"},
        server_name="fake",
        tool_name="tool_a",
        conn=McpConnection(server_id="s", name="fake", url="u", headers={}),
        pool=pool,
        budget=McpTurnBudget(max_calls_per_turn=5),
        tool_result_max_chars=50,
    )
    result = await tool.execute({})
    assert result.startswith("x" * 50)
    assert "[resultado truncado — 50 de 200 caracteres]" in result


# ─── Registry (RBAC por module tag) + resolver — integracao DB ────────────


def _scope(db, tenant_id, permissions) -> ScopedContext:
    return ScopedContext(
        tenant_id=tenant_id,
        empresa_id=None,
        user_id=uuid4(),
        module=Module.CREDITO,
        permissions=permissions,
        db=db,
    )


@pytest.mark.asyncio
async def test_registry_filtra_por_permissao_de_modulo(tenant_a: Tenant) -> None:
    async with AsyncSessionLocal() as db:
        server = McpServer(
            tenant_id=None,
            name=f"srv-{uuid4().hex[:8]}",
            version=1,
            url="http://localhost/mcp",
            module="credito",
        )
        db.add(server)
        await db.flush()
        db.add(McpServerActive(tenant_id=None, name=server.name, server_id=server.id))
        await db.commit()
        name = server.name

    async with AsyncSessionLocal() as db:
        # Sem permissao de credito -> filtragem silenciosa (None).
        sem = await McpRegistry.resolve(
            db, name=name, scope=_scope(db, tenant_a.id, {})
        )
        assert sem is None
        # Com permissao -> resolve.
        com = await McpRegistry.resolve(
            db,
            name=name,
            scope=_scope(db, tenant_a.id, {Module.CREDITO: Permission.READ}),
        )
        assert com is not None and com.name == name


@pytest.mark.asyncio
async def test_resolver_mapeia_payload_para_headers(tenant_a: Tenant) -> None:
    async with AsyncSessionLocal() as db:
        provider = await _get_or_create_bdc_provider(db)
        cred = DataProviderCredential(
            provider_id=provider.id,
            alias=f"bdc-test-{uuid4().hex[:8]}",
            encrypted_payload=encrypt_envelope(
                {"access_token": "AT-123", "token_id": "TID-9"}
            ),
            active=True,
        )
        db.add(cred)
        await db.flush()
        server = McpServer(
            tenant_id=None,
            name=f"srv-{uuid4().hex[:8]}",
            version=1,
            url="http://localhost/mcp",
            credential_id=cred.id,
            auth_header_map={"access_token": "AccessToken", "token_id": "TokenId"},
        )
        db.add(server)
        await db.commit()

        conn = await resolve_connection(db, server)
        assert conn.headers == {"AccessToken": "AT-123", "TokenId": "TID-9"}


@pytest.mark.asyncio
async def test_resolver_recusa_credencial_com_campo_vazio(tenant_a: Tenant) -> None:
    """Guard: campo vazio na credencial e erro de CONFIG explicito — nunca
    header vazio silencioso (licao do incidente da chave Anthropic vazia)."""
    async with AsyncSessionLocal() as db:
        provider = await _get_or_create_bdc_provider(db)
        cred = DataProviderCredential(
            provider_id=provider.id,
            alias=f"bdc-vazio-{uuid4().hex[:8]}",
            encrypted_payload=encrypt_envelope({"access_token": "", "token_id": "x"}),
            active=True,
        )
        db.add(cred)
        await db.flush()
        server = McpServer(
            tenant_id=None,
            name=f"srv-{uuid4().hex[:8]}",
            version=1,
            url="http://localhost/mcp",
            credential_id=cred.id,
            auth_header_map={"access_token": "AccessToken", "token_id": "TokenId"},
        )
        db.add(server)
        await db.commit()

        with pytest.raises(McpCredentialError, match="vazio"):
            await resolve_connection(db, server)
