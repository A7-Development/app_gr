"""Prompt library — DB-backed (refactor 2026-04-30, CLAUDE.md sec 19.4).

Refactor history:
    Phase 1 (initial):     prompts in code (`<categoria>/<nome>_vN.py`) + in-memory registry.
    Phase 2 (current):     prompts in DB (`ai_prompt` table) + async repository.

The repository (`repository.py`) is the only entry point for services. It
reads from `ai_prompt` and `ai_prompt_active` to produce a fully-configured
`Prompt` instance. Editing prompts is now done via `/admin/ia/prompts` (no
deploy required).

Migration that seeded the 4 initial prompts:
    `7c2dffe119a4_ai_prompt_db_managed.py`
"""

from app.shared.ai.prompts import repository
from app.shared.ai.prompts._base import (
    CacheStrategy,
    Message,
    MessageContent,
    Prompt,
)
from app.shared.ai.prompts.repository import PromptNotFoundError

__all__ = [
    "CacheStrategy",
    "Message",
    "MessageContent",
    "Prompt",
    "PromptNotFoundError",
    "repository",
]
