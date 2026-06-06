"""compose_system_text — system prompt composer com XML tags (CLAUDE.md §19.0).

Anthropic recomenda XML tags pra structured prompts (Claude foi treinado
extensivamente com tags durante RLHF). Markdown rico flui dentro das tags
sem escape — texto editavel via UI continua amigavel pro curador, parser
runtime continua estavel.

Layout final (concatenado com double newline):

    <persona>
    {role_block (markdown)}
    </persona>

    <expertise name="contabilidade.fidc">
    {knowledge_text (markdown)}
    </expertise>

    <expertise name="regulatorio.cmn_4966">
    ...
    </expertise>

    <task>
    {prompt.system_text}
    </task>

O cache_control da Anthropic e aplicado pelo runtime APOS este system_text
(via system_blocks em `_run_tool_loop`). Cache cross-tenant funciona
porque persona + expertises + prompt globais sao identicos por tenant —
so user message diverge.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.shared.ai.models.agent_expertise import AgentExpertise
    from app.shared.ai.models.agent_persona import AgentPersona


def render_output_schema_block(output_schema: Any | None) -> str | None:
    """Bloco <output_format> derivado do output_schema Pydantic do agente.

    Auto-injetado no system prompt (decisao 2026-06-06, opcao A): o runtime
    NAO descrevia o schema, entao a adesao dependia do prompt repetir o
    formato — fragil (o curador podia quebrar o shape ao editar) e duplicado.
    Gerando o JSON Schema a partir da classe Pydantic, o prompt passa a tratar
    SO de julgamento/tom; a estrutura vem daqui, sempre em sincronia com o
    codigo. Idempotente/aditivo: agentes que ainda descrevem o shape no prompt
    so recebem o reforco.

    Returns None quando nao ha schema (ou nao e um BaseModel) — back-compat.
    """
    if output_schema is None or not hasattr(output_schema, "model_json_schema"):
        return None
    schema_json = json.dumps(
        output_schema.model_json_schema(), ensure_ascii=False, indent=2
    )
    return (
        "<output_format>\n"
        "Sua resposta FINAL deve ser SOMENTE um objeto JSON, dentro de um bloco "
        "```json ... ```, que valida EXATAMENTE contra este JSON Schema:\n\n"
        f"{schema_json}\n\n"
        "Regras duras:\n"
        "- Use EXATAMENTE os nomes de campo do schema (nao invente, nao "
        "renomeie, nao abrevie).\n"
        "- Campos `required` sao obrigatorios; so use null onde o tipo permite.\n"
        "- NAO inclua nenhum campo fora do schema.\n"
        "- Se nao houver dados para analisar, AINDA ASSIM preencha TODOS os "
        "campos obrigatorios com valores degenerados coerentes (enums tipo "
        "'indefinida'/'desconhecida'/'baixo', listas vazias, textos curtos "
        "explicando a ausencia).\n"
        "- Retorne SOMENTE o JSON, sem texto fora do bloco ```json ... ```.\n"
        "</output_format>"
    )


def compose_system_text(
    *,
    persona: AgentPersona | None,
    expertises: Sequence[AgentExpertise],
    prompt_system_text: str,
    output_schema: Any | None = None,
) -> str:
    """Monta system_text com XML tags + markdown dentro.

    Args:
        persona: row de `agent_persona` (`role_block` markdown). None = nao
            adicionar bloco <persona>.
        expertises: lista ordenada (order-preserving conforme `expertise_ids`
            do agent_definition) de rows de `agent_expertise`. Vazia = nao
            adicionar blocos <expertise>.
        prompt_system_text: texto resolvido do `ai_prompt` (rendered, sem
            templates pendentes).

    Returns:
        String concatenada com double newline entre blocos. Pronto pra ser
        embrulhado em `{"type":"text","text":..,"cache_control":...}` no
        runtime.
    """
    parts: list[str] = []

    if persona is not None:
        parts.append(f"<persona>\n{persona.role_block.strip()}\n</persona>")

    for exp in expertises:
        # `name` da expertise vai como atributo XML pra facilitar debug
        # visual ("qual expertise produziu essa instrucao?").
        parts.append(
            f'<expertise name="{_escape_xml_attr(exp.name)}">\n'
            f"{exp.knowledge_text.strip()}\n"
            f"</expertise>"
        )

    parts.append(f"<task>\n{prompt_system_text.strip()}\n</task>")

    schema_block = render_output_schema_block(output_schema)
    if schema_block is not None:
        parts.append(schema_block)

    return "\n\n".join(parts)


def _escape_xml_attr(value: str) -> str:
    """Escape minimo para o atributo `name=` em <expertise name="...">.

    Names canonicos seguem `<dominio>.<topico>` (snake_case + dots) — nao
    deveriam carregar caracteres XML perigosos. Esta funcao e defesa em
    profundidade: protege caso UI futura permita nome com `"` / `<` / `>`.
    """
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
