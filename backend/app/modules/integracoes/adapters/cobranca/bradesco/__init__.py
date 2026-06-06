"""Adapter Bradesco -- cobranca (CNAB400).

Parser dos arquivos de retorno e remessa + decoder ring de codigo de
ocorrencia. BMP (274) e Vortx (310) reaproveitam o mesmo CNAB400-padrao.
"""

from app.modules.integracoes.adapters.cobranca.bradesco.parser import (
    LAYOUT,
    estado_from_codigo,
    parse_remessa,
    parse_retorno,
)

__all__ = ["LAYOUT", "estado_from_codigo", "parse_remessa", "parse_retorno"]
