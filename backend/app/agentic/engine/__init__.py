"""Specialist Agents — IA experts plugged into the workflow engine.

Each Specialist Agent is a Claude agent (Anthropic Messages API via the
official `anthropic` SDK, with native tool use + prompt caching) with:
- A versioned system prompt loaded from `ai_prompt` table
- Custom tools (`AgentTool` instances, tenant-scoped via closure)
- A Pydantic output schema that the orchestrator validates

Used by the `specialist_agent` workflow node — see
`app/shared/workflow/nodes/specialist_agent.py`.

Coexistence with the existing LLM adapter:
- `app/modules/integracoes/adapters/llm/anthropic/` continues to handle
  simple chat (used by the AI panel for the BI module) via a custom HTTP
  client over httpx with SSE streaming.
- This package adds a parallel runtime for agents with tools — same SDK,
  different shape (multi-turn loop with `tool_use`/`tool_result` blocks
  + JSON output validation).
"""
