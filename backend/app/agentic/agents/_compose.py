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

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared.ai.models.agent_expertise import AgentExpertise
    from app.shared.ai.models.agent_persona import AgentPersona


def compose_system_text(
    *,
    persona: AgentPersona | None,
    expertises: Sequence[AgentExpertise],
    prompt_system_text: str,
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
