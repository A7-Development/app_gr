"""Utilitários de `field_path` para os Contratos de Dados.

Convenção (docs/contratos-de-dados-fontes-externas.md §7.4): ponto para objeto
aninhado (`LegalNature.Activity`), `[]` para array (`Activities[].Code`).

- `extract_by_path(data, path)`: lê o valor de um caminho num payload. Para
  caminhos com `[]`, devolve a LISTA de valores (um por elemento).
- `flatten_paths(data)`: enumera todos os caminhos-folha presentes num payload
  (mesma convenção) — base do detector de campo novo.

Funções puras — sem DB, sem rede. Genéricas (qualquer fonte/dataset).
"""

from __future__ import annotations

from typing import Any


def extract_by_path(data: Any, path: str) -> Any:
    """Lê o valor de `path` em `data`. `[]` → lista de valores por elemento.

    None quando o caminho não existe. Não levanta exceção em shape inesperado.
    """
    return _walk(data, path.split("."))


def _walk(node: Any, tokens: list[str]) -> Any:
    if not tokens:
        return node
    if node is None:
        return None
    tok, rest = tokens[0], tokens[1:]
    if tok.endswith("[]"):
        key = tok[:-2]
        arr = node.get(key) if isinstance(node, dict) else None
        if not isinstance(arr, list):
            return None
        return [_walk(el, rest) for el in arr]
    nxt = node.get(tok) if isinstance(node, dict) else None
    return _walk(nxt, rest)


def flatten_paths(data: Any, prefix: str = "") -> set[str]:
    """Enumera os caminhos-folha presentes em `data` (convenção ponto + []).

    Arrays viram `prefixo[]` + os campos dos elementos. Só folhas (escalares)
    entram — contêineres intermediários não.
    """
    paths: set[str] = set()
    if isinstance(data, dict):
        for k, v in data.items():
            p = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict | list):
                paths |= flatten_paths(v, p)
            else:
                paths.add(p)
    elif isinstance(data, list):
        ap = f"{prefix}[]"
        if not data:
            paths.add(ap)
        for el in data:
            if isinstance(el, dict | list):
                paths |= flatten_paths(el, ap)
            else:
                paths.add(ap)
    elif prefix:
        paths.add(prefix)
    return paths
