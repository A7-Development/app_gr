"""Chat orchestrator: end-to-end multi-turn flow.

`stream_chat_response` is an async generator yielding event dicts that the API
layer relays as SSE frames to the browser. It composes everything:

    1. Rate limits (RPM / TPM / BRL-day).
    2. Conversation resolution (load or create).
    3. PII redaction on the user message.
    4. Pre-flight injection detection (cheap call).
    5. History load (summary + recent turns, trim by tokens).
    6. Prompt template resolve from registry (fall back to default if no DB row).
    7. Adapter call (Anthropic), stream deltas.
    8. Persist user/assistant `AIMessage` rows.
    9. Append `ai_usage_event` + `decision_log` + decrement credits.
    10. Final SSE event with `usage_event_id` and `turn_index`.

This module knows nothing about HTTP — it just yields dicts. The endpoint
serializes each as `event: <type>\\ndata: <json>\\n\\n`.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AIProvider, AIUsageStatus, Module
from app.core.tenant_middleware import RequestPrincipal
from app.modules.integracoes.adapters.llm.anthropic.adapter import AnthropicAdapter
from app.modules.integracoes.adapters.llm.anthropic.config import (
    CredentialNotFoundError,
    get_active_anthropic_credential,
)
from app.modules.integracoes.adapters.llm.anthropic.version import (
    ADAPTER_VERSION as ANTHROPIC_ADAPTER_VERSION,
)
from app.shared.ai.models.message import MessageRole
from app.shared.ai.models.subscription import TenantAISubscription
from app.shared.ai.prompts import Message, MessageContent, Prompt, repository
from app.shared.ai.services import audit, conversation, metering, rate_limit, redaction
from app.shared.ai.services.metering import UsageRecord

logger = logging.getLogger(__name__)


# Default prompt name to resolve if the page doesn't suggest a more specific one.
_DEFAULT_CHAT_PROMPT = "chat.fidc_geral"
_INJECTION_PROMPT = "system.prompt_injection_detector"

# Soft prediction (over-estimate): max_tokens + 500 buffer.
_TPM_RESERVE_BUFFER = 500


def _credits_for_tokens(tokens_in: int, tokens_out: int) -> int:
    """Convert token usage to billable credits (1 cred ~= 100 output tokens or 1000 input)."""
    return max(1, tokens_in // 1000 + tokens_out // 100)


async def _injection_check(
    *, db: AsyncSession, adapter: AnthropicAdapter, user_message: str
) -> tuple[bool, str, str]:
    """Run a cheap LLM call to classify INJECTION vs SAFE.

    Returns `(is_injection, model_used, prompt_full_id)`. Failures are
    non-fatal — we err on SAFE so a misbehaving classifier doesn't lock the
    whole tenant out.
    """
    try:
        detector = await repository.resolve(db, name=_INJECTION_PROMPT)
    except repository.PromptNotFoundError as e:
        logger.warning("Injection detector prompt not found (treating as safe): %s", e)
        return False, "", f"{_INJECTION_PROMPT}@unknown"

    msgs = detector.render({"user_message": user_message})

    try:
        full_text = ""
        async for delta in adapter.chat_stream(
            messages=[m.model_dump() for m in msgs],
            model=detector.model_default,
            temperature=detector.temperature,
            max_tokens=detector.max_tokens,
        ):
            full_text += delta
        is_injection = "INJECTION" in full_text.upper()
        return is_injection, detector.model_default, detector.full_id
    except Exception as e:
        logger.warning("Injection check failed (treating as safe): %s", e)
        return False, detector.model_default, detector.full_id


async def _build_messages(
    *,
    db: AsyncSession,
    conv: Any,  # AIConversation (avoid circular import in type hints)
    page_context: str,
    period: str | None,
    filters: str | None,
    user_message_redacted: str,
) -> tuple[Prompt, list[dict]]:
    """Render the prompt template + inject history + add the new user turn."""
    prompt = await repository.resolve(db, name=_DEFAULT_CHAT_PROMPT)
    rendered = prompt.render(
        {
            "page": page_context,
            "period": period or "",
            "filters": filters or "",
        }
    )

    # Append history (summary + recent turns) and the new user message.
    history = await conversation.load_history_for_prompt(db, conversation=conv)
    for h in history:
        rendered.append(
            Message(role=h.role, content=[MessageContent(text=h.text)])
        )
    rendered.append(
        Message(role="user", content=[MessageContent(text=user_message_redacted)])
    )

    return prompt, [m.model_dump() for m in rendered]


async def stream_chat_response(
    *,
    db: AsyncSession,
    principal: RequestPrincipal,
    user_message: str,
    page_context: str,
    period: str | None,
    filters: str | None,
    conversation_id: uuid.UUID | None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield event dicts for an SSE stream.

    Event types:
        - {"type": "conversation_id", "conversation_id": "<uuid>"}  (always first)
        - {"type": "delta", "text": "<chunk>"}
        - {"type": "error", "error": "<message>", "status": "<code>"}  (terminal)
        - {"type": "done", "usage_event_id": "<uuid>", "turn_index": N}  (terminal, success)
    """
    tenant_id = principal.tenant_id
    user_id = principal.user_id

    # ----- Rate / cost guards -------------------------------------------------
    sub = (
        await db.execute(
            select(TenantAISubscription).where(
                TenantAISubscription.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    hard_cap = sub.hard_cap_brl if sub else None

    try:
        await rate_limit.check_rpm(tenant_id)
        await rate_limit.reserve_tpm(
            tenant_id, predicted_tokens=2048 + _TPM_RESERVE_BUFFER
        )
        await rate_limit.check_daily_cost_cap(tenant_id, hard_cap_brl=hard_cap)
    except rate_limit.RateLimitError as e:
        yield {"type": "error", "error": str(e), "status": "rate_limited"}
        return

    # ----- Conversation -------------------------------------------------------
    try:
        conv = await conversation.get_or_create_conversation(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            page_context=page_context,
        )
    except (LookupError, PermissionError) as e:
        yield {"type": "error", "error": str(e), "status": "not_found"}
        return

    yield {"type": "conversation_id", "conversation_id": str(conv.id)}

    # ----- Redact user message -----------------------------------------------
    redacted = redaction.redact(user_message)
    user_text_for_llm = redacted.text

    # ----- Acquire credential + adapter --------------------------------------
    try:
        cred = await get_active_anthropic_credential(db)
    except CredentialNotFoundError as e:
        yield {"type": "error", "error": str(e), "status": "config_error"}
        return

    adapter = AnthropicAdapter(api_key=cred.api_key)

    try:
        # ----- Pre-flight: injection check ----------------------------------
        is_injection, injection_model, injection_prompt_id = await _injection_check(
            db=db, adapter=adapter, user_message=user_text_for_llm
        )
        if is_injection:
            await metering.record_usage(
                db,
                UsageRecord(
                    request_id=f"injection-block-{uuid.uuid4()}",
                    tenant_id=tenant_id,
                    user_id=user_id,
                    feature="injection_check",
                    context_module=Module.BI,  # default; overridden when page known
                    provider=AIProvider.ANTHROPIC,
                    model=injection_model,
                    prompt_template_version=injection_prompt_id,
                    tokens_input=0,
                    tokens_output=0,
                    tokens_cached=0,
                    cost_brl_provider=Decimal("0"),
                    cost_credits_billed=1,
                    status=AIUsageStatus.INJECTION_BLOCKED,
                ),
            )
            await db.commit()
            yield {
                "type": "error",
                "error": (
                    "A mensagem foi bloqueada por suspeita de tentativa de "
                    "injecao de prompt. Reformule a pergunta sobre os dados."
                ),
                "status": "injection_blocked",
            }
            return

        # ----- Build full prompt and call main adapter ----------------------
        prompt, payload_messages = await _build_messages(
            db=db,
            conv=conv,
            page_context=page_context,
            period=period,
            filters=filters,
            user_message_redacted=user_text_for_llm,
        )

        full_text_chunks: list[str] = []
        async for delta in adapter.chat_stream(
            messages=payload_messages,
            model=prompt.model_default,
            temperature=prompt.temperature,
            max_tokens=prompt.max_tokens,
        ):
            full_text_chunks.append(delta)
            yield {"type": "delta", "text": delta}

        result = adapter.last_result
        assert result is not None, "adapter.last_result not populated"

        # ----- Persist + audit ----------------------------------------------
        # 1. Append user message turn
        user_msg = await conversation.append_message(
            db,
            conversation=conv,
            role=MessageRole.USER,
            text_redacted=user_text_for_llm,
        )

        # 2. Audit
        audit_entry = await audit.log_ai_call(
            db,
            audit.AIAuditRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                feature="chat",
                model=result.model,
                adapter_version=ANTHROPIC_ADAPTER_VERSION,
                prompt_full_id=prompt.full_id,
                inputs_ref={
                    "conversation_id": str(conv.id),
                    "user_message_id": str(user_msg.id),
                    "page": page_context,
                    "period": period,
                    "filters": filters,
                    "redacted": user_text_for_llm,
                },
                output={
                    "text_redacted": result.full_text,
                    "stop_reason": result.stop_reason,
                    "tokens": {
                        "input": result.usage.tokens_input,
                        "output": result.usage.tokens_output,
                        "cached": result.usage.tokens_cached,
                    },
                },
            ),
        )

        # 3. Metering (and credit decrement)
        usage_event = await metering.record_usage(
            db,
            UsageRecord(
                request_id=result.request_id or str(uuid.uuid4()),
                tenant_id=tenant_id,
                user_id=user_id,
                feature="chat",
                context_module=Module.BI,
                provider=AIProvider.ANTHROPIC,
                model=result.model,
                prompt_template_version=prompt.full_id,
                tokens_input=result.usage.tokens_input,
                tokens_output=result.usage.tokens_output,
                tokens_cached=result.usage.tokens_cached,
                cost_brl_provider=result.cost_brl,
                cost_credits_billed=_credits_for_tokens(
                    result.usage.tokens_input, result.usage.tokens_output
                ),
                status=AIUsageStatus.OK,
                decision_log_id=audit_entry.id,
            ),
        )

        # 4. Append assistant message turn (links to usage_event)
        await conversation.append_message(
            db,
            conversation=conv,
            role=MessageRole.AI,
            text_redacted=result.full_text,
            usage_event_id=usage_event.id,
        )

        # 5. Update day-cost ledger
        await rate_limit.record_cost(tenant_id, cost_brl=result.cost_brl)

        await db.commit()

        yield {
            "type": "done",
            "usage_event_id": str(usage_event.id),
            "turn_index": conv.turn_count,
        }

    except Exception as e:
        logger.exception("Chat stream failed for tenant %s user %s", tenant_id, user_id)
        await db.rollback()
        yield {"type": "error", "error": f"Falha na chamada de IA: {e}", "status": "error"}
    finally:
        await adapter.aclose()
