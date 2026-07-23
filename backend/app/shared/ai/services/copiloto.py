"""Copiloto (Strata AI) orchestrator — free-form chat turn over the agent loop.

Spec: specs/active/copiloto-mcp.md (v3). This is the Fase 1a turn runner:
one SSE turn of the Strata AI chat, resolved through the agent catalog
(`credito.strata_ai`) and executed with the official Anthropic SDK in a
tool-loop skeleton. Fase 1a runs with an EMPTY tool list; Fase 1b plugs the
MCP-wrapped tools and Fase 2 the native silver tools into the same loop —
the loop shape does not change (spec §6.1).

Differences from `services/chat.py` (AIPanel path, untouched — spec §7):
- Agent-resolved system prompt (persona + expertise + `chat.copiloto` via
  `AgentRegistry`), not a bare prompt template.
- SDK `messages.create` per iteration (tool loop ready) instead of the
  httpx streaming adapter. R1 buffers the answer and emits a single
  `delta` at the end (spec §6.2); R2 will switch to `messages.stream`.
- Conversations carry `surface='copiloto'` and assistant turns persist
  their structured content blocks envelope-encrypted (`content_encrypted`)
  so follow-up turns can re-feed tool results (spec §6.5).

Event dicts yielded (endpoint serializes as SSE):
    {"type": "conversation_id", "conversation_id": "<uuid>"}   (always first)
    {"type": "ping"}                                           (heartbeat ~15s)
    {"type": "tool_status", "id", "source", "label", "status", "duration_ms"}
    {"type": "delta", "text": "<full answer>"}                 (R1: once)
    {"type": "error", "error", "status"}                       (terminal)
    {"type": "done", "usage_event_id", "turn_index"}           (terminal, ok)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic._scope import ScopedContext
from app.agentic.agents._compose import compose_system_text
from app.agentic.agents.registry import AgentNotFoundError, AgentRegistry
from app.agentic.mcp.public import (
    MCP_TOOL_PREFIX,
    McpCapabilities,
    McpWrappedTool,
    build_mcp_capabilities,
)
from app.agentic.tools._base import AgentTool
from app.core.enums import AIProvider, AIUsageStatus, Module, Permission
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
from app.shared.ai.services import audit, conversation, metering, rate_limit, redaction
from app.shared.ai.services.chat import _credits_for_tokens, _injection_check
from app.shared.ai.services.metering import UsageRecord
from app.shared.crypto import encrypt_envelope
from app.shared.identity.subscription import TenantModuleSubscription
from app.shared.identity.user_permission import UserModulePermission

logger = logging.getLogger(__name__)

_AGENT_NAME = "credito.strata_ai"
_SURFACE = "copiloto"
_FEATURE = "copiloto_chat"

_MAX_TOOL_ITERATIONS = 12
_TPM_RESERVE_BUFFER = 500
_DEFAULT_MAX_TOKENS = 4096

# Heartbeat interval while awaiting a long model/tool step (spec §6.2 —
# keeps proxies from dropping the SSE connection).
_HEARTBEAT_SECONDS = 15.0


def _estimate_cost_brl(
    *, tokens_input: int, tokens_output: int, tokens_cache_read: int, tokens_cache_creation: int
) -> Decimal:
    """Coarse BRL cost estimate — same approximation as engine/runtime.py

    (generic Sonnet pricing + fixed FX R$ 5.50/USD; fine-grained billing is
    the metering layer's future concern).
    """
    cost_usd = (
        tokens_input * 3.0
        + tokens_output * 15.0
        + tokens_cache_read * 0.30
        + tokens_cache_creation * 3.75
    ) / 1_000_000
    return Decimal(str(round(cost_usd * 5.50, 4)))


def _tool_status_frame(
    *, status_id: str, source: str, label: str, status: str, duration_ms: int | None = None
) -> dict[str, Any]:
    """SSE frame for live tool feedback. `source` is white-label vocabulary:
    'lake' (native/silver) or 'hub' (external MCP) — vendor never named."""
    return {
        "type": "tool_status",
        "id": status_id,
        "source": source,
        "label": label,
        "status": status,
        "duration_ms": duration_ms,
    }


async def _load_user_permissions(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> dict[Module, Permission]:
    """Permissoes efetivas do usuario: user_module_permission ∩ assinatura
    do tenant (spec §6.3 — cardapio holistico dirigido por permissao)."""
    enabled = {
        Module(row)
        for row in (
            await db.execute(
                select(TenantModuleSubscription.module).where(
                    TenantModuleSubscription.tenant_id == tenant_id,
                    TenantModuleSubscription.enabled.is_(True),
                )
            )
        ).scalars()
    }
    perms: dict[Module, Permission] = {}
    rows = (
        await db.execute(
            select(
                UserModulePermission.module, UserModulePermission.permission
            ).where(UserModulePermission.user_id == user_id)
        )
    ).all()
    for module, permission in rows:
        m = Module(module)
        if m in enabled and Permission(permission) != Permission.NONE:
            perms[m] = Permission(permission)
    return perms


async def _create_with_heartbeat(
    coro: Any,
) -> AsyncIterator[tuple[str, Any]]:
    """Await `coro` yielding ('ping', None) every _HEARTBEAT_SECONDS.

    Final item is ('result', value) — or the exception propagates.
    """
    task = asyncio.ensure_future(coro)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=_HEARTBEAT_SECONDS)
            if done:
                yield "result", task.result()
                return
            yield "ping", None
    finally:
        if not task.done():
            task.cancel()


async def stream_copiloto_response(
    *,
    db: AsyncSession,
    principal: RequestPrincipal,
    user_message: str,
    conversation_id: uuid.UUID | None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield event dicts for one SSE turn of the Strata AI chat."""
    tenant_id = principal.tenant_id
    user_id = principal.user_id

    # ----- Rate / cost guards (same policy as chat.py) -----------------------
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
            tenant_id, predicted_tokens=_DEFAULT_MAX_TOKENS + _TPM_RESERVE_BUFFER
        )
        await rate_limit.check_daily_cost_cap(tenant_id, hard_cap_brl=hard_cap)
    except rate_limit.RateLimitError as e:
        yield {"type": "error", "error": str(e), "status": "rate_limited"}
        return

    # ----- Conversation (surface-scoped) -------------------------------------
    try:
        conv = await conversation.get_or_create_conversation(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            page_context=_SURFACE,
            surface=_SURFACE,
        )
    except (LookupError, PermissionError) as e:
        yield {"type": "error", "error": str(e), "status": "not_found"}
        return

    yield {"type": "conversation_id", "conversation_id": str(conv.id)}

    # ----- Redact user message ------------------------------------------------
    # CPF/CNPJ preservados: sao a ENTRADA da consulta no chat livre —
    # mascara-los quebraria as tools (spec §12.7). Email/conta continuam
    # redactados.
    redacted = redaction.redact(user_message, preserve_query_identifiers=True)
    user_text_for_llm = redacted.text

    # ----- Credential ---------------------------------------------------------
    try:
        cred = await get_active_anthropic_credential(db)
    except CredentialNotFoundError as e:
        yield {"type": "error", "error": str(e), "status": "config_error"}
        return

    # The injection detector reuses the httpx adapter path (cheap call).
    adapter = AnthropicAdapter(api_key=cred.api_key)
    mcp_caps: McpCapabilities | None = None

    try:
        # ----- Pre-flight: injection check -----------------------------------
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
                    context_module=Module.CREDITO,
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

        # ----- Resolve agent (DB-first: persona + expertise + prompt) --------
        permissions = await _load_user_permissions(
            db, tenant_id=tenant_id, user_id=user_id
        )
        scope = ScopedContext(
            tenant_id=tenant_id,
            empresa_id=None,
            user_id=user_id,
            module=Module.CREDITO,
            permissions=permissions,
            db=db,
        )
        try:
            resolved = await AgentRegistry.get(db, name=_AGENT_NAME, scope=scope)
        except AgentNotFoundError as e:
            yield {"type": "error", "error": str(e), "status": "config_error"}
            return

        # ----- Capabilities: MCP (1b) + nativas (F2) -------------------------
        mcp_caps = await build_mcp_capabilities(
            db, mcp_toolsets=resolved.mcp_toolsets, scope=scope
        )
        for _name, _err in mcp_caps.unavailable.items():
            # Aviso honesto: o cardapio segue sem o servidor (spec §4.3/§6.6).
            yield _tool_status_frame(
                status_id=str(uuid.uuid4()),
                source="hub",
                label="O Strata Hub está indisponível agora — respondo com o que tenho.",
                status="error",
            )

        native_tools: list[AgentTool] = []
        tools: list[AgentTool | McpWrappedTool] = [*native_tools, *mcp_caps.tools]
        tool_definitions = [t.to_api_definition() for t in tools]
        tool_dispatch: dict[str, AgentTool | McpWrappedTool] = {
            t.name: t for t in tools
        }

        # ----- System prompt + message history --------------------------------
        rendered = resolved.prompt.render(
            {"page": _SURFACE, "period": "", "filters": ""}
        )
        prompt_system_text = "\n\n".join(
            block.text
            for msg in rendered
            if msg.role == "system"
            for block in msg.content
        )
        system_text = compose_system_text(
            persona=resolved.persona,
            expertises=resolved.expertises,
            prompt_system_text=prompt_system_text,
            output_schema=None,  # free-text chat — never inject <output_format>
        )
        system_blocks = [
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        history = await conversation.load_history_for_prompt(db, conversation=conv)
        messages: list[dict[str, Any]] = [
            {
                "role": h.role if h.role in ("user", "assistant") else "user",
                "content": h.text,
            }
            for h in history
        ]
        messages.append({"role": "user", "content": user_text_for_llm})
        turn_start_len = len(messages)

        # ----- Tool loop (SDK) ------------------------------------------------
        client = AsyncAnthropic(api_key=cred.api_key)
        model = resolved.model
        max_tokens = (
            resolved.max_tokens or resolved.prompt.max_tokens or _DEFAULT_MAX_TOKENS
        )
        temperature = (
            resolved.temperature
            if resolved.temperature is not None
            else resolved.prompt.temperature
        )

        tokens_input = tokens_output = tokens_cache_read = tokens_cache_creation = 0
        final_text = ""
        stop_reason: str | None = None

        try:
            for _iteration in range(_MAX_TOOL_ITERATIONS):
                kwargs: dict[str, Any] = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system_blocks,
                    "messages": messages,
                }
                if temperature is not None:
                    kwargs["temperature"] = temperature
                if tool_definitions:
                    kwargs["tools"] = tool_definitions

                response = None
                async for kind, value in _create_with_heartbeat(
                    client.messages.create(**kwargs)
                ):
                    if kind == "ping":
                        yield {"type": "ping"}
                    else:
                        response = value
                assert response is not None

                usage = response.usage
                tokens_input += usage.input_tokens
                tokens_output += usage.output_tokens
                tokens_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
                tokens_cache_creation += (
                    getattr(usage, "cache_creation_input_tokens", 0) or 0
                )
                stop_reason = response.stop_reason

                if response.stop_reason != "tool_use":
                    final_text = "".join(
                        block.text
                        for block in response.content
                        if block.type == "text"
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": [b.model_dump() for b in response.content],
                        }
                    )
                    break

                # tool_use: echo assistant content, execute each tool, append
                # tool_results, iterate. Fase 1a never reaches this branch
                # (no tools offered) — the plumbing is here so 1b only adds
                # executors, not loop structure (spec §6.1).
                messages.append(
                    {
                        "role": "assistant",
                        "content": [b.model_dump() for b in response.content],
                    }
                )
                tool_results: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    tool = tool_dispatch.get(block.name)
                    status_id = str(uuid.uuid4())
                    source = (
                        "hub" if block.name.startswith(MCP_TOOL_PREFIX) else "lake"
                    )
                    label = (
                        "Consultando o Strata Hub…"
                        if source == "hub"
                        else "Consultando o Strata Lake…"
                    )
                    yield _tool_status_frame(
                        status_id=status_id, source=source, label=label, status="running"
                    )
                    started = time.monotonic()
                    try:
                        if tool is None:
                            raise KeyError(f"tool '{block.name}' fora do cardapio")
                        if isinstance(tool, McpWrappedTool):
                            result_text = await tool.execute(dict(block.input))
                        else:
                            result_text = await tool.handler(scope, dict(block.input))
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            }
                        )
                        yield _tool_status_frame(
                            status_id=status_id,
                            source=source,
                            label=label,
                            status="done",
                            duration_ms=int((time.monotonic() - started) * 1000),
                        )
                    except Exception as tool_exc:  # inclui McpToolCallError — modelo decide
                        logger.warning(
                            "Copiloto tool '%s' falhou: %s", block.name, tool_exc
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Erro ao executar a consulta: {tool_exc}",
                                "is_error": True,
                            }
                        )
                        yield _tool_status_frame(
                            status_id=status_id,
                            source=source,
                            label=label,
                            status="error",
                            duration_ms=int((time.monotonic() - started) * 1000),
                        )
                messages.append({"role": "user", "content": tool_results})
            else:
                # Exhausted iterations without a final answer (spec §6.6).
                final_text = (
                    "Precisei parar por aqui — a pergunta exigiu consultas "
                    "demais num turno so. Refine a pergunta e tente de novo."
                )
                stop_reason = "max_iterations"
        finally:
            await client.close()

        yield {"type": "delta", "text": final_text}

        # ----- Persist + audit ------------------------------------------------
        user_msg = await conversation.append_message(
            db,
            conversation=conv,
            role=MessageRole.USER,
            text_redacted=user_text_for_llm,
        )

        audit_entry = await audit.log_ai_call(
            db,
            audit.AIAuditRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                feature=_FEATURE,
                model=model,
                adapter_version=ANTHROPIC_ADAPTER_VERSION,
                # Composite version: agent@v + persona@v + expertises@v +
                # prompt@v (spec §19.12) — one key tells the whole story.
                prompt_full_id=resolved.audit_version,
                inputs_ref={
                    "conversation_id": str(conv.id),
                    "user_message_id": str(user_msg.id),
                    "surface": _SURFACE,
                    "redacted": user_text_for_llm,
                    "tools_called": [
                        b.get("name")
                        for m in messages[turn_start_len:]
                        if m["role"] == "assistant" and isinstance(m["content"], list)
                        for b in m["content"]
                        if isinstance(b, dict) and b.get("type") == "tool_use"
                    ],
                },
                output={
                    "text_redacted": final_text,
                    "stop_reason": stop_reason,
                    "tokens": {
                        "input": tokens_input,
                        "output": tokens_output,
                        "cached": tokens_cache_read,
                    },
                },
            ),
        )

        cost_brl = _estimate_cost_brl(
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_cache_read=tokens_cache_read,
            tokens_cache_creation=tokens_cache_creation,
        )
        usage_event = await metering.record_usage(
            db,
            UsageRecord(
                request_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                user_id=user_id,
                feature=_FEATURE,
                context_module=Module.CREDITO,
                provider=AIProvider.ANTHROPIC,
                model=model,
                prompt_template_version=resolved.audit_version,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                tokens_cached=tokens_cache_read,
                cost_brl_provider=cost_brl,
                cost_credits_billed=_credits_for_tokens(tokens_input, tokens_output),
                status=AIUsageStatus.OK,
                decision_log_id=audit_entry.id,
            ),
        )

        # Assistant turn: redacted text + full structured blocks of the turn
        # (everything after the initial user message), envelope-encrypted so
        # the next turn can re-feed tool results (spec §6.5).
        turn_blocks = messages[turn_start_len:]
        await conversation.append_message(
            db,
            conversation=conv,
            role=MessageRole.AI,
            text_redacted=final_text,
            usage_event_id=usage_event.id,
            content_encrypted=encrypt_envelope({"messages": turn_blocks}),
        )

        await rate_limit.record_cost(tenant_id, cost_brl=cost_brl)
        await db.commit()

        yield {
            "type": "done",
            "usage_event_id": str(usage_event.id),
            "turn_index": conv.turn_count,
        }

    except Exception as e:
        logger.exception(
            "Copiloto stream failed for tenant %s user %s", tenant_id, user_id
        )
        await db.rollback()
        yield {"type": "error", "error": f"Falha na chamada de IA: {e}", "status": "error"}
    finally:
        if mcp_caps is not None:
            await mcp_caps.aclose()
        await adapter.aclose()
