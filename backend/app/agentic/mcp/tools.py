"""Wrapper: tool de MCP -> objeto AgentTool-compativel (spec §4.3).

O `_run_tool_loop` (e o loop do Copiloto) so precisam de `name`,
`description`, `input_schema`, `handler` e `to_api_definition()` — este
wrapper implementa exatamente essa interface, sem forcar a semantica de
`Module`/`min_permission` da tool nativa (a filtragem RBAC de MCP ja
aconteceu no `McpRegistry`, no nivel do servidor).

Nome apresentado ao modelo: `mcp__<server>__<tool>` — prefixo evita
colisao com nativas e identifica o executor no dispatch (o vocabulario
white-label da UI e responsabilidade dos frames `tool_status`, nunca do
nome tecnico).

Guard-rails aplicados AQUI (o resultado passa pelas nossas maos —
vantagem do cliente proprio, spec §6.4):
    - cap de chamadas por turno por servidor (`max_calls_per_turn`);
    - truncamento de `tool_result` acima de `tool_result_max_chars`,
      com marcador explicito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from app.agentic.mcp.client import (
    McpSessionPool,
    McpToolCallError,
    McpToolDef,
)
from app.agentic.mcp.resolver import McpConnection

if TYPE_CHECKING:
    from app.agentic.mcp.models import McpServer

MCP_TOOL_PREFIX = "mcp__"


class CapabilityTool(Protocol):
    """Interface minima que o tool loop consome (nativa OU MCP)."""

    name: str
    description: str
    input_schema: dict[str, Any]

    def to_api_definition(self) -> dict[str, Any]: ...

    # Nativas: handler(scope, args). MCP: handler(args) via execute().


@dataclass
class McpTurnBudget:
    """Contador de chamadas externas do turno, por servidor (spec §6.4)."""

    max_calls_per_turn: int
    calls_made: int = 0

    @property
    def exhausted(self) -> bool:
        return self.calls_made >= self.max_calls_per_turn


@dataclass(frozen=True, slots=True)
class McpWrappedTool:
    """Uma tool de MCP pronta para entrar no cardapio do modelo."""

    name: str                    # "mcp__bigdatacorp__companies_basic_data_tool"
    description: str
    input_schema: dict[str, Any]
    server_name: str
    tool_name: str               # nome original no servidor
    conn: McpConnection
    pool: McpSessionPool
    budget: McpTurnBudget
    tool_result_max_chars: int = 20000
    cost_hint: str = "expensive"

    def to_api_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    async def execute(self, args: dict[str, Any]) -> str:
        """Executa a chamada com caps + truncamento. Erros viram
        McpToolCallError (o caller transforma em tool_result is_error)."""
        if self.budget.exhausted:
            raise McpToolCallError(
                "Limite de consultas externas deste turno atingido "
                f"({self.budget.max_calls_per_turn}). Responda com o que ja "
                "tem ou oriente o usuario a refinar a pergunta."
            )
        self.budget.calls_made += 1
        result = await self.pool.call_tool(self.conn, self.tool_name, args)
        if len(result) > self.tool_result_max_chars:
            kept = self.tool_result_max_chars
            result = (
                result[:kept]
                + f"\n\n[resultado truncado — {kept} de {len(result)} caracteres]"
            )
        return result


@dataclass
class McpCapabilities:
    """Cardapio MCP resolvido de um turno + o pool a fechar no finally."""

    tools: list[McpWrappedTool] = field(default_factory=list)
    pool: McpSessionPool = field(default_factory=McpSessionPool)
    # Servidores que falharam na montagem (nome -> erro) — para aviso honesto.
    unavailable: dict[str, str] = field(default_factory=dict)

    async def aclose(self) -> None:
        await self.pool.aclose()


def wrap_server_tools(
    *,
    server: McpServer,
    conn: McpConnection,
    tool_defs: list[McpToolDef],
    toolset_allowlist: list[str] | None,
    pool: McpSessionPool,
) -> list[McpWrappedTool]:
    """Filtra pela allowlist (servidor ∩ toolset do agente) e embrulha.

    `toolset_allowlist` vem do `mcp_toolsets` do agente (None = usa so a
    allowlist do servidor). Um budget UNICO por servidor e compartilhado
    entre as tools embrulhadas (cap e por servidor, nao por tool).
    """
    server_allow = set(server.allowed_tools) if server.allowed_tools else None
    agent_allow = set(toolset_allowlist) if toolset_allowlist else None

    budget = McpTurnBudget(max_calls_per_turn=server.max_calls_per_turn)
    wrapped: list[McpWrappedTool] = []
    for tool in tool_defs:
        if server_allow is not None and tool.name not in server_allow:
            continue
        if agent_allow is not None and tool.name not in agent_allow:
            continue
        wrapped.append(
            McpWrappedTool(
                name=f"{MCP_TOOL_PREFIX}{server.name}__{tool.name}",
                description=tool.description,
                input_schema=tool.input_schema,
                server_name=server.name,
                tool_name=tool.name,
                conn=conn,
                pool=pool,
                budget=budget,
                tool_result_max_chars=server.tool_result_max_chars,
                cost_hint=server.cost_hint,
            )
        )
    return wrapped
