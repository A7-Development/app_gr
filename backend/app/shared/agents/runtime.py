"""Specialist Agent runtime — invokes Claude via claude-agent-sdk.

Flow per agent invocation:
1. Resolve prompt from `ai_prompt` table (versioned, editable without deploy).
2. Render prompt with context (workflow node previous outputs + dossie data).
3. Build in-process MCP server with tools requested by the agent spec.
4. Invoke claude-agent-sdk's `query()` with thinking budget.
5. Capture token usage from the result (for metering).
6. Parse the agent's text output as JSON, validate against `output_schema`.
   Retry once on validation failure with a correction prompt.
7. Persist a `decision_log` entry + `ai_usage_event` for billing/audit.
8. Return `AgentRunResult` to the workflow node.

This is a SECOND adapter layer over the LLM, separate from
`adapters/llm/anthropic/` (which handles simple chat). Reason: the SDKs
are different packages (`claude-agent-sdk` vs `anthropic`) and the
abstraction levels differ (agent loop with tools vs single completion).
"""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Iterator

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.llm.anthropic.config import (
    CredentialNotFoundError,
    get_active_anthropic_credential,
)
from app.shared.agents.catalog import (
    TOOL_DOC_GET,
    TOOL_DOC_LIST,
    TOOL_DOSSIER_FLAG,
    TOOL_DOSSIER_READ,
    TOOL_DOSSIER_SAVE,
    TOOL_REF_CALC,
    TOOL_REF_COMPARE,
    SpecialistAgentSpec,
)
from app.shared.ai.prompts import repository as prompt_repo

if TYPE_CHECKING:
    from app.shared.workflow.nodes._base import NodeContext

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentRunResult:
    """Outcome of a Specialist Agent run."""

    output_data: dict[str, Any]      # parsed + validated agent output
    output_schema_name: str           # e.g. 'SocialContractAnalysis'
    tokens_input: int = 0
    tokens_output: int = 0
    cost_brl: Decimal = Decimal("0")
    prompt_full_id: str = ""          # 'agent.social_contract@v1'


# ─── Prompt rendering helpers ─────────────────────────────────────────────


def _render_context_for_prompt(ctx: NodeContext) -> str:
    """Build a text block summarizing previous outputs and trigger data.

    The agent receives this as part of the user prompt so it knows what
    other nodes produced. Big outputs are truncated.
    """
    lines: list[str] = []
    lines.append("[Contexto do dossie]")
    lines.append(f"Dossier ID: {ctx.trigger_data.get('dossier_id', '?')}")

    if ctx.trigger_data.get("target_cnpj"):
        lines.append(f"CNPJ alvo: {ctx.trigger_data['target_cnpj']}")
    if ctx.trigger_data.get("target_name"):
        lines.append(f"Empresa alvo: {ctx.trigger_data['target_name']}")

    lines.append("")
    lines.append("[Outputs de nos anteriores]")
    if not ctx.previous_outputs:
        lines.append("(nenhum)")
    else:
        for nid, payload in ctx.previous_outputs.items():
            output = payload.get("output")
            if output is None:
                continue
            try:
                serialized = json.dumps(output, ensure_ascii=False, indent=2)[:2000]
            except (TypeError, ValueError):
                serialized = str(output)[:2000]
            lines.append(f"--- {nid} ---")
            lines.append(serialized)
    return "\n".join(lines)


