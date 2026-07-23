"""Camada MCP — primitivo horizontal da camada agentica (spec copiloto-mcp §4).

Servidores MCP externos sao provedores de capability para agentes, irmaos
de `tools/`, `agents/`, `workflows/` e `memory/`. O BACKEND e o cliente
MCP (mesmo papel do Claude Code no dev): fala Streamable HTTP com os
headers de auth do vendor, lista tools, executa `tools/call` — tudo
dentro do nosso `_run_tool_loop`, nada exposto publicamente
(outbound-only, principio 10 da spec).

Blocos:
    models.py    McpServer + McpServerActive (DB-first, versionado)
    registry.py  McpRegistry — resolucao por escopo (RBAC por module tag)
    resolver.py  credencial (decrypt do store existente) -> headers
    client.py    cliente MCP (SDK oficial `mcp`): tools/list cacheado +
                 pool de sessoes por turno
    tools.py     wrapper: tool de MCP -> objeto AgentTool-compativel
    public.py    contrato do primitivo
"""
