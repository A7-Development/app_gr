"""Audit: write decision_log entries for AI calls.

We reuse the existing `decision_log` table (CLAUDE.md sec 14.2). Each AI call
becomes one append-only row with:

    decision_type           = RECOMMENDATION
    rule_or_model           = the model name (e.g. "claude-opus-4-7")
    rule_or_model_version   = "<adapter_version> + <prompt_full_id>"
    inputs_ref              = {conversation_id, message_id, redacted_input}
    output                  = {response_text, status, error?}
    explanation             = (optional human-readable summary, when applicable)
    triggered_by            = "ai:<feature>:user:<user_id>"

Pre-existing `DecisionType.RECOMMENDATION` is used (no new enum value, keeps
the schema closed). Audit consumers can still tell AI apart by checking
`rule_or_model_version` ("anthropic_v..."/"openai_v...").
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.audit_log.decision_log import DecisionLog, DecisionType


@dataclass(slots=True)
class AIAuditRecord:
    """Input arguments to `log_ai_call`."""

    tenant_id: UUID
    user_id: UUID | None
    feature: str  # 'chat' | 'insight_auto' | 'injection_check' | ...
    model: str
    adapter_version: str  # e.g. "anthropic_adapter_v1.0.0"
    prompt_full_id: str  # e.g. "chat.fidc_geral@v1"
    inputs_ref: dict
    output: dict
    explanation: str | None = None


async def log_ai_call(db: AsyncSession, rec: AIAuditRecord) -> DecisionLog:
    """Persist a decision_log row for an AI call. Caller commits."""
    triggered_by = f"ai:{rec.feature}:user:{rec.user_id}" if rec.user_id else f"ai:{rec.feature}"
    entry = DecisionLog(
        tenant_id=rec.tenant_id,
        decision_type=DecisionType.RECOMMENDATION,
        inputs_ref=rec.inputs_ref,
        rule_or_model=rec.model,
        rule_or_model_version=f"{rec.adapter_version}+{rec.prompt_full_id}",
        output=rec.output,
        explanation=rec.explanation,
        triggered_by=triggered_by,
    )
    db.add(entry)
    await db.flush()  # populate entry.id; caller commits.
    return entry