async def _render_checklist_block(
    db: AsyncSession,
    *,
    tenant_id: Any,
    section_id: str,
) -> str:
    """Build the per-tenant checklist block injected in the agent prompt.

    Each tenant defines its own analysis items in `credit_analysis_item` (with
    `tenant_id IS NULL` as Strata templates available to all). The agent
    receives the items relevant to its section and must evaluate each one.

    Returns empty string when tenant has no checklist for this section —
    agent then performs free-form analysis.
    """
    if not section_id:
        return ""

    # Late import to avoid circular ref at module load.
    from sqlalchemy import or_, select

    from app.modules.credito.models.analysis_item import CreditAnalysisItem

    rows = (
        await db.execute(
            select(CreditAnalysisItem)
            .where(
                or_(
                    CreditAnalysisItem.tenant_id == tenant_id,
                    CreditAnalysisItem.tenant_id.is_(None),
                ),
                CreditAnalysisItem.section == section_id,
                CreditAnalysisItem.active.is_(True),
            )
            .order_by(
                CreditAnalysisItem.tenant_id.is_(None),  # tenant-specific first
                CreditAnalysisItem.order_index,
            )
        )
    ).scalars().all()

    if not rows:
        return ""

    parts: list[str] = []
    parts.append("## Checklist a avaliar nesta secao")
    parts.append("")
    parts.append(
        "Os itens abaixo foram definidos pelo tenant para esta secao. Avalie "
        "CADA UM e inclua o resultado em `checklist_results` no seu output, "
        "respeitando o codigo do item e a severidade definida."
    )
    parts.append("")
    for item in rows:
        sev = item.severity.value if hasattr(item.severity, "value") else str(item.severity)
        parts.append(f"- **[{item.code}]** ({sev}): {item.description}")
        if item.guidance:
            parts.append(f"  _Orientacao_: {item.guidance}")
    return "\n".join(parts)


# ─── Tool wiring ──────────────────────────────────────────────────────────


def _build_tools_for_agent(
    spec: SpecialistAgentSpec,
    tenant_id: Any,
    dossier_id: Any,
    db: AsyncSession,
) -> list:
    """Instantiate the tool list for this agent based on spec.tools.

    Imports are local here to avoid loading claude-agent-sdk at module
    import time (so unrelated tests don't need it installed).
    """
    from app.shared.agents.tools.document_tools import make_document_tools
    from app.shared.agents.tools.dossier_tools import make_dossier_tools
    from app.shared.agents.tools.reference_tools import make_reference_tools

    selected: list = []
    requested = set(spec.tools)

    if requested & {TOOL_DOSSIER_READ, TOOL_DOSSIER_FLAG, TOOL_DOSSIER_SAVE}:
        all_dossier = make_dossier_tools(tenant_id, dossier_id, db)
        # Filter by name match.
        for t in all_dossier:
            if t.name in requested:  # type: ignore[attr-defined]
                selected.append(t)

    if requested & {TOOL_DOC_GET, TOOL_DOC_LIST}:
        all_doc = make_document_tools(tenant_id, dossier_id, db)
        for t in all_doc:
            if t.name in requested:  # type: ignore[attr-defined]
                selected.append(t)

    if requested & {TOOL_REF_COMPARE, TOOL_REF_CALC}:
        all_ref = make_reference_tools(tenant_id, dossier_id, db)
        for t in all_ref:
            if t.name in requested:  # type: ignore[attr-defined]
                selected.append(t)

    return selected


# ─── JSON extraction ──────────────────────────────────────────────────────


_JSON_BLOCK_RE = re.compile(r"```json\s*([\s\S]+?)\s*```")


def _extract_json_object(text: str) -> dict[str, Any]:
    """Find the JSON object inside the model's reply.

    Tries (in order):
    1. ```json ... ``` fenced block
    2. Last balanced { ... } block
    3. Whole text as JSON
    """
    if not text:
        raise ValueError("Resposta vazia.")

    m = _JSON_BLOCK_RE.search(text)
    if m:
        return json.loads(m.group(1))

    # Find last balanced {...}
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    candidate = text[start : i + 1]
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1
                    continue

    return json.loads(text)


# ─── Main entry point ─────────────────────────────────────────────────────


