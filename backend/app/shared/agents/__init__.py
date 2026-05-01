"""Specialist Agents — IA experts plugged into the workflow engine.

Each Specialist Agent is a Claude agent (via `claude-agent-sdk`) with:
- A versioned system prompt loaded from `ai_prompt` table
- Custom tools (MCP server in-process) tenant-scoped
- A Pydantic output schema that the orchestrator validates

Used by the `specialist_agent` workflow node — see
`app/shared/workflow/nodes/specialist_agent.py`.

Coexistence with the existing LLM adapter:
- `app/modules/integracoes/adapters/llm/anthropic/` continues to handle
  simple chat (used by the AI panel for the BI module).
- This package adds a parallel runtime for agents with tools — different
  use case, different SDK (`claude-agent-sdk` vs `anthropic`).
"""
