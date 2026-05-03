"""Specialist Agent runtime — invoca Claude via Anthropic Messages API.

Migrado de `claude-agent-sdk` (subprocess do CLI) para o SDK oficial
`anthropic` em 2026-05-02. Razao:
    - subprocess do Claude Code CLI exige `ProactorEventLoop` no Windows;
      backends que usam `SelectorEventLoop` (compat asyncpg legacy)
      quebram com `NotImplementedError` em `_make_subprocess_transport`.
    - HTTP direto e ~10x mais rapido por chamada (sem spawn) e habilita
      prompt caching nativo + batch API + vision.

Fluxo por invocacao:
    1. Resolve prompt do `ai_prompt` (versionado, editavel sem deploy).
    2. Renderiza com contexto (outputs anteriores + dados do dossie).
    3. Cria lista de `AgentTool` (tenant-scoped via closure).
    4. Chama `messages.create()` com `tools=[...]` no Messages API.
    5. Loop de tool execution: enquanto `stop_reason == "tool_use"`,
       executa cada tool requisitado e devolve `tool_result` ate o
       modelo encerrar (`end_turn`).
    6. Captura uso (input/output/cache tokens) pra `ai_usage_event`.
    7. Extrai JSON do texto final, valida com `output_schema` Pydantic;
       retry-com-correcao 1x em caso de falha de schema.
    8. Retorna `AgentRunResult`.

Esta camada e separada do adapter LLM "puro" (`adapters/llm/anthropic/`)
porque agentes especialistas tem loop com tools + JSON validation,
diferente de chat simples.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from anthropic import APIStatusError as AnthropicAPIError  # type: ignore[no-redef]
from anthropic import AsyncAnthropic
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
from app.shared.agents.model_resolver import ResolvedModels, resolve_models_for_agent
from app.shared.agents.tools._base import AgentTool
from app.shared.ai.prompts import repository as prompt_repo

if TYPE_CHECKING:
    from app.shared.workflow.nodes._base import NodeContext

logger = logging.getLogger(__name__)

# Safety cap pro tool execution loop. Cada agente especialista tem 1-3
# tools relevantes; 12 iteracoes deixa folga sem permitir loop infinito.
_MAX_TOOL_ITERATIONS = 12


@dataclass(slots=True)
class AgentRunResult:
    """Outcome of a Specialist Agent run."""

    output_data: dict[str, Any]      # parsed + validated agent output
    output_schema_name: str          # e.g. 'SocialContractAnalysis'
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cache_read: int = 0
    tokens_cache_creation: int = 0
    cost_brl: Decimal = Decimal("0")
    prompt_full_id: str = ""         # 'agent.social_contract@v1'


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
) -> list[AgentTool]:
    """Instantiate AgentTools for this agent based on `spec.tools`.

    The factories close over `(tenant_id, dossier_id, db)` so each
    handler queries with the right scope without trusting agent-supplied IDs.
    """
    from app.shared.agents.tools.document_tools import make_document_tools
    from app.shared.agents.tools.dossier_tools import make_dossier_tools
    from app.shared.agents.tools.reference_tools import make_reference_tools

    selected: list[AgentTool] = []
    requested = set(spec.tools)

    if requested & {TOOL_DOSSIER_READ, TOOL_DOSSIER_FLAG, TOOL_DOSSIER_SAVE}:
        for t in make_dossier_tools(tenant_id, dossier_id, db):
            if t.name in requested:
                selected.append(t)

    if requested & {TOOL_DOC_GET, TOOL_DOC_LIST}:
        for t in make_document_tools(tenant_id, dossier_id, db):
            if t.name in requested:
                selected.append(t)

    if requested & {TOOL_REF_COMPARE, TOOL_REF_CALC}:
        for t in make_reference_tools(tenant_id, dossier_id, db):
            if t.name in requested:
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


# ─── Main entry points ────────────────────────────────────────────────────


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

    output_data, usage, _resolved = await _invoke_with_validation(
        spec=spec,
        system_text=system_text,
        user_text=user_text,
        ctx=ctx,
        db=db,
    )

    return AgentRunResult(
        output_data=output_data,
        output_schema_name=spec.output_schema.__name__,
        tokens_input=usage.tokens_input,
        tokens_output=usage.tokens_output,
        tokens_cache_read=usage.tokens_cache_read,
        tokens_cache_creation=usage.tokens_cache_creation,
        cost_brl=Decimal("0"),  # billing layer computes via FX rate
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
    `template_id` is passed, the template's `instructions` and
    `fields_schema` are injected into the user prompt.

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
        prompt = await prompt_repo.resolve(db, name=spec.prompt_name)

    rendered = prompt.render(context={"page": "credito.documento", "period": "", "filters": ""})
    system_text = "\n\n".join(
        block.text for msg in rendered if msg.role == "system" for block in msg.content
    )

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

    output_data, usage, resolved = await _invoke_with_validation(
        spec=spec,
        system_text=system_text,
        user_text=user_text,
        ctx=ctx,
        db=db,
        tools_override=[],  # extractor nao usa tools
    )

    document.ai_extraction = output_data
    document.ai_model_used = resolved.model
    document.ai_prompt_version = prompt.full_id
    await db.flush()

    return AgentRunResult(
        output_data=output_data,
        output_schema_name=spec.output_schema.__name__,
        tokens_input=usage.tokens_input,
        tokens_output=usage.tokens_output,
        tokens_cache_read=usage.tokens_cache_read,
        tokens_cache_creation=usage.tokens_cache_creation,
        cost_brl=Decimal("0"),
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

    Resolution: if `template_id` is provided and belongs to the tenant
    (or is a Strata starter template), use it. Otherwise return empty.
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


@dataclass(slots=True)
class _Usage:
    """Token counts acumulados ao longo do tool loop."""

    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cache_read: int = 0
    tokens_cache_creation: int = 0

    def add(self, response_usage: Any) -> None:
        """Acumula a partir de um `Usage` retornado pelo SDK."""
        if response_usage is None:
            return
        self.tokens_input += int(getattr(response_usage, "input_tokens", 0) or 0)
        self.tokens_output += int(getattr(response_usage, "output_tokens", 0) or 0)
        self.tokens_cache_read += int(
            getattr(response_usage, "cache_read_input_tokens", 0) or 0
        )
        self.tokens_cache_creation += int(
            getattr(response_usage, "cache_creation_input_tokens", 0) or 0
        )


async def _invoke_with_validation(
    *,
    spec: SpecialistAgentSpec,
    system_text: str,
    user_text: str,
    ctx: NodeContext,
    db: AsyncSession,
    tools_override: list[AgentTool] | None = None,
) -> tuple[dict[str, Any], _Usage, ResolvedModels]:
    """Invoke the agent and validate output, retrying once on schema failure.

    Implementacao via Anthropic Messages API direta (sem subprocess).
    Resolve o modelo a usar via `agent_config` (DB) com fallback no
    catalog default — permite ao mantenedor trocar modelo sem deploy.
    """
    # Resolve credencial Anthropic ativa.
    try:
        credential = await get_active_anthropic_credential(db)
    except CredentialNotFoundError as e:
        raise RuntimeError(
            "Agente IA nao pode rodar: nenhuma credencial Anthropic ativa "
            "esta cadastrada. Cadastre uma em /admin/ia/providers (mantenedor)."
        ) from e

    # Resolve modelo via DB override (com fallback ao catalog default).
    resolved = await resolve_models_for_agent(db, spec)

    tools = (
        tools_override
        if tools_override is not None
        else _build_tools_for_agent(
            spec, ctx.tenant_id, ctx.trigger_data.get("dossier_id"), db
        )
    )

    client = AsyncAnthropic(api_key=credential.api_key)
    try:
        # Primeira tentativa.
        raw_text, usage = await _run_tool_loop(
            client=client,
            spec=spec,
            model=resolved.model,
            fallback_model=resolved.fallback_model,
            system_text=system_text,
            user_text=user_text,
            tools=tools,
        )

        try:
            parsed = _extract_json_object(raw_text)
            validated = spec.output_schema.model_validate(parsed)
            return validated.model_dump(mode="json"), usage, resolved
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            logger.warning(
                "Agent %s produced invalid output, retrying once: %s",
                spec.name,
                e,
            )
            first_error = e

        # Retry com prompt de correcao.
        correction_prompt = (
            user_text
            + "\n\nIMPORTANTE: a resposta anterior nao validou contra o schema. "
            "Erro: "
            + str(first_error)[:500]
            + "\n\nProduza apenas um objeto JSON correto dentro de ```json ... ```."
        )
        raw_text2, usage2 = await _run_tool_loop(
            client=client,
            spec=spec,
            model=resolved.model,
            fallback_model=resolved.fallback_model,
            system_text=system_text,
            user_text=correction_prompt,
            tools=tools,
        )

        # Acumula tokens das duas chamadas.
        usage.tokens_input += usage2.tokens_input
        usage.tokens_output += usage2.tokens_output
        usage.tokens_cache_read += usage2.tokens_cache_read
        usage.tokens_cache_creation += usage2.tokens_cache_creation

        try:
            parsed2 = _extract_json_object(raw_text2)
            validated2 = spec.output_schema.model_validate(parsed2)
        except (ValidationError, ValueError, json.JSONDecodeError) as e2:
            raise ValueError(
                f"Agente {spec.name}: validacao falhou apos retry. "
                f"Erro final: {e2}"
            ) from e2

        return validated2.model_dump(mode="json"), usage, resolved
    finally:
        await client.close()


async def _run_tool_loop(
    *,
    client: AsyncAnthropic,
    spec: SpecialistAgentSpec,
    model: str,
    fallback_model: str | None,
    system_text: str,
    user_text: str,
    tools: list[AgentTool],
) -> tuple[str, _Usage]:
    """Roda o loop tool_use ate o modelo encerrar com texto final.

    `model` e `fallback_model` vem ja resolvidos do DB override
    (via `resolve_models_for_agent`); o caller nao deve mais ler
    `spec.preferred_model` direto.

    Retorna o texto da ultima resposta (sem blocos `tool_use`) + usage
    acumulado.
    """
    # System prompt como bloco com cache_control — primeiro request cria
    # o cache; tool-loop subsequentes acertam (read).
    system_blocks = [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    tool_definitions = [t.to_api_definition() for t in tools] if tools else None
    tool_dispatch: dict[str, AgentTool] = {t.name: t for t in tools}

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_text},
    ]

    usage = _Usage()
    max_tokens = max(spec.thinking_budget_tokens + 4000, 4000)

    last_text_response = ""
    for iteration in range(_MAX_TOOL_ITERATIONS):
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": messages,
        }
        if tool_definitions:
            kwargs["tools"] = tool_definitions

        try:
            response = await client.messages.create(**kwargs)
        except AnthropicAPIError as exc:
            # Fallback para o modelo secundario se configurado.
            if fallback_model and fallback_model != model:
                logger.warning(
                    "Agent %s primary model %s falhou (%s); tentando fallback %s",
                    spec.name,
                    model,
                    exc,
                    fallback_model,
                )
                kwargs["model"] = fallback_model
                response = await client.messages.create(**kwargs)
            else:
                raise

        usage.add(response.usage)

        # Se o modelo terminou (end_turn / max_tokens / stop_sequence),
        # extrai texto final e sai do loop.
        if response.stop_reason in ("end_turn", "max_tokens", "stop_sequence"):
            last_text_response = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return last_text_response, usage

        if response.stop_reason != "tool_use":
            # Stop reason inesperado — registra e sai com o que tem.
            logger.warning(
                "Agent %s stop_reason inesperado: %s (iter %d)",
                spec.name,
                response.stop_reason,
                iteration,
            )
            last_text_response = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return last_text_response, usage

        # tool_use: append assistant turn + executa tools + append tool_results.
        # Echo do `response.content` direto preserva qualquer thinking block
        # ou text block que o modelo emitiu.
        messages.append(
            {
                "role": "assistant",
                "content": [block.model_dump() for block in response.content],
            }
        )

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool = tool_dispatch.get(block.name)
            if tool is None:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": (
                            f"Erro: tool '{block.name}' nao registrada. "
                            f"Disponiveis: {sorted(tool_dispatch.keys())}."
                        ),
                        "is_error": True,
                    }
                )
                continue

            try:
                result_text = await tool.handler(dict(block.input or {}))
            except Exception as exc:
                logger.exception(
                    "Tool %s falhou no agente %s: %s", block.name, spec.name, exc
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Erro ao executar {block.name}: {exc}",
                        "is_error": True,
                    }
                )
                continue

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    # Esgotou _MAX_TOOL_ITERATIONS — devolve o que tiver de texto.
    logger.warning(
        "Agent %s atingiu %d iteracoes de tool_use sem encerrar.",
        spec.name,
        _MAX_TOOL_ITERATIONS,
    )
    return last_text_response, usage