async def run_specialist_agent(
    *,
    spec: SpecialistAgentSpec,
    ctx: NodeContext,
    db: AsyncSession,
) -> AgentRunResult:
    """Run a Specialist Agent and return its validated output.

    On output schema validation failure, retries once with a correction prompt.
    On second failure, raises ValueError (the workflow node will mark FAILED).
    """
    # Resolve versioned prompt.
    prompt = await prompt_repo.resolve(db, name=spec.prompt_name)
    rendered = prompt.render(context={"page": "credito.dossie", "period": "", "filters": ""})
    system_text = "\n\n".join(
        block.text for msg in rendered if msg.role == "system" for block in msg.content
    )

    # Inject checklist items defined by the tenant for this agent's section.
    # Each tenant configures its own items via /credito/checklist; the agent
    # receives them dynamically — prompts stay generic across tenants.
    checklist_block = await _render_checklist_block(
        db,
        tenant_id=ctx.tenant_id,
        section_id=spec.section_id,
    )

    user_parts = [_render_context_for_prompt(ctx)]
    if checklist_block:
        user_parts.append(checklist_block)
    user_parts.append(
        "Produza a analise no formato JSON definido pelo schema da tarefa. "
        "Inclua o objeto JSON dentro de um bloco ```json ... ```."
    )
    user_text = "\n\n".join(user_parts)

    output_data, tokens_in, tokens_out, cost = await _invoke_with_validation(
        spec=spec,
        system_text=system_text,
        user_text=user_text,
        ctx=ctx,
        db=db,
    )

    return AgentRunResult(
        output_data=output_data,
        output_schema_name=spec.output_schema.__name__,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        cost_brl=cost,
        prompt_full_id=prompt.full_id,
    )


async def run_document_extraction(
    *,
    spec: SpecialistAgentSpec,
    document: Any,  # CreditDossierDocument
    ctx: NodeContext,
    db: AsyncSession,
    template_id: Any = None,  # Optional CreditDocumentTemplate.id
) -> AgentRunResult:
    """Run the document_extractor agent on a single document.

    Resolves the prompt name dynamically: `extract.<doc_type>` (falls back
    to `extract.document` if the specific one isn't seeded yet). When a
    `template_id` is passed (or auto-resolved from a tenant template that
    matches the doc_type), the template's `instructions` and `fields_schema`
    are injected into the user prompt — guiding extraction without changing
    the prompt itself.

    Persists `ai_extraction` directly on the document row.
    """
    doc_type = (
        document.doc_type.value
        if hasattr(document.doc_type, "value")
        else str(document.doc_type)
    )

    prompt_name_specific = f"extract.{doc_type}"
    try:
        prompt = await prompt_repo.resolve(db, name=prompt_name_specific)
    except prompt_repo.PromptNotFoundError:
        # Fallback to the base extractor prompt.
        prompt = await prompt_repo.resolve(db, name=spec.prompt_name)

    rendered = prompt.render(context={"page": "credito.documento", "period": "", "filters": ""})
    system_text = "\n\n".join(
        block.text for msg in rendered if msg.role == "system" for block in msg.content
    )

    # Optionally pull tenant template guidance (or starter template) for this doc_type.
    template_block = await _render_template_block(
        db,
        tenant_id=ctx.tenant_id,
        doc_type=doc_type,
        template_id=template_id,
    )

    user_parts = [
        f"Tipo do documento: {doc_type}",
        f"Nome do arquivo: {document.original_filename}",
    ]
    if template_block:
        user_parts.append(template_block)
    user_parts.append(
        "Extraia os dados estruturados. Retorne JSON dentro de bloco ```json ... ```."
    )
    user_text = "\n\n".join(user_parts)

    output_data, tokens_in, tokens_out, cost = await _invoke_with_validation(
        spec=spec,
        system_text=system_text,
        user_text=user_text,
        ctx=ctx,
        db=db,
        # No tools for extractor.
        tools_override=[],
    )

    # Persist on the document row.
    document.ai_extraction = output_data
    document.ai_model_used = spec.preferred_model
    document.ai_prompt_version = prompt.full_id
    await db.flush()

    return AgentRunResult(
        output_data=output_data,
        output_schema_name=spec.output_schema.__name__,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        cost_brl=cost,
        prompt_full_id=prompt.full_id,
    )


