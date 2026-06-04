"""Adapter Bradesco -- cobranca (CNAB400).

Parser do arquivo de retorno + decoder ring de codigo de ocorrencia. Remessa
(parse semantico) fica para a fase de enriquecimento de Obs.
"""

from app.modules.integracoes.adapters.cobranca.bradesco.parser import (
    LAYOUT,
    estado_from_codigo,
    parse_retorno,
)

__all__ = ["LAYOUT", "estado_from_codigo", "parse_retorno"]
