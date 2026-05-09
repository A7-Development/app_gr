"""Tools available to specialist agents.

Each module exports a factory `make_<group>_tools(tenant_id, dossier_id, db)`
that returns a list of `@tool`-decorated callables ready to be wrapped in
an in-process MCP server.

The factories close over the tenant scope so the tool implementations don't
need to ask the agent for the tenant_id (which would be a security risk —
the agent could lie or be tricked into reading another tenant's data).
"""
