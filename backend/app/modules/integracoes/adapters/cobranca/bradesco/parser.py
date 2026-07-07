"""Parser Bradesco CNAB400 -- retorno de cobranca.

Layout fixed-width de 400 colunas. Decodifica o registro de detalhe (tipo 1)
em campos nomeados **crus** (sem conversao de tipo -- bronze fiel, CLAUDE.md
13.2) e expoe o decoder ring de codigo de ocorrencia -> estado canonico do
boleto (especificidade Bradesco). O header (tipo 0) carrega a data de
gravacao do arquivo (data de referencia).

Posicoes (1-based, inclusivas) verificadas contra arquivo real em 2026-06-04
(COB-237-0595-96482-...):

    header  data_gravacao       095-100  DDMMAA
    detalhe seu_numero          038-062  controle do participante (nosso DID)
    detalhe nosso_numero        071-082
    detalhe codigo_ocorrencia   109-110
    detalhe data_ocorrencia     111-116  DDMMAA
    detalhe numero_documento    117-126  <- chave de cruzamento com wh_titulo
    detalhe data_vencimento     147-152  DDMMAA
    detalhe valor_titulo        153-165  centavos (zero-padded)
    detalhe banco_pagador       166-168  banco cobrador/recebedor da liquidacao
    detalhe agencia_pagadora    169-173  agencia cobradora/recebedora
    detalhe valor_pago          254-266  centavos (zero-padded)
    detalhe data_credito        296-301  DDMMAA (credito ao beneficiario)

Banco/agencia pagadora e data de credito (verificados contra arquivos reais em
2026-07-07, caso JCL/MFL): preenchidos nas liquidacoes (cod 06/15/17); nos
demais codigos vem zerados/vazios -- a normalizacao (zero -> None) e do decode.
Sao a FONTE PRIMARIA de "onde o boleto foi pago" (Sentinela CNAB): o ERP perde
essa informacao quando a agencia nao existe no cadastro dele.

O parser NAO converte tipos nem aplica vigencia -- isso e do mapper
(`cobranca/mappers/boleto.py`), que le o bronze e monta `wh_boleto`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.warehouse.boleto import ESTADO_ATIVO, ESTADO_BAIXADO, ESTADO_LIQUIDADO

LAYOUT = "cnab400_bradesco"
_LINE_WIDTH = 400

# Registros CNAB400.
_REG_HEADER = "0"
_REG_DETALHE = "1"
_REG_TRAILER = "9"

# Codigo de ocorrencia Bradesco -> estado canonico do boleto. A vigencia (qual
# ocorrencia esta valendo por titulo) e resolvida no mapper; aqui so o de->para
# por codigo. Codigo nao mapeado -> None (mapper decide; nao entra como ativo).
_ESTADO_POR_OCORRENCIA: dict[str, str] = {
    "02": ESTADO_ATIVO,  # Entrada confirmada
    "06": ESTADO_LIQUIDADO,  # Liquidacao
    "15": ESTADO_LIQUIDADO,  # Liquidacao em cartorio
    "17": ESTADO_LIQUIDADO,  # Liquidacao apos baixa / titulo nao registrado
    "09": ESTADO_BAIXADO,  # Baixa simples
    "10": ESTADO_BAIXADO,  # Baixa por ter sido liquidado no banco/correspondente
    "03": ESTADO_BAIXADO,  # Entrada rejeitada (nao virou boleto ativo)
}


def estado_from_codigo(codigo: str | None) -> str | None:
    """Estado canonico do boleto a partir do codigo de ocorrencia Bradesco."""
    if codigo is None:
        return None
    return _ESTADO_POR_OCORRENCIA.get(codigo.strip())


@dataclass(frozen=True)
class OcorrenciaParsed:
    """Um registro de detalhe parseado (campos crus, prontos pro bronze)."""

    linha_num: int
    tipo_registro: str
    payload: dict[str, str]


@dataclass
class RetornoParsed:
    """Resultado do parse de um arquivo de retorno."""

    data_ref_raw: str | None  # DDMMAA do header (data de gravacao)
    ocorrencias: list[OcorrenciaParsed] = field(default_factory=list)


@dataclass
class RemessaParsed:
    """Resultado do parse de um arquivo de remessa (o que ENVIAMOS ao banco)."""

    data_ref_raw: str | None  # DDMMAA do header (data de geracao da remessa)
    ocorrencias: list[OcorrenciaParsed] = field(default_factory=list)


def _slice(line: str, start: int, end: int) -> str:
    """Recorte 1-based inclusivo, com trim de espacos nas pontas."""
    return line[start - 1 : end].strip()


def parse_retorno(texto: str) -> RetornoParsed:
    """Parseia o texto de um arquivo de retorno Bradesco CNAB400.

    Ignora linhas com largura != 400 (defensivo). So registros de detalhe
    (tipo 1) viram ocorrencias; header (0) da a data de referencia; trailer
    (9) e descartado.
    """
    data_ref_raw: str | None = None
    ocorrencias: list[OcorrenciaParsed] = []

    for idx, line in enumerate(texto.splitlines(), start=1):
        if len(line) != _LINE_WIDTH:
            continue
        tipo = line[0]
        if tipo == _REG_HEADER:
            data_ref_raw = _slice(line, 95, 100) or None
        elif tipo == _REG_DETALHE:
            ocorrencias.append(
                OcorrenciaParsed(
                    linha_num=idx,
                    tipo_registro=_REG_DETALHE,
                    payload={
                        "seu_numero": _slice(line, 38, 62),
                        "nosso_numero": _slice(line, 71, 82),
                        "codigo_ocorrencia": _slice(line, 109, 110),
                        "data_ocorrencia": _slice(line, 111, 116),
                        "numero_documento": _slice(line, 117, 126),
                        "data_vencimento": _slice(line, 147, 152),
                        "valor_titulo": _slice(line, 153, 165),
                        "banco_pagador": _slice(line, 166, 168),
                        "agencia_pagadora": _slice(line, 169, 173),
                        "valor_pago": _slice(line, 254, 266),
                        "data_credito": _slice(line, 296, 301),
                    },
                )
            )
        # trailer (9) e demais: ignorados.

    return RetornoParsed(data_ref_raw=data_ref_raw, ocorrencias=ocorrencias)


# ── Remessa (o que enviamos ao banco) ───────────────────────────────────────
# O registro de detalhe da REMESSA tem layout DIFERENTE do retorno (mesmo
# CNAB400, posicoes distintas). Verificado contra os arquivos reais em
# 2026-06-06 (100% dos `documento` 111-120 cruzam wh_titulo; `seu_numero`
# 38-62 = "DID"+titulo_id, a PK do Bitfin embutida):
#
#     header  data_gravacao       095-100  DDMMAA  (data de geracao da remessa)
#     detalhe seu_numero          038-062  controle do participante (DID<id>)
#     detalhe nosso_numero        071-082  (mesmo do retorno -- cruza 14/15)
#     detalhe codigo_ocorrencia   109-110  COMANDO da remessa (01=registro,
#                                          02=baixa, 04=abatimento, 06=alt.venc,
#                                          09=protesto) -- semantica do evento
#     detalhe numero_documento    111-120  <- chave de cruzamento com wh_titulo
#     detalhe data_vencimento     121-126  DDMMAA
#     detalhe valor_titulo        127-139  centavos (zero-padded)
#
# A remessa NAO tem data de ocorrencia por registro (nao houve evento no banco
# ainda -- nos a estamos ENVIANDO). A data do evento "instrucao enviada" e a
# data de geracao do arquivo (header), resolvida no decode via arquivo.data_ref.
# Por isso o payload nao carrega `data_ocorrencia`; as demais chaves espelham o
# retorno para o decode ser uniforme.


def parse_remessa(texto: str) -> RemessaParsed:
    """Parseia o texto de um arquivo de remessa Bradesco/BMP/Vortx CNAB400.

    Mesma mecanica do `parse_retorno` (fixed-width 400, so detalhe tipo 1),
    mas com as posicoes do layout de REMESSA. `codigo_ocorrencia` aqui e o
    COMANDO (01=registro...), nao a ocorrencia de retorno.
    """
    data_ref_raw: str | None = None
    ocorrencias: list[OcorrenciaParsed] = []

    for idx, line in enumerate(texto.splitlines(), start=1):
        if len(line) != _LINE_WIDTH:
            continue
        tipo = line[0]
        if tipo == _REG_HEADER:
            data_ref_raw = _slice(line, 95, 100) or None
        elif tipo == _REG_DETALHE:
            ocorrencias.append(
                OcorrenciaParsed(
                    linha_num=idx,
                    tipo_registro=_REG_DETALHE,
                    payload={
                        "seu_numero": _slice(line, 38, 62),
                        "nosso_numero": _slice(line, 71, 82),
                        "codigo_ocorrencia": _slice(line, 109, 110),
                        "numero_documento": _slice(line, 111, 120),
                        "data_vencimento": _slice(line, 121, 126),
                        "valor_titulo": _slice(line, 127, 139),
                    },
                )
            )
        # trailer (9) e demais: ignorados.

    return RemessaParsed(data_ref_raw=data_ref_raw, ocorrencias=ocorrencias)
