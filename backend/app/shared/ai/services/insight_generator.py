"""Insight generator: 3 short bullets for the InsightBar of a dashboard page.

Single (non-streaming) LLM call. Cheaper model + tight max_tokens. Used by
GET /api/v1/ai/insights with server-side cache (10min TTL by `(tenant, page,
filters_hash)`).

This module does the LLM call but DOES NOT cache. The endpoint layer caches.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.engine.prompts import repository
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
from app.shared.ai.services import audit, metering
from app.shared.ai.services.metering import UsageRecord

logger = logging.getLogger(__name__)


_INSIGHT_PROMPT = "insight.carteira_3bullets"


async def generate_insights(
    *,
    db: AsyncSession,
    principal: RequestPrincipal,
    page: str,
    period: str | None,
    kpis_block: str,
) -> dict:
    """Run a one-shot insight call. Returns `{insights, generated_at}`.

    `kpis_block` is plain text the caller assembles from the page's current
    KPIs/trends (the endpoint layer fetches these from the warehouse).
    """
    try:
        prompt = await repository.resolve(db, name=_INSIGHT_PROMPT)
    except repository.PromptNotFoundError:
        logger.warning("Insight prompt %s not active — returning empty insights.", _INSIGHT_PROMPT)
        return {"insights": [], "generated_at": datetime.now(UTC).isoformat()}

    msgs = prompt.render({"period": period or "", "kpis_block": kpis_block})

    try:
        cred = await get_active_anthropic_credential(db)
    except CredentialNotFoundError:
        # Soft-fail to empty insights; the dashboard still renders.
        logger.warning("No Anthropic credential — returning empty insights.")
        return {"insights": [], "generated_at": datetime.now(UTC).isoformat()}

    adapter = AnthropicAdapter(api_key=cred.api_key)
    try:
        full_text = ""
        async for delta in adapter.chat_stream(
            messages=[m.model_dump() for m in msgs],
            model=prompt.model_default,
            temperature=prompt.temperature,
            max_tokens=prompt.max_tokens,
        ):
            full_text += delta

        result = adapter.last_result
        if result is None:
            return {"insights": [], "generated_at": datetime.now(UTC).isoformat()}

        # Parse JSON array (prompt asks for it). Tolerate prefix/suffix garbage.
        bullets = _extract_json_array(full_text)
        items = [{"text": str(b)} for b in bullets[:3]]

        # Metering + audit
        audit_entry = await audit.log_ai_call(
            db,
            audit.AIAuditRecord(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                feature="insight_auto",
                model=result.model,
                adapter_version=ANTHROPIC_ADAPTER_VERSION,
                prompt_full_id=prompt.full_id,
                inputs_ref={"page": page, "period": period},
                output={"insights": items, "raw": result.full_text[:500]},
            ),
        )
        await metering.record_usage(
            db,
            UsageRecord(
                request_id=result.request_id or str(uuid.uuid4()),
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                feature="insight_auto",
                context_module=Module.BI,
                provider=AIProvider.ANTHROPIC,
                model=result.model,
                prompt_template_version=prompt.full_id,
                tokens_input=result.usage.tokens_input,
                tokens_output=result.usage.tokens_output,
                tokens_cached=result.usage.tokens_cached,
                cost_brl_provider=result.cost_brl,
                cost_credits_billed=5,  # flat: insight = 5 cred
                status=AIUsageStatus.OK,
                decision_log_id=audit_entry.id,
            ),
        )
        await db.commit()
        return {"insights": items, "generated_at": datetime.now(UTC).isoformat()}

    except Exception as e:
        logger.exception("generate_insights failed: %s", e)
        await db.rollback()
        # Best-effort: do not raise (the dashboard should still render).
        return {"insights": [], "generated_at": datetime.now(UTC).isoformat()}
    finally:
        await adapter.aclose()


def _extract_json_array(text: str) -> list:
    """Find a JSON array in `text`, tolerating prefix or trailing text."""
    text = text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []


# Suppress unused-import lint if Decimal is removed in future tweaks.
_ = Decimal
