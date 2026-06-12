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

import base64
import dataclasses
import json
import logging
import mimetypes
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from anthropic import APIStatusError as AnthropicAPIError  # type: ignore[no-redef]
from anthropic import AsyncAnthropic
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

# Import do pacote `app.agentic.tools` carrega `_base.AgentTool` E forca
# os decorators `@register_tool` nas tools de cada subdir (CLAUDE.md §19.0).
# Sem este import o `ToolRegistry` fica vazio no momento em que
# `_build_tools_for_agent` consulta.
import app.agentic.tools  # noqa: F401
from app.agentic._scope import ScopedContext
from app.agentic.agents import AgentRegistry, ResolvedAgent, compose_system_text
from app.agentic.engine.catalog import (
    SpecialistAgentSpec,
)
from app.agentic.engine.model_resolver import ResolvedModels, resolve_models_for_agent
from app.agentic.engine.prompts import repository as prompt_repo
from app.agentic.memory import AnalysisSession
from app.agentic.playbooks.services.resolver import resolve_templates
from app.agentic.tools._base import AgentTool
from app.agentic.tools.registry import ToolRegistry
from app.core.config import get_settings
from app.core.enums import Module, Permission
from app.modules.integracoes.adapters.llm.anthropic.config import (
    CredentialNotFoundError,
    get_active_anthropic_credential,
)

if TYPE_CHECKING:
    from app.agentic.playbooks.nodes._base import NodeContext

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
    model_used: str = ""             # modelo resolvido em runtime (override
                                     # chain DB > agent_config > catalog).
                                     # Pode ser o fallback se o primary falhou.
                                     # Usar pra audit + UI honesta.
    # ─── Cache + audit (run_standalone_agent) ─────────────────────────────
    from_cache: bool = False         # True = output veio de execucao previa,
                                     # NAO houve chamada nova ao LLM. Custo = 0.
    analysis_run_id: Any = None      # UUID da row em agent_analysis_run (pra
                                     # audit/UI). None quando rodou via
                                     # run_specialist_agent legado.
    cache_age_seconds: int = 0       # idade do cache em segundos quando hit.
    duration_ms: int = 0             # duracao real do invoke em ms; 0 quando hit.


# ─── Prompt rendering helpers ─────────────────────────────────────────────


