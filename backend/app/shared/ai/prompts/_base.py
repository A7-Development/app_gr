"""Base classes for the prompt library.

A `Prompt` is an instance built from a row in `ai_prompt`. The repository
(`repository.py`) reads the row, instantiates `Prompt`, and `Prompt.render`
produces the final messages list to send to the LLM adapter.

Refactor 2026-04-30: prompts moved out of code into DB. Previously this file
defined an abstract base class with ClassVars per subclass; now it defines a
single instantiable `Prompt` whose fields come from the DB.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class CacheStrategy(enum.StrEnum):
    """Onde colocar o cache breakpoint Anthropic."""

    NONE = "none"
    AFTER_SYSTEM = "after_system"


class MessageContent(BaseModel):
    """A single content block of a message (text-only for now)."""

    model_config = ConfigDict(extra="forbid")

    type: str = "text"
    text: str
    # When set on the last block of `system`, the LLM provider caches the
    # prefix up to and including this block. Anthropic-style; ignored by
    # providers without prompt caching.
    cache_control: dict | None = None


class Message(BaseModel):
    """An LLM chat message (system | user | assistant)."""

    model_config = ConfigDict(extra="forbid")

    role: str  # "system" | "user" | "assistant"
    content: list[MessageContent]


class Prompt(BaseModel):
    """A versioned prompt template, instantiated from a DB row.

    `system_text` is the obligatory system prompt. Two optional fields shape
    a multi-turn priming flow:

    - `user_context_template`: rendered with `context.format(**context)` and
      sent as a `user` message right after `system`. Use for "[Pagina atual]
      ..." style context blocks.

    - `assistant_prime`: a canned assistant reply ack-ing the context. Use to
      make the model commit to the priming before the real user turn arrives.

    `render(context)` returns the messages list. The orchestrator then appends
    history turns and the new user message AFTER the rendered prefix.
    """

    model_config = ConfigDict(extra="forbid")

    name: str                     # 'chat.fidc_geral'
    version: str                  # 'v1'
    system_text: str
    user_context_template: str | None = None
    assistant_prime: str | None = None
    model_default: str            # 'claude-opus-4-7'
    fallback_model: str | None = None
    temperature: float = 0.30
    max_tokens: int = 2048
    cache_strategy: CacheStrategy = CacheStrategy.AFTER_SYSTEM

    @property
    def full_id(self) -> str:
        """Identifier used in audit (`rule_or_model_version`)."""
        return f"{self.name}@{self.version}"

    def render(self, context: dict[str, Any] | None = None) -> list[Message]:
        """Build the messages prefix to feed the adapter.

        Returns:
            [system, optional user_context, optional assistant_prime].

        The orchestrator appends history + new user message AFTER this list.
        """
        ctx = context or {}
        out: list[Message] = []

        # System block (with cache breakpoint if requested).
        out.append(
            Message(
                role="system",
                content=[
                    MessageContent(
                        text=self.system_text,
                        cache_control=(
                            {"type": "ephemeral"}
                            if self.cache_strategy == CacheStrategy.AFTER_SYSTEM
                            else None
                        ),
                    )
                ],
            )
        )

        # Optional user context block.
        if self.user_context_template:
            try:
                rendered = self.user_context_template.format(**_safe_format_dict(ctx))
            except KeyError as e:
                raise ValueError(
                    f"Prompt {self.full_id}: variavel {e} ausente em context para "
                    "user_context_template."
                ) from e
            out.append(
                Message(
                    role="user",
                    content=[MessageContent(text=rendered)],
                )
            )

        # Optional assistant prime.
        if self.assistant_prime:
            out.append(
                Message(
                    role="assistant",
                    content=[MessageContent(text=self.assistant_prime)],
                )
            )

        return out


def _safe_format_dict(ctx: dict[str, Any]) -> dict[str, Any]:
    """Stringify None values so str.format produces stable output.

    Avoids `Pagina: None` when caller passes a key with `None`. Replaces with
    empty string; missing keys still raise KeyError (caught by `render`).
    """
    return {k: ("" if v is None else v) for k, v in ctx.items()}