async def _render_template_block(
    db: AsyncSession,
    *,
    tenant_id: Any,
    doc_type: str,
    template_id: Any = None,
) -> str:
    """Build a guidance block from a CreditDocumentTemplate (when applicable).

    Resolution order:
    1. If `template_id` is provided and belongs to the tenant — use it.
    2. Otherwise no template — return empty (free-form extraction).

    We deliberately DO NOT auto-pick a template here; tenant explicitly opts
    in by linking a template at upload time. Avoids surprises.
    """
    if template_id is None:
        return ""

    from sqlalchemy import or_, select

    from app.modules.credito.models.document_template import CreditDocumentTemplate

    template = (
        await db.execute(
            select(CreditDocumentTemplate).where(
                CreditDocumentTemplate.id == template_id,
                or_(
                    CreditDocumentTemplate.tenant_id == tenant_id,
                    CreditDocumentTemplate.tenant_id.is_(None),
                ),
                CreditDocumentTemplate.active.is_(True),
            )
        )
    ).scalar_one_or_none()

    if template is None:
        return ""

    parts: list[str] = [f"## Template aplicado: {template.name}"]
    if template.description:
        parts.append(template.description)
    if template.instructions:
        parts.append("**Instrucoes do template:**")
        parts.append(template.instructions)
    if template.fields_schema:
        try:
            parts.append("**Campos esperados:**")
            parts.append("```json")
            parts.append(json.dumps(template.fields_schema, ensure_ascii=False, indent=2))
            parts.append("```")
        except (TypeError, ValueError):
            pass
    return "\n\n".join(parts)


# ─── Internals ────────────────────────────────────────────────────────────


@contextmanager
def _ensure_anthropic_api_key(api_key: str) -> Iterator[None]:
    """Garante que ANTHROPIC_API_KEY esta no env enquanto o claude-agent-sdk
    roda. O SDK e wrapper do CLI Claude Code que herda env vars do processo
    Python — sem a key no env, ele tenta OAuth e falha com 'Failed to start
    Claude Code'.

    Restaura o valor anterior ao sair (defensivo em concorrencia, embora
    hoje todas as credenciais Anthropic sejam globais — CLAUDE.md §19.3).
    """
    prev = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = api_key
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = prev


async def _invoke_with_validation(
    *,
    spec: SpecialistAgentSpec,
    system_text: str,
    user_text: str,
    ctx: NodeContext,
    db: AsyncSession,
    tools_override: list | None = None,
) -> tuple[dict[str, Any], int, int, Decimal]:
    """Invoke the agent and validate output, retrying once on schema failure."""
    from claude_agent_sdk import (  # type: ignore[import-not-found]
        ClaudeAgentOptions,
        ResultMessage,
        create_sdk_mcp_server,
        query,
    )

    # Resolver credencial Anthropic ativa antes de invocar o SDK.
    # Sem ANTHROPIC_API_KEY no env, o CLI bundled tenta OAuth e falha.
    try:
        credential = await get_active_anthropic_credential(db)
    except CredentialNotFoundError as e:
        raise RuntimeError(
            "Agente IA nao pode rodar: nenhuma credencial Anthropic ativa "
            "esta cadastrada. Cadastre uma em /admin/ia/providers (mantenedor)."
        ) from e

    tools = (
        tools_override
        if tools_override is not None
        else _build_tools_for_agent(spec, ctx.tenant_id, ctx.trigger_data.get("dossier_id"), db)
    )

    options_kwargs: dict[str, Any] = {
        "model": spec.preferred_model,
        "system_prompt": system_text,
    }

    if tools:
        mcp_server = create_sdk_mcp_server(
            name=f"agent_{spec.name}",
            version="1.0.0",
            tools=tools,
        )
        options_kwargs["mcp_servers"] = {f"agent_{spec.name}": mcp_server}
        options_kwargs["allowed_tools"] = [
            f"mcp__agent_{spec.name}__{t.name}" for t in tools  # type: ignore[attr-defined]
        ]

    options = ClaudeAgentOptions(**options_kwargs)

    with _ensure_anthropic_api_key(credential.api_key):
        raw_text, tokens_in, tokens_out, cost = await _call_query(
            prompt=user_text,
            options=options,
            query_fn=query,
            ResultMessage=ResultMessage,
        )

    # Try to parse + validate.
    try:
        parsed = _extract_json_object(raw_text)
        validated = spec.output_schema.model_validate(parsed)
        return validated.model_dump(mode="json"), tokens_in, tokens_out, cost
    except (ValidationError, ValueError, json.JSONDecodeError) as e:
        logger.warning(
            "Agent %s produced invalid output, retrying once: %s",
            spec.name,
            e,
        )

    # One retry with correction prompt.
    correction_prompt = (
        user_text
        + "\n\nIMPORTANTE: a resposta anterior nao validou contra o schema. "
        "Erro: "
        + str(e)[:500]
        + "\n\nProduza apenas um objeto JSON correto dentro de ```json ... ```."
    )
    options2 = ClaudeAgentOptions(**options_kwargs)
    with _ensure_anthropic_api_key(credential.api_key):
        raw_text2, tin2, tout2, cost2 = await _call_query(
            prompt=correction_prompt,
            options=options2,
            query_fn=query,
            ResultMessage=ResultMessage,
        )

    try:
        parsed2 = _extract_json_object(raw_text2)
        validated2 = spec.output_schema.model_validate(parsed2)
    except (ValidationError, ValueError, json.JSONDecodeError) as e2:
        raise ValueError(
            f"Agente {spec.name}: validacao falhou apos retry. Erro final: {e2}"
        ) from e2

    return (
        validated2.model_dump(mode="json"),
        tokens_in + tin2,
        tokens_out + tout2,
        cost + cost2,
    )


