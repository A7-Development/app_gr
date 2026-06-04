"""Deteccao do banco cobrador pelo conteudo do arquivo CNAB.

Os arquivos de retorno de varios bancos chegam misturados numa unica pasta
(inbox). O banco/layout se descobre lendo o HEADER CNAB (registro 0), nao o
nome do arquivo. No CNAB400 de cobranca o codigo do banco fica em 77-79 e o
nome em 80-94.

Adicionar banco = +1 entrada em `_POR_CODIGO` + o parser do banco em
`etl._LAYOUTS`. Detectar um banco sem parser ainda implementado faz o arquivo
pousar no bronze e ser contado como "sem parser" (nao vira wh_boleto ate o
parser existir).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import SourceType
from app.warehouse.cnab_raw_arquivo import (
    BANCO_BRADESCO,
    BANCO_GRAFENO,
    BANCO_ITAU,
)


@dataclass(frozen=True)
class BancoDetectado:
    banco: str
    layout: str
    source_type: SourceType


# Codigo do banco (header CNAB400, pos 77-79) -> (banco, layout, source_type).
# Grafeno (274) a CONFIRMAR com amostra real -- pode operar sob outro codigo.
_POR_CODIGO: dict[str, BancoDetectado] = {
    "237": BancoDetectado(
        BANCO_BRADESCO, "cnab400_bradesco", SourceType.COBRANCA_BRADESCO
    ),
    "341": BancoDetectado(BANCO_ITAU, "cnab400_itau", SourceType.COBRANCA_ITAU),
    "274": BancoDetectado(
        BANCO_GRAFENO, "cnab400_grafeno", SourceType.COBRANCA_GRAFENO
    ),
}


def detectar_banco(conteudo: str) -> BancoDetectado | None:
    """Identifica o banco pelo header CNAB. None se nao reconhecido."""
    linhas = conteudo.splitlines()
    if not linhas:
        return None
    header = linhas[0]
    if len(header) < 94:
        return None
    codigo = header[76:79].strip()  # pos 77-79 (1-based)
    return _POR_CODIGO.get(codigo)
