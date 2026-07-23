"""Contrato publico do primitivo MCP (spec copiloto-mcp §4).

Consumidores (runtime do Copiloto, admin API) importam DAQUI — internals
(client/resolver) podem evoluir sem quebrar quem consome.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.agentic.mcp.client import McpToolCallError, list_tools_cached
from app.agentic.mcp.models import McpMode, McpServer, McpServerActive, McpTransport
from app.agentic.mcp.registry import McpRegistry, McpServerNotFoundError
from app.agentic.mcp.resolver import McpCredentialError, resolve_connection
from app.agentic.mcp.tools import (
    MCP_TOOL_PREFIX,
    McpCapabilities,
    McpWrappedTool,
    wrap_server_tools,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.agentic._scope import ScopedContext

logger = logging.getLogger(__name__)

__all__ = [
    "MCP_TOOL_PREFIX",
    "McpCapabilities",
    "McpMode",
    "McpRegistry",
    "McpServer",
    "McpServerActive",
    "McpServerNotFoundError",
    "McpToolCallError",
    "McpTransport",
    "McpWrappedTool",
    "build_mcp_capabilities",
    "probe_server",
]


async def build_mcp_capabilities(
    db: AsyncSession,
    *,
    mcp_toolsets: tuple[dict, ...],
    scope: ScopedContext,
) -> McpCapabilities:
    """Monta o cardapio MCP de um turno a partir dos toolsets do agente.

    Nunca levanta por indisponibilidade de servidor: falha de resolucao/
    handshake degrada o cardapio (servidor entra em `unavailable` para o
    aviso honesto ao usuario — spec §4.3/§6.6). Erros de CONFIG
    (credencial invalida) tambem degradam, mas logam como error.
    """
    caps = McpCapabilities()

    for toolset in mcp_toolsets:
        name = toolset.get("mcp_server_name")
        if not name:
            continue
        try:
            server = await McpRegistry.resolve(db, name=name, scope=scope)
            if server is None:
                # Sem permissao no modulo do servidor — filtragem silenciosa.
                continue
            conn = await resolve_connection(db, server)
            tool_defs = await list_tools_cached(conn)
            caps.tools.extend(
                wrap_server_tools(
                    server=server,
                    conn=conn,
                    tool_defs=tool_defs,
                    toolset_allowlist=toolset.get("tools"),
                    pool=caps.pool,
                )
            )
        except (McpServerNotFoundError, McpCredentialError) as exc:
            logger.error("MCP '%s' fora do cardapio (config): %s", name, exc)
            caps.unavailable[name] = str(exc)
        except Exception as exc:  # transporte/handshake — degrada
            logger.warning("MCP '%s' fora do cardapio (indisponivel): %s", name, exc)
            caps.unavailable[name] = str(exc)

    return caps


async def probe_server(db: AsyncSession, server: McpServer) -> dict:
    """Probe barato (initialize + tools/list, sem custo de dataset) — usado
    pelo botao "Testar conexao" do admin (spec §7) e por smokes."""
    conn = await resolve_connection(db, server)
    tools = await list_tools_cached(conn, force_refresh=True)
    return {
        "ok": True,
        "tool_count": len(tools),
        "allowed_count": (
            len([t for t in tools if t.name in set(server.allowed_tools)])
            if server.allowed_tools
            else len(tools)
        ),
    }
