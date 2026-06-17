"""Codigo curto e discreto de agente (traceabilidade na UI).

Derivado DETERMINISTICAMENTE do nome canonico (`modulo.nome_agente`) — nao
precisa de coluna nem migration, e e estavel por familia (todas as versoes
do mesmo nome compartilham o mesmo codigo, pois o nome e a identidade).

Proposito: dar um rotulo curto pra localizar/rastrear o agente sem expor o
nome interno (`controladoria.analista_variacao_cota`) ao usuario final. Ex.:
`AGT-3F9A2C1B`.

Espaco de 8 hex = 4.29 bilhoes; pelo problema do aniversario, a colisao com
~500 agentes fica em ~0,003% (e ~0,3% com 5.000). Se um dia precisar de
garantia formal de unicidade + codigo sequencial, vira coluna em
agent_definition (com migration + assignment na criacao).
"""

from __future__ import annotations

import hashlib

_PREFIX = "AGT-"


def derive_agent_code(name: str) -> str:
    """Codigo curto estavel a partir do nome canonico do agente.

    `derive_agent_code("controladoria.analista_variacao_cota") -> "AGT-XXXXXX"`.
    """
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"{_PREFIX}{digest[:8].upper()}"
