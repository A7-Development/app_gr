"""Mappers de cobranca: ocorrencias CNAB (bronze) -> wh_boleto (silver)."""

from app.modules.integracoes.adapters.cobranca.mappers.boleto import (
    map_ocorrencias_to_boletos,
)

__all__ = ["map_ocorrencias_to_boletos"]
