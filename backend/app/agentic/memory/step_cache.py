"""StepCache — memoization de tool calls dentro de uma AnalysisSession.

Cache in-memory por session (escopo curto, vai embora quando session
termina). Chave estavel = sha256(tool_name + sorted_args_json). Quando
agente chama a mesma tool com mesmos args duas vezes na mesma analise,
a segunda chamada acerta o cache em vez de rodar o handler.

Quem decide se a tool e cacheable:
    `AgentTool.cacheable: bool` (decorator `@register_tool(cacheable=True)`).
    Default False. Tools puras (`calc.*`) e leituras com TTL curto
    (`bureau.*` consultas batch) podem ser anotadas. Tools com side
    effect (`dossier.update_*`) ficam False.

Quem consulta/insere:
    Runtime `_run_tool_loop` (C2/Task 5). Este modulo so guarda.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def _stable_key(tool_name: str, args: dict[str, Any]) -> str:
    """Chave estavel independente de ordem de keys no args.

    `sort_keys=True` + `default=str` garante que dict com mesma semantica
    e ordem de keys diferente colidem (correto). `default=str` cobre
    Decimal/UUID/datetime que o LLM as vezes manda como input.
    """
    canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    raw = f"{tool_name}::{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@dataclass(slots=True)
class StepCache:
    """Cache de outputs de tool dentro de uma AnalysisSession.

    Sem TTL — vive enquanto a session vive. Tools com TTL real (ex.:
    valor de IPCA, score Serasa de 24h) devem ser anotadas como
    `cacheable=True` somente quando o TTL natural delas e maior que
    o ciclo tipico de uma analise.
    """

    _entries: dict[str, str] = field(default_factory=dict)
    _hit_count: int = 0
    _miss_count: int = 0

    def get(self, tool_name: str, args: dict[str, Any]) -> str | None:
        """Lookup. Retorna output cacheado ou None. Atualiza contadores."""
        key = _stable_key(tool_name, args)
        cached = self._entries.get(key)
        if cached is None:
            self._miss_count += 1
            return None
        self._hit_count += 1
        return cached

    def put(self, tool_name: str, args: dict[str, Any], output: str) -> None:
        """Armazena output. Sobrescreve silenciosamente se ja existia."""
        key = _stable_key(tool_name, args)
        self._entries[key] = output

    @property
    def hit_count(self) -> int:
        return self._hit_count

    @property
    def miss_count(self) -> int:
        return self._miss_count

    @property
    def size(self) -> int:
        return len(self._entries)