def _render_context_for_prompt(
    ctx: NodeContext,
    *,
    spec: SpecialistAgentSpec | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Build the user-prompt context block.

    Two code paths:

    - **Structured path** (used when `spec.inputs` is non-empty AND
      `config.input_bindings` declares refs for those slots): resolves each
      slot via the engine's template resolver and emits a clean named JSON
      block. No truncation, only declared fields. The agent always knows
      what it is reading.

    - **Legacy path** (fallback when `spec` is None, `spec.inputs` is empty,
      or no bindings are declared): dumps every `previous_outputs` entry
      as JSON, truncated at 2000 chars/node. Mid-field truncation is a
      known issue of this path — the structured path is the migration target.
    """
    lines: list[str] = []
    lines.append("[Contexto do dossie]")
    lines.append(f"Dossier ID: {ctx.trigger_data.get('dossier_id', '?')}")

    if ctx.trigger_data.get("target_cnpj"):
        lines.append(f"CNPJ alvo: {ctx.trigger_data['target_cnpj']}")
    if ctx.trigger_data.get("target_name"):
        lines.append(f"Empresa alvo: {ctx.trigger_data['target_name']}")

    lines.append("")

    if spec is not None and spec.inputs:
        bindings: dict[str, Any] = (
            (config or {}).get("input_bindings") or {}
            if isinstance(config, dict)
            else {}
        )
        resolved = _resolve_input_bindings(spec, bindings, ctx)
        lines.append("[Dados disponiveis para sua analise]")
        lines.append(json.dumps(resolved, ensure_ascii=False, indent=2))
        # Scratchpad cross-agent (F1.C2): observacoes de agentes anteriores
        # da mesma analise. Vazio quando session ausente ou primeiro agente.
        scratchpad_text = _render_scratchpad(ctx)
        if scratchpad_text:
            lines.append("")
            lines.append(scratchpad_text)
        return "\n".join(lines)

    # Legacy fallback: full dump, truncated.
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
    scratchpad_text = _render_scratchpad(ctx)
    if scratchpad_text:
        lines.append("")
        lines.append(scratchpad_text)
    return "\n".join(lines)


def _render_scratchpad(ctx: NodeContext) -> str:
    """Return rendered scratchpad block when session has cross-agent notes.

    Empty string when no session, or session.scratchpad is empty. The block
    starts with a header `[Observacoes de agentes anteriores nesta analise]`
    making it discoverable for the model without inflating the prompt when
    irrelevant.
    """
    session = getattr(ctx, "session", None)
    if session is None:
        return ""
    return session.scratchpad.render()


def _resolve_input_bindings(
    spec: SpecialistAgentSpec,
    bindings: dict[str, Any],
    ctx: NodeContext,
) -> dict[str, Any]:
    """Resolve each declared input slot against the run context.

    Returns a dict { input_name: resolved_value } in the order the agent
    declared its inputs (Python 3.7+ dict insertion order). Unbound
    OPTIONAL slots resolve to None; unbound REQUIRED slots also resolve
    to None — the graph validator should have caught the missing binding
    earlier. Bindings pointing to missing upstream paths resolve to None
    via the resolver.
    """
    resolve_ctx: dict[str, Any] = {
        "trigger": ctx.trigger_data or {},
        "node": ctx.previous_outputs or {},
    }
    out: dict[str, Any] = {}
    for slot in spec.inputs:
        binding = bindings.get(slot.name)
        if not isinstance(binding, str) or not binding.strip():
            out[slot.name] = None
            continue
        out[slot.name] = resolve_templates("{{" + binding + "}}", resolve_ctx)
    return out


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
    scope: ScopedContext,
    *,
    allowed_tools: tuple[str, ...] | list[str] | None = None,
    cross_module: bool = False,
) -> list[AgentTool]:
    """Resolve tools via ToolRegistry filtrado por scope + allowed list.

    Substituiu as factories closure-based em F2.a (CLAUDE.md §19.0). Tools
    sao registradas dinamicamente via `@register_tool` no momento da
    importacao de `app.agentic.tools.*`. Adicionar tool nova = novo
    arquivo com decorator, zero mudanca aqui.

    `allowed_tools`:
        None  -> usa o default do CATALOG (`spec.tools`) — agentes curados
                 em codigo. [] -> agente sem tools. [...] -> override da UI
                 (editavel em `agent_definition.allowed_tools` sem deploy).

    `cross_module` (CLAUDE.md §11.3 / §19): quando False (default da
    AgentDefinition), o `get_available` aplica o filtro de modulo — o
    agente so enxerga tools do proprio modulo. Cruzar modulo exige
    `cross_module=True` explicito na definicao + auditoria. O caller passa
    `resolved.cross_module`; agentes legados sem AgentDefinition (resolved
    is None: extracao de documento, testes) mantem `cross_module=True` no
    call site por back-compat — eram invocados por nodes ja autorizados.
    """
    effective = list(allowed_tools) if allowed_tools is not None else list(spec.tools)
    return ToolRegistry.get_available(
        scope,
        allowed=effective,
        cross_module=cross_module,
    )


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
    session: AnalysisSession | None = None,
) -> AgentRunResult:
    """Run a Specialist Agent and return its validated output.

    F2.b.2: Resolve a definicao do agente via `AgentRegistry.get()`
    (DB-first, CATALOG fallback). O `system_text` enviado ao LLM e
    composto com XML tags + markdown:

        <persona>{role_block}</persona>
        <expertise name="X">{knowledge_text}</expertise>
        <task>{prompt.system_text}</task>

    Quando agent_definition_active nao tem entry pra este `spec.name`
    (dev sem migration aplicada, teste, agente novo em codigo), o
    registry cai em fallback CATALOG — persona/expertises ficam vazios
    e o composer omite os blocos correspondentes. Garante backward
    compat: nada quebra.

    `prompt_full_id` no AgentRunResult retorna `audit_version`
    (composto agent+persona+expertises+prompt) — vira
    `decision_log.rule_or_model_version` permitindo audit completo.

    On output schema validation failure, retries once with a correction
    prompt. On second failure, raises ValueError (the workflow node
    will mark FAILED).
    """
    # F2.b.2: scope construido cedo pra alimentar registry; e tambem
    # reaproveitado pelo `_invoke_with_validation` (via ctx).
    from app.core.enums import Module as _Module

    scope_for_registry = ScopedContext(
        tenant_id=ctx.tenant_id,
        empresa_id=None,
        user_id=ctx.initiated_by,
        module=_Module.CREDITO,
        permissions={},
        db=db,
        extras={},
    )

    resolved = await AgentRegistry.get(db, name=spec.name, scope=scope_for_registry)
    prompt = resolved.prompt

    rendered = prompt.render(context={"page": "credito.dossie", "period": "", "filters": ""})
    prompt_system_text = "\n\n".join(
        block.text for msg in rendered if msg.role == "system" for block in msg.content
    )

    # XML-tagged system_text (persona + expertises + task).
    system_text = compose_system_text(
        persona=resolved.persona,
        expertises=resolved.expertises,
        prompt_system_text=prompt_system_text,
        # Auto-injeta o <output_format> derivado do output_schema Pydantic
        # (opcao A, 2026-06-06): prompts nao precisam mais descrever o shape.
        output_schema=spec.output_schema,
    )

    # Inject checklist items defined by the tenant for this agent's section.
    checklist_block = await _render_checklist_block(
        db,
        tenant_id=ctx.tenant_id,
        section_id=spec.section_id,
    )

    # Pull the workflow node's config so we can read `input_bindings` when
    # the agent declares typed `inputs`. When config is unavailable (e.g.
    # the runtime is invoked outside a workflow node), the structured path
    # is bypassed and the legacy fallback runs.
    node_config: dict[str, Any] = getattr(ctx, "node_config", None) or {}
    user_parts = [_render_context_for_prompt(ctx, spec=spec, config=node_config)]
    if checklist_block:
        user_parts.append(checklist_block)
    user_parts.append(
        "Produza a analise no formato JSON definido pelo schema da tarefa. "
        "Inclua o objeto JSON dentro de um bloco ```json ... ```."
    )
    user_text = "\n\n".join(user_parts)

    # F1.C2: instrumenta `session.steps` quando session presente. Rotula
    # cada step pelo identificador curto do agente (ex.: 'credito.financial_analyst@v1').
    agent_full_id = resolved.full_id

    if session is not None:
        session.record_observation(
            agent_full_id=agent_full_id,
            message=f"start {agent_full_id}",
        )

    output_data, usage, resolved_models = await _invoke_with_validation(
        spec=spec,
        system_text=system_text,
        user_text=user_text,
        ctx=ctx,
        db=db,
        resolved=resolved,
        session=session,
        agent_full_id=agent_full_id,
    )

    if session is not None:
        # Auto-anexa um summary do output ao scratchpad para o proximo
        # agente da sessao ler. Truncado em 1500 chars — folga sem
        # explodir tokens em sessions com varios agentes.
        try:
            summary_text = json.dumps(
                output_data, ensure_ascii=False, default=str
            )[:1500]
        except (TypeError, ValueError):
            summary_text = str(output_data)[:1500]
        session.scratchpad.append(agent_name=resolved.raw_name, text=summary_text)
        session.record_scratchpad_write(
            agent_full_id=agent_full_id, text=summary_text
        )
        session.record_observation(
            agent_full_id=agent_full_id,
            message=f"end {agent_full_id}",
        )

    return AgentRunResult(
        output_data=output_data,
        output_schema_name=spec.output_schema.__name__,
        tokens_input=usage.tokens_input,
        tokens_output=usage.tokens_output,
        tokens_cache_read=usage.tokens_cache_read,
        tokens_cache_creation=usage.tokens_cache_creation,
        cost_brl=Decimal("0"),  # billing layer computes via FX rate
        prompt_full_id=resolved.audit_version,
        model_used=resolved_models.model,
    )


def _load_document_content_block(document: Any) -> list[dict[str, Any]]:
    """Carrega o arquivo do documento e monta o bloco de content multimodal.

    Suporta PDF (bloco `document`) e imagens (bloco `image`) — e o que faz o
    Claude Vision realmente "ver" o arquivo enviado. O caminho e resolvido sob
    DOSSIER_STORAGE_ROOT (defense: nao pode escapar do root).
    """
    root = Path(get_settings().DOSSIER_STORAGE_ROOT).resolve()
    rel = (getattr(document, "file_path", "") or "").lstrip("/\\")
    path = (root / rel).resolve()
    if path != root and root not in path.parents:
        raise ValueError("file_path do documento escapa do storage root.")
    if not path.exists():
        raise ValueError(
            f"Arquivo do documento nao encontrado no storage: {document.file_path}"
        )
    data = path.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")
    mime = (
        getattr(document, "mime_type", None)
        or mimetypes.guess_type(str(path))[0]
        or ""
    )
    if mime == "application/pdf" or path.suffix.lower() == ".pdf":
        return [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64,
                },
            }
        ]
    if mime.startswith("image/"):
        return [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            }
        ]
    raise ValueError(
        f"Tipo de arquivo nao suportado p/ extracao multimodal: {mime or path.suffix}"
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

    # Contrato de dados tipado por doc_type (2026-06-11): quando o doc_type
    # tem schema proprio, o runtime troca o DocumentExtraction permissivo
    # pelo schema especifico e auto-injeta o <output_format> derivado dele —
    # mesmo mecanismo dos specialist agents (compose, opcao A 2026-06-06).
    # O prompt extract.<doc_type> passa a ser dono apenas das REGRAS DE
    # LEITURA; editar prompt na UI nunca muda o shape que o codigo consome.
    from app.agentic.agents._compose import render_output_schema_block
    from app.agentic.engine.output_schemas import EXTRACTION_SCHEMA_BY_DOC_TYPE

    typed_schema = EXTRACTION_SCHEMA_BY_DOC_TYPE.get(doc_type)
    if typed_schema is not None:
        spec = dataclasses.replace(spec, output_schema=typed_schema)
        schema_block = render_output_schema_block(typed_schema)
        if schema_block:
            system_text = f"{system_text}\n\n{schema_block}"

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

    # Anexa o arquivo (PDF/imagem) como bloco multimodal — sem isto o agente
    # nao "ve" o documento (a chamada iria so com texto).
    content_blocks = _load_document_content_block(document)

    output_data, usage, resolved_models = await _invoke_with_validation(
        spec=spec,
        system_text=system_text,
        user_text=user_text,
        ctx=ctx,
        db=db,
        tools_override=[],  # extractor nao usa tools
        user_content_blocks=content_blocks,
    )

    document.ai_extraction = output_data
    document.ai_model_used = resolved_models.model
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
        model_used=resolved_models.model,
    )


async def run_standalone_agent(
    *,
    agent_name: str,
    scope: ScopedContext,
    user_context: dict[str, Any] | None = None,
    db: AsyncSession,
    session: AnalysisSession | None = None,
) -> AgentRunResult:
    """Run a specialist agent OUTSIDE the Credito workflow.

    Unlike `run_specialist_agent` (acoplado ao NodeContext do playbook engine
    e a Module.CREDITO hardcoded), este caminho permite invocar qualquer
    agente do CATALOG passando scope + tenant + permissions explicitamente.

    Use para agentes standalone (ex.: `controladoria.analista_variacao_cota`)
    invocados via endpoint REST direto, smoke test, ou job agendado.

    Args:
        agent_name: nome canonico do agente (ex.: 'controladoria.analista_variacao_cota').
            O AgentRegistry strip o prefixo de modulo pra match com CATALOG.
        scope: ScopedContext ja populado pelo caller — tenant_id, user_id,
            module, permissions, extras. Tools/permissions filtram baseado
            nisso.
        user_context: dict de variaveis pra renderizar o user_context_template
            do ai_prompt (ex.: {fundo_nome, data_d0, data_anterior}).
        db: AsyncSession.
        session: AnalysisSession opcional (working memory + step trace).

    Returns:
        AgentRunResult com output validado contra spec.output_schema.
    """
    from app.agentic.analysis_cache import (
        PersistRunArgs,
        hash_inputs,
        lookup_cached,
        persist_run,
    )
    from app.agentic.engine.catalog import CATALOG
    from app.agentic.playbooks.nodes._base import NodeContext

    # Resolve catalog spec — strip prefixo de modulo se houver.
    raw_name = agent_name.split(".", 1)[1] if "." in agent_name else agent_name
    if raw_name not in CATALOG:
        raise ValueError(f"Agente '{raw_name}' nao encontrado em CATALOG.")
    spec = CATALOG[raw_name]

    # Resolve definition (DB-first via AgentRegistry).
    resolved = await AgentRegistry.get(db, name=agent_name, scope=scope)
    prompt = resolved.prompt

    # ─── Cache check ──────────────────────────────────────────────────────
    # Inputs_snapshot = (scope.extras + user_context) — tudo que diferencia
    # uma analise da outra. audit_version vai no hash separadamente (vide
    # hash_inputs) e garante invalidacao auto quando prompt/persona muda.
    inputs_snapshot = {
        "scope_extras": dict(scope.extras),
        "user_context": dict(user_context or {}),
    }
    inputs_hash = hash_inputs(resolved.audit_version, inputs_snapshot)

    cached = await lookup_cached(
        db,
        tenant_id=scope.tenant_id,
        agent_name=agent_name,
        agent_version=resolved.version,
        inputs_hash=inputs_hash,
    )
    if cached is not None:
        logger.info(
            "Cache HIT pra agente '%s' (idade=%ds, run_id=%s) — economia de chamada LLM.",
            agent_name, cached.age_seconds, cached.id,
        )
        return AgentRunResult(
            output_data=cached.output_data,
            output_schema_name=cached.output_schema_name,
            tokens_input=cached.tokens_input,
            tokens_output=cached.tokens_output,
            tokens_cache_read=cached.tokens_cache_read,
            tokens_cache_creation=cached.tokens_cache_creation,
            cost_brl=cached.cost_brl_estimated or Decimal("0"),
            prompt_full_id=cached.audit_version,
            model_used=cached.model_used,
            from_cache=True,
            analysis_run_id=cached.id,
            cache_age_seconds=cached.age_seconds,
        )

    # ─── Cache miss — invoca LLM ──────────────────────────────────────────

    # Renderiza prompt com context. user_context vira variaveis pra
    # {placeholder} em user_context_template do ai_prompt.
    render_context: dict[str, Any] = {
        "page": f"{scope.module.value}.standalone",
        "period": "",
        "filters": "",
    }
    if user_context:
        render_context.update(user_context)
    rendered = prompt.render(context=render_context)

    system_text_raw = "\n\n".join(
        block.text for msg in rendered if msg.role == "system" for block in msg.content
    )
    system_text = compose_system_text(
        persona=resolved.persona,
        expertises=resolved.expertises,
        prompt_system_text=system_text_raw,
        output_schema=spec.output_schema,
    )

    user_text = "\n\n".join(
        block.text for msg in rendered if msg.role == "user" for block in msg.content
    )
    if not user_text:
        # Fallback se ai_prompt nao tem user_context_template.
        user_text = (
            "Produza a analise no formato JSON definido pelo schema da tarefa. "
            "Inclua o objeto JSON dentro de um bloco ```json ... ```."
        )

    # NodeContext sintetico — necessario por causa do contrato existente
    # de `_invoke_with_validation` (acoplado a ctx.tenant_id, ctx.initiated_by,
    # ctx.run_id). Quando esse contrato for limpo, este shim some.
    from uuid import uuid4
    ctx = NodeContext(
        run_id=uuid4(),
        tenant_id=scope.tenant_id,
        node_id="standalone",
        initiated_by=scope.user_id,
        previous_outputs={},
        trigger_data={},
        node_config={},
        session=session,
    )

    agent_full_id = resolved.full_id

    if session is not None:
        session.record_observation(
            agent_full_id=agent_full_id,
            message=f"start {agent_full_id} (standalone)",
        )

    invoke_start_ms = int(time.time() * 1000)
    persist_status = "success"
    persist_error: str | None = None
    output_data: dict[str, Any] | None = None
    usage = None
    resolved_models = None

    try:
        output_data, usage, resolved_models = await _invoke_with_validation(
            spec=spec,
            system_text=system_text,
            user_text=user_text,
            ctx=ctx,
            db=db,
            resolved=resolved,
            session=session,
            agent_full_id=agent_full_id,
            scope_override=scope,  # Bypass do scope hardcoded CREDITO.
        )
    except Exception as e:
        persist_status = "error"
        persist_error = f"{type(e).__name__}: {e}"
        # Persiste o run com status='error' pra audit antes de propagar.
        await persist_run(
            db,
            PersistRunArgs(
                tenant_id=scope.tenant_id,
                agent_name=agent_name,
                agent_version=resolved.version,
                audit_version=resolved.audit_version,
                inputs_hash=inputs_hash,
                inputs_snapshot=inputs_snapshot,
                output_data=None,
                output_schema_name=spec.output_schema.__name__,
                model_used=resolved.model or "",
                tokens_input=0,
                tokens_output=0,
                tokens_cache_read=0,
                tokens_cache_creation=0,
                cost_brl_estimated=None,
                duration_ms=int(time.time() * 1000) - invoke_start_ms,
                status=persist_status,
                error_message=persist_error,
                triggered_by_user_id=scope.user_id,
            ),
        )
        raise

    duration_ms = int(time.time() * 1000) - invoke_start_ms

    # Estimativa de custo em BRL (aproximacao — billing fino fica em layer separado).
    # Sonnet 4.6: $3/M in, $15/M out, $0.30/M cache_read, $3.75/M cache_creation
    # Opus 4.7:   $15/M in, $75/M out, $1.50/M cache_read, $18.75/M cache_creation
    # Como pricing varia por modelo, deixamos billing detalhado pra futuro.
    # Estimativa generica usando Sonnet 4.6 + FX R$ 5.50/USD:
    cost_usd = (
        usage.tokens_input * 3.0
        + usage.tokens_output * 15.0
        + usage.tokens_cache_read * 0.30
        + usage.tokens_cache_creation * 3.75
    ) / 1_000_000
    cost_brl = Decimal(str(round(cost_usd * 5.50, 4)))

    # ─── Persist (cache + audit) ──────────────────────────────────────────
    analysis_run_id = await persist_run(
        db,
        PersistRunArgs(
            tenant_id=scope.tenant_id,
            agent_name=agent_name,
            agent_version=resolved.version,
            audit_version=resolved.audit_version,
            inputs_hash=inputs_hash,
            inputs_snapshot=inputs_snapshot,
            output_data=output_data,
            output_schema_name=spec.output_schema.__name__,
            model_used=resolved_models.model,
            tokens_input=usage.tokens_input,
            tokens_output=usage.tokens_output,
            tokens_cache_read=usage.tokens_cache_read,
            tokens_cache_creation=usage.tokens_cache_creation,
            cost_brl_estimated=cost_brl,
            duration_ms=duration_ms,
            status=persist_status,
            error_message=None,
            triggered_by_user_id=scope.user_id,
        ),
    )
    logger.info(
        "Cache MISS pra agente '%s' — execucao gravada (run_id=%s, cost~R$%.2f, duracao=%dms).",
        agent_name, analysis_run_id, float(cost_brl), duration_ms,
    )

    return AgentRunResult(
        output_data=output_data,
        output_schema_name=spec.output_schema.__name__,
        tokens_input=usage.tokens_input,
        tokens_output=usage.tokens_output,
        tokens_cache_read=usage.tokens_cache_read,
        tokens_cache_creation=usage.tokens_cache_creation,
        cost_brl=cost_brl,
        prompt_full_id=resolved.audit_version,
        model_used=resolved_models.model,
        from_cache=False,
        analysis_run_id=analysis_run_id,
        cache_age_seconds=0,
        duration_ms=duration_ms,
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
    user_content_blocks: list[dict[str, Any]] | None = None,
    resolved: ResolvedAgent | None = None,
    session: AnalysisSession | None = None,
    agent_full_id: str | None = None,
    scope_override: ScopedContext | None = None,
) -> tuple[dict[str, Any], _Usage, ResolvedModels]:
    """Invoke the agent and validate output, retrying once on schema failure.

    Implementacao via Anthropic Messages API direta (sem subprocess).

    Modelo resolvido em ordem de override (F2.b.2):
        1. `resolved.model` (passed by run_specialist_agent via AgentRegistry —
           reflete override em `agent_definition.model`)
        2. `agent_config.model` (via `resolve_models_for_agent` — overrride
           legado pre-F2.b)
        3. `spec.preferred_model` (CATALOG default em codigo)

    Quando `resolved` e None (run_document_extraction, testes), cai pro
    pattern legado (agent_config + CATALOG default) — backward compat.
    """
    # Resolve credencial Anthropic ativa.
    try:
        credential = await get_active_anthropic_credential(db)
    except CredentialNotFoundError as e:
        raise RuntimeError(
            "Agente IA nao pode rodar: nenhuma credencial Anthropic ativa "
            "esta cadastrada. Cadastre uma em /admin/ia/providers (mantenedor)."
        ) from e

    # Modelo: F2.b.2 prefere override do agent_definition, senao usa o
    # caminho legado (agent_config -> CATALOG).
    if resolved is not None:
        resolved_models = ResolvedModels(
            model=resolved.model,
            fallback_model=resolved.fallback_model,
            source="agent_definition",
        )
    else:
        resolved_models = await resolve_models_for_agent(db, spec)

    # Construir ScopedContext a partir do NodeContext (CLAUDE.md §19.0).
    # F2.a: module hardcoded em CREDITO (todos os specialist agents hoje
    # vivem em workflows do Credito); permissions vazias com
    # cross_module=True na chamada do registry. F2.b vai trazer module
    # via AgentDefinition + permissions reais do user invocador.
    # `scope_override` (2026-05-24): permite agentes standalone (fora de
    # workflow Credito) injetarem scope custom com module + permissions
    # + extras adequados (ex.: agente de controladoria com Module.CONTROLADORIA
    # + ua_id em extras).
    if scope_override is not None:
        scope = scope_override
    else:
        # Fallback de invocacao INTERNA de workflow (sem scope_override). A
        # autorizacao do usuario ja aconteceu no trigger do workflow
        # (require_module no endpoint que dispara o dossie); o agente interno
        # e confiavel e so enxerga as tools curadas em `spec.tools` (o filtro
        # `allowed` do registry restringe a isso de qualquer forma). Por isso
        # concede ADMIN em todos os modulos — senao o filtro de permissao do
        # ToolRegistry derruba TODAS as tools (permissions={} -> NONE nao
        # satisfaz READ) e o agente roda sem tool. F2.b trara permissions
        # reais do user via AgentDefinition.
        scope = ScopedContext(
            tenant_id=ctx.tenant_id,
            empresa_id=None,
            user_id=ctx.initiated_by,
            module=Module.CREDITO,
            permissions=dict.fromkeys(Module, Permission.ADMIN),
            db=db,
            extras={
                "dossier_id": ctx.trigger_data.get("dossier_id"),
                "run_id": ctx.run_id,
                "node_id": ctx.node_id,
            },
        )

    tools = (
        tools_override
        if tools_override is not None
        else _build_tools_for_agent(
            spec,
            scope,
            # Override de tools da AgentDefinition (None = usa spec.tools).
            allowed_tools=resolved.allowed_tools if resolved is not None else None,
            # Honra o gate de modulo da definicao; legado (resolved None)
            # mantem o comportamento antigo (cross_module aberto).
            cross_module=resolved.cross_module if resolved is not None else True,
        )
    )

    client = AsyncAnthropic(api_key=credential.api_key)
    try:
        # Primeira tentativa.
        raw_text, usage = await _run_tool_loop(
            client=client,
            spec=spec,
            model=resolved_models.model,
            fallback_model=resolved_models.fallback_model,
            system_text=system_text,
            user_text=user_text,
            tools=tools,
            user_content_blocks=user_content_blocks,
            scope=scope,
            session=session,
            agent_full_id=agent_full_id,
        )

        try:
            parsed = _extract_json_object(raw_text)
            validated = spec.output_schema.model_validate(parsed)
            return validated.model_dump(mode="json"), usage, resolved_models
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
            model=resolved_models.model,
            fallback_model=resolved_models.fallback_model,
            system_text=system_text,
            user_text=correction_prompt,
            tools=tools,
            user_content_blocks=user_content_blocks,
            scope=scope,
            session=session,
            agent_full_id=agent_full_id,
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

        return validated2.model_dump(mode="json"), usage, resolved_models
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
    user_content_blocks: list[dict[str, Any]] | None = None,
    scope: ScopedContext | None = None,
    session: AnalysisSession | None = None,
    agent_full_id: str | None = None,
) -> tuple[str, _Usage]:
    """Roda o loop tool_use ate o modelo encerrar com texto final.

    `model` e `fallback_model` vem ja resolvidos do DB override
    (via `resolve_models_for_agent`); o caller nao deve mais ler
    `spec.preferred_model` direto.

    Quando `session` e passada (F1.C2), cada tool_use/tool_result e
    registrado em `session.steps` (alimenta `AgentLiveStatus` no
    frontend) e tools marcadas `cacheable=True` consultam/inserem
    em `session.step_cache` — repeticao com mesmos args dentro da
    sessao acerta o cache. `agent_full_id` rotula os steps (ex.:
    'credito.financial_analyst@v1').

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

    # Quando ha blocos de documento (extracao multimodal), a primeira mensagem
    # do user vira uma lista [<doc/imagem>, ..., {type:text}] — e como o Claude
    # Vision "ve" o arquivo. Sem blocos, mantem o content como string (texto).
    if user_content_blocks:
        first_user_content: Any = [
            *user_content_blocks,
            {"type": "text", "text": user_text},
        ]
    else:
        first_user_content = user_text
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": first_user_content},
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

        # Narracao "em voz alta": o texto que o modelo escreve ANTES de
        # disparar as tools desta rodada e o raciocinio dele. Registra como
        # step REASONING pra surfacear ao vivo no AgentLiveStatus (via
        # session._on_step). So quando ha session — caminho sem session
        # (testes/single-shot) ignora.
        if session is not None:
            interim_text = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            if interim_text:
                session.record_reasoning(
                    agent_full_id=agent_full_id or spec.name,
                    text=interim_text,
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

            if scope is None:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": (
                            f"Erro: tool '{block.name}' requer ScopedContext mas "
                            "_run_tool_loop foi chamado sem scope. Provavel bug "
                            "no caller — abra issue."
                        ),
                        "is_error": True,
                    }
                )
                continue

            tool_args = dict(block.input or {})
            tool_label = agent_full_id or spec.name

            # Cache check: so tools `cacheable=True` + sessao ativa.
            cached_output: str | None = None
            if session is not None and tool.cacheable:
                cached_output = session.step_cache.get(block.name, tool_args)

            if cached_output is not None:
                # Hit: registra trace e devolve direto, sem invocar handler.
                session.record_tool_use(  # type: ignore[union-attr]
                    agent_full_id=tool_label,
                    tool_name=block.name,
                    input_args=tool_args,
                )
                session.record_tool_result(  # type: ignore[union-attr]
                    agent_full_id=tool_label,
                    tool_name=block.name,
                    output=cached_output,
                    duration_ms=0,
                    from_cache=True,
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": cached_output,
                    }
                )
                continue

            # Miss (ou nao-cacheable, ou sem sessao): registra tool_use e
            # executa handler.
            if session is not None:
                session.record_tool_use(
                    agent_full_id=tool_label,
                    tool_name=block.name,
                    input_args=tool_args,
                )

            tool_started = time.monotonic()
            try:
                result_text = await tool.handler(scope, tool_args)
            except Exception as exc:
                logger.exception(
                    "Tool %s falhou no agente %s: %s", block.name, spec.name, exc
                )
                if session is not None:
                    session.record_error(
                        agent_full_id=tool_label,
                        tool_name=block.name,
                        error=str(exc),
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

            duration_ms = int((time.monotonic() - tool_started) * 1000)
            if session is not None:
                session.record_tool_result(
                    agent_full_id=tool_label,
                    tool_name=block.name,
                    output=result_text,
                    duration_ms=duration_ms,
                    from_cache=False,
                )
                # Insere no cache pos-call quando a tool autorizar.
                if tool.cacheable:
                    session.step_cache.put(block.name, tool_args, result_text)

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