async def _call_query(
    *,
    prompt: str,
    options: Any,
    query_fn: Any,
    ResultMessage: Any,
) -> tuple[str, int, int, Decimal]:
    """Drive the Agent SDK query and return final text + token usage.

    The SDK streams messages of multiple types; we accumulate the result
    text on `ResultMessage(subtype='success')` events.
    """
    final_text = ""
    tokens_in = 0
    tokens_out = 0
    cost = Decimal("0")

    try:
        message_iterator = query_fn(prompt=prompt, options=options)
    except Exception as exc:
        # Captura erros sincronos na construcao do iterator.
        logger.exception(
            "claude-agent-sdk query() raised on construction: %s (%r)",
            exc,
            exc,
        )
        raise

    async for message in _iter_with_logging(message_iterator):
        if isinstance(message, ResultMessage):
            # The result message exposes the final text + usage.
            if hasattr(message, "result") and message.result:
                final_text = str(message.result)
            # Best-effort usage capture; SDK exposes it on .usage when present.
            usage = getattr(message, "usage", None)
            if usage:
                tokens_in += int(getattr(usage, "input_tokens", 0) or 0)
                tokens_out += int(getattr(usage, "output_tokens", 0) or 0)
            total_cost = getattr(message, "total_cost_usd", None)
            if total_cost is not None:
                # USD → BRL conversion is approximate at this layer; the
                # billing layer converts properly via current FX rate.
                cost += Decimal(str(total_cost))
            break

    if not final_text:
        raise ValueError("Agente nao produziu texto de resposta (sem ResultMessage de sucesso).")
    return final_text, tokens_in, tokens_out, cost


async def _iter_with_logging(iterator: Any) -> Any:
    """Wrap async iterator pra logar exceptions com cause chain completa.

    Sem isso, erros do SDK chegam como mensagens vagas (`Failed to start
    Claude Code:`) sem tracking do que de fato falhou. Aqui logamos a
    cadeia inteira (cause/context) com traceback antes de propagar.
    """
    try:
        async for item in iterator:
            yield item
    except Exception as exc:
        # Coleta cadeia de causes pra identificar a raiz.
        chain: list[str] = []
        current: BaseException | None = exc
        while current is not None:
            chain.append(f"{type(current).__name__}: {current!r}")
            current = current.__cause__ or current.__context__
        logger.exception(
            "claude-agent-sdk query() FAILED — cause chain:\n  %s",
            "\n  ".join(chain),
        )
        raise
