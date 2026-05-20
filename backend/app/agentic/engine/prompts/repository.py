"""Prompt repository — async DB-backed lookup, replaces the in-memory registry.

Resolves which version of a prompt to use right now (via `ai_prompt_active`)
and returns a fully-configured `Prompt` instance built from the `ai_prompt`
row.

This is the ONLY way services should obtain prompts:

    from app.shared.ai.prompts import repository
    prompt = await repository.resolve(db, name="chat.fidc_geral")
    messages = prompt.render(context={"page": "BI · Carteira"})
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.ai.models.prompt import AIPrompt
from app.shared.ai.models.prompt_active import AIPromptActive
from app.shared.ai.prompts._base import CacheStrategy, Prompt


class PromptNotFoundError(LookupError):
    """Raised when no `ai_prompt` row matches `name@version`."""


def _row_to_prompt(row: AIPrompt) -> Prompt:
    """Convert a SQLAlchemy AIPrompt row into a Prompt instance."""
    return Prompt(
        name=row.name,
        version=row.version,
        system_text=row.system_text,
        user_context_template=row.user_context_template,
        assistant_prime=row.assistant_prime,
        model_default=row.model,
        fallback_model=row.fallback_model,
        temperature=float(row.temperature),
        max_tokens=row.max_tokens,
        cache_strategy=CacheStrategy(row.cache_strategy.value)
        if hasattr(row.cache_strategy, "value")
        else CacheStrategy(row.cache_strategy),
    )


async def resolve(
    db: AsyncSession,
    *,
    name: str,
    version: str | None = None,
) -> Prompt:
    """Resolve a prompt by `name`.

    - `version=None` (default) -> consults `ai_prompt_active` to pick the
      current active version. If no active row exists, raises.
    - `version="<vN>"` -> returns that specific version (testing, A/B,
      preview).

    Raises:
        PromptNotFoundError: name not registered, version not found, or
            requested row is archived.
    """
    chosen = version
    if chosen is None or chosen == "active":
        active_row = (
            await db.execute(
                select(AIPromptActive).where(AIPromptActive.name == name)
            )
        ).scalar_one_or_none()
        if active_row is None:
            raise PromptNotFoundError(
                f"No active version registered for prompt '{name}'."
            )
        chosen = active_row.active_version

    row = (
        await db.execute(
            select(AIPrompt).where(
                AIPrompt.name == name,
                AIPrompt.version == chosen,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise PromptNotFoundError(
            f"Prompt '{name}@{chosen}' nao existe na tabela ai_prompt."
        )
    if row.archived_at is not None and version is None:
        # Active resolution refuses archived versions; explicit version load
        # (preview, audit) is allowed.
        raise PromptNotFoundError(
            f"Versao ativa de '{name}' aponta para '{chosen}', que esta arquivada. "
            "Reative outra versao via /admin/ai/prompts."
        )
    return _row_to_prompt(row)


async def list_versions(db: AsyncSession, *, name: str) -> list[AIPrompt]:
    """All rows for `name`, including archived, ordered by created_at desc."""
    rows = (
        await db.execute(
            select(AIPrompt)
            .where(AIPrompt.name == name)
            .order_by(AIPrompt.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


async def list_names(db: AsyncSession) -> list[str]:
    """All distinct `name` values present in `ai_prompt`."""
    rows = (
        await db.execute(select(AIPrompt.name).distinct().order_by(AIPrompt.name))
    ).scalars().all()
    return list(rows)


async def get_active_version(db: AsyncSession, *, name: str) -> str | None:
    """Return the active version string for `name`, or None if not set."""
    row = (
        await db.execute(
            select(AIPromptActive).where(AIPromptActive.name == name)
        )
    ).scalar_one_or_none()
    return row.active_version if row else None


def next_version_for(existing: list[AIPrompt]) -> str:
    """Compute next version label given existing rows.

    Strategy: parse `vN` integer suffixes; pick max + 1. Non-numeric versions
    fall back to `v(<count> + 1)`.
    """
    max_n = 0
    for row in existing:
        v = row.version
        if v.startswith("v") and v[1:].isdigit():
            max_n = max(max_n, int(v[1:]))
    if max_n == 0:
        return f"v{len(existing) + 1}"
    return f"v{max_n + 1}"
