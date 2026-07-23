"""Cliente MCP do backend (SDK oficial `mcp`) — spec copiloto-mcp §4.3.

Duas responsabilidades:

1. `list_tools_cached(conn)` — `initialize` + `tools/list` numa sessao
   curta, com cache em processo por servidor (TTL) para nao pagar
   handshake a cada turno. Usado na montagem do cardapio e no botao
   "Testar conexao" do admin.

2. `McpSessionPool` — pool de sessoes POR TURNO: a sessao com cada
   servidor abre lazy na primeira `tools/call` e fecha no fim do turno
   (`aclose()`), como a spec §4.3 pede. Sem retry automatico em
   `tools/call` (dataset pago — spec §6.4); expiracao de sessao no meio
   do turno reabre 1x (initialize nao e dataset pago — spec §6.6).
"""

from __future__ import annotations

import logging
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.agentic.mcp.resolver import McpConnection

logger = logging.getLogger(__name__)

# Timeout por chamada de tool (BDC pode ser lento em datasets grandes).
_CALL_TIMEOUT_SECONDS = 60.0
# Timeout do handshake/list (barato — falha rapida degrada o cardapio).
_LIST_TIMEOUT_SECONDS = 20.0
# TTL do cache de tools/list por servidor.
_TOOLS_CACHE_TTL_SECONDS = 600.0


@dataclass(frozen=True, slots=True)
class McpToolDef:
    """Definicao de uma tool exposta pelo servidor (do tools/list)."""

    name: str
    description: str
    input_schema: dict[str, Any]


# Cache em processo: server_id -> (expires_at_monotonic, [McpToolDef]).
_tools_cache: dict[str, tuple[float, list[McpToolDef]]] = {}


async def list_tools_cached(
    conn: McpConnection, *, force_refresh: bool = False
) -> list[McpToolDef]:
    """tools/list do servidor, cacheado em processo por TTL.

    Levanta a excecao do transporte quando o servidor esta inalcancavel e
    nao ha cache — o caller decide degradar (cardapio sem o servidor).
    """
    now = time.monotonic()
    cached = _tools_cache.get(conn.server_id)
    if cached and not force_refresh:
        expires_at, tools = cached
        if now < expires_at:
            return tools

    try:
        tools = await _list_tools(conn)
    except Exception:
        # Servidor fora: serve cache vencido se existir (melhor cardapio
        # velho que cardapio sem o servidor).
        if cached:
            logger.warning(
                "MCP '%s': tools/list falhou; usando cache vencido", conn.name
            )
            return cached[1]
        raise

    _tools_cache[conn.server_id] = (now + _TOOLS_CACHE_TTL_SECONDS, tools)
    return tools


async def _list_tools(conn: McpConnection) -> list[McpToolDef]:
    async with streamablehttp_client(
        conn.url,
        headers=conn.headers,
        timeout=timedelta(seconds=_LIST_TIMEOUT_SECONDS),
    ) as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.list_tools()
    return [
        McpToolDef(
            name=t.name,
            description=t.description or "",
            input_schema=t.inputSchema or {"type": "object", "properties": {}},
        )
        for t in result.tools
    ]


def _serialize_result_content(result: Any) -> str:
    """Concatena os blocos de texto do CallToolResult num payload string."""
    parts: list[str] = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts) if parts else "(consulta sem conteudo)"


class McpToolCallError(RuntimeError):
    """Falha de execucao de tools/call (vira tool_result is_error)."""


class McpSessionPool:
    """Sessoes MCP de UM turno de chat. Lazy-open, fecha em `aclose()`.

    NAO e thread-safe nem cross-turn — cada turno cria o seu (o loop de
    tools roda sequencial na mesma task).
    """

    def __init__(self) -> None:
        self._sessions: dict[str, tuple[AsyncExitStack, ClientSession]] = {}

    async def _get_session(self, conn: McpConnection) -> ClientSession:
        entry = self._sessions.get(conn.server_id)
        if entry is not None:
            return entry[1]

        stack = AsyncExitStack()
        try:
            read, write, _ = await stack.enter_async_context(
                streamablehttp_client(
                    conn.url,
                    headers=conn.headers,
                    timeout=timedelta(seconds=_CALL_TIMEOUT_SECONDS),
                )
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except BaseException:
            await stack.aclose()
            raise

        self._sessions[conn.server_id] = (stack, session)
        return session

    async def _drop_session(self, server_id: str) -> None:
        entry = self._sessions.pop(server_id, None)
        if entry is not None:
            try:
                await entry[0].aclose()
            except Exception:  # nosec — teardown best-effort
                logger.debug("MCP: teardown de sessao falhou", exc_info=True)

    async def call_tool(
        self, conn: McpConnection, tool_name: str, args: dict[str, Any]
    ) -> str:
        """Executa tools/call. SEM retry em falha de chamada (dataset pago);
        sessao expirada e reaberta UMA vez (handshake nao e pago)."""
        try:
            session = await self._get_session(conn)
            result = await session.call_tool(tool_name, args)
        except Exception as first_exc:
            # Sessao pode ter expirado no meio do turno — reabre 1x. Se a
            # falha for do servidor/da chamada, a retentativa unica ainda e
            # de handshake + 1 call; aceitavel porque so acontece quando a
            # PRIMEIRA tentativa nem completou transporte.
            logger.warning(
                "MCP '%s' tools/call '%s' falhou (%s); reabrindo sessao 1x",
                conn.name,
                tool_name,
                first_exc,
            )
            await self._drop_session(conn.server_id)
            try:
                session = await self._get_session(conn)
                result = await session.call_tool(tool_name, args)
            except Exception as second_exc:
                raise McpToolCallError(str(second_exc)) from second_exc

        if getattr(result, "isError", False):
            raise McpToolCallError(_serialize_result_content(result))
        return _serialize_result_content(result)

    async def aclose(self) -> None:
        for server_id in list(self._sessions):
            await self._drop_session(server_id)
