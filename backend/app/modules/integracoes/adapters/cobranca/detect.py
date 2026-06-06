"""Deteccao do banco cobrador pelo CONTEUDO do arquivo CNAB (header), nunca
pelo nome do arquivo.

Os arquivos de remessa/retorno de varios bancos chegam misturados numa inbox.
O nome do arquivo so traz um codigo de roteamento (e pode ter typo); a
identidade REAL esta no HEADER CNAB (registro tipo "0"): no CNAB400 de cobranca
o codigo do banco fica em 77-79 e o nome por extenso em 80-94. As mesmas
posicoes valem para remessa e retorno.

Validacao dupla (codigo + nome): se o codigo bater mas o nome por extenso nao
casar com a assinatura esperada, NAO rotulamos (retorna None) -- evita rotular
errado caso um codigo seja reusado por outro emissor. Codigos confirmados
contra header real (2026-06-06):

    237 + "BRADESCO"    -> bradesco
    274 + "BMP"         -> bmp    (Money Plus; ex-"grafeno")
    310 + "VORTX DTVM"  -> vortx  (Vortx DTVM; ex-"grafeno")
    341 + "ITAU"        -> itau

Adicionar banco = +1 entrada em `_POR_CODIGO` + (para virar wh_boleto) o parser
do banco em `etl._LAYOUTS`. Banco detectado sem parser ainda pousa no bronze e
e contado como "sem parser".
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import SourceType
from app.warehouse.cnab_raw_arquivo import (
    BANCO_BMP,
    BANCO_BRADESCO,
    BANCO_ITAU,
    BANCO_VORTX,
)


@dataclass(frozen=True)
class BancoDetectado:
    banco: str
    layout: str
    source_type: SourceType


@dataclass(frozen=True)
class _BancoSpec:
    # Assinatura do nome por extenso (80-94, upper) usada para VALIDAR o codigo.
    nome_sig: str
    det: BancoDetectado


# Codigo do banco (header CNAB400 cobranca, pos 77-79) -> spec.
_POR_CODIGO: dict[str, _BancoSpec] = {
    "237": _BancoSpec(
        "BRADESCO",
        BancoDetectado(BANCO_BRADESCO, "cnab400_bradesco", SourceType.COBRANCA_BRADESCO),
    ),
    "274": _BancoSpec(
        "BMP",
        BancoDetectado(BANCO_BMP, "cnab400_bmp", SourceType.COBRANCA_BMP),
    ),
    "310": _BancoSpec(
        "VORTX",
        BancoDetectado(BANCO_VORTX, "cnab400_vortx", SourceType.COBRANCA_VORTX),
    ),
    "341": _BancoSpec(
        "ITAU",
        BancoDetectado(BANCO_ITAU, "cnab400_itau", SourceType.COBRANCA_ITAU),
    ),
}

# Largura minima da linha para alcancar o nome do banco (pos 80-94).
_HEADER_MIN_WIDTH = 94


def _localizar_header(conteudo: str) -> str | None:
    """Primeiro registro header (tipo '0') largo o suficiente para ler 77-94.

    Robusto a linha em branco / BOM / lixo no inicio do arquivo -- varre ate
    achar o primeiro registro tipo "0" valido em vez de assumir a linha 1.
    `splitlines()` ja remove o CR de fim de linha (arquivos vem com CRLF).
    """
    for linha in conteudo.splitlines():
        if len(linha) >= _HEADER_MIN_WIDTH and linha[0] == "0":
            return linha
    return None


def detectar_banco(conteudo: str) -> BancoDetectado | None:
    """Identifica o banco pelo header CNAB (codigo 77-79 + nome 80-94).

    Vale para remessa e retorno (mesmas posicoes). Retorna None quando o header
    nao e legivel, o codigo nao e conhecido, OU o nome por extenso nao confere
    com o codigo (conflito -> nao rotula errado).
    """
    header = _localizar_header(conteudo)
    if header is None:
        return None
    codigo = header[76:79].strip()        # pos 77-79 (1-based)
    nome = header[79:94].strip().upper()  # pos 80-94 (1-based)
    spec = _POR_CODIGO.get(codigo)
    if spec is None:
        return None
    if spec.nome_sig not in nome:
        return None  # codigo conhecido mas nome diverge -> conflito
    return spec.det
