"""AI services — pure logic and persistence helpers used by the chat orchestrator.

Modules here are network-free (do NOT call LLM providers); they handle
redaction, auditability, metering, conversation history, and rate limiting.

The provider call lives in `app/modules/integracoes/adapters/llm/`.
The orchestration (compose context, call provider, persist) lives in
`services/chat.py`.
"""
