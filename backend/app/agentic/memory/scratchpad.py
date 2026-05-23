"""Scratchpad — bloco textual cross-agent compartilhado em AnalysisSession.

Quando agente A registra observacao no scratchpad, agente B (na mesma
session) le quando for invocado. E o canal default de cross-agent
memory (CLAUDE.md sec 19.11, D4 hybrid):

    scratchpad     bloco textual auto-injetado no prompt (esta camada)
    remember/recall  tools opcionais para itens estruturados (memory/tools.py)

Cap de tamanho:
    Default 8000 chars no acumulado. Quando excede, derruba entradas
    mais antigas (LRU) — o ultimo a falar e o que o proximo agente ve.
    Cap protege contra "scratchpad explode o prompt" em sessions longas.

Render:
    `render()` produz bloco markdown-friendly pronto pra concatenar
    em user_text. Vazio quando scratchpad nunca foi escrito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# Cap default — folga confortavel pra sessions normais (~10-20 agent
# invocations) sem ocupar tudo do token budget. Override por session se
# precisar.
_DEFAULT_MAX_CHARS = 8000


@dataclass(slots=True, frozen=True)
class ScratchpadEntry:
    """Uma entrada append-only no scratchpad."""

    iso_at: datetime
    agent_name: str
    text: str


@dataclass(slots=True)
class Scratchpad:
    """Cross-agent textual memory dentro de uma AnalysisSession.

    API minima — append + render + is_empty. Mais nao precisa hoje.
    """

    max_chars: int = _DEFAULT_MAX_CHARS
    _entries: list[ScratchpadEntry] = field(default_factory=list)
    _total_chars: int = 0

    def append(self, *, agent_name: str, text: str) -> None:
        """Anexa observacao. Sem-op se text vazio/whitespace.

        Quando passa do `max_chars`, descarta entradas mais antigas
        (FIFO) ate caber. O agente mais recente nunca e descartado
        — mesmo que o texto sozinho exceda o cap (raro), so essa
        entrada fica.
        """
        text = (text or "").strip()
        if not text:
            return

        entry = ScratchpadEntry(
            iso_at=datetime.now(UTC),
            agent_name=agent_name,
            text=text,
        )
        self._entries.append(entry)
        self._total_chars += len(text)

        # Trim FIFO ate caber. Preserva o ultimo (mesmo que sozinho exceda).
        while self._total_chars > self.max_chars and len(self._entries) > 1:
            dropped = self._entries.pop(0)
            self._total_chars -= len(dropped.text)

    def render(self) -> str:
        """Bloco textual pronto pra concatenar em user_text do proximo agente.

        Vazio (string "") quando nunca foi escrito. Header e linhas com
        agent_name prefixado — formato simples, modelos lidam bem.
        """
        if not self._entries:
            return ""

        lines = ["[Observacoes de agentes anteriores nesta analise]"]
        for entry in self._entries:
            lines.append(f"- ({entry.agent_name}) {entry.text}")
        return "\n".join(lines)

    def is_empty(self) -> bool:
        return not self._entries

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def total_chars(self) -> int:
        return self._total_chars

    def snapshot(self) -> list[ScratchpadEntry]:
        """Copia imutavel das entries atuais (uso: persistencia + debugging)."""
        return list(self._entries)
