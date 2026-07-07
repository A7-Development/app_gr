"""Cliente HTTP dos dados abertos do Bacen (fontes publicas, sem credencial).

Duas fontes:
  - Participantes do STR: CSV em bcb.gov.br (atualizacao diaria). Traz ISPB,
    nome e o CODIGO COMPE do banco -- a chave que trafega no CNAB.
  - Informes_Agencias (API Olinda, OData): agencias de bancos com municipio/UF.
    Snapshot mensal do UNICAD. Cooperativas NAO tem agencia aqui (o codigo de
    "agencia" 756/748 do CNAB e interno das redes cooperativas -- por decisao
    de escopo, cooperativa e classificada como canal proprio, sem praca).
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

STR_CSV_URL = (
    "https://www.bcb.gov.br/content/estabilidadefinanceira/str1/ParticipantesSTR.csv"
)
OLINDA_AGENCIAS_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/Informes_Agencias/versao/v1/odata/Agencias"
)

_TIMEOUT_S = 120
_PAGE_SIZE = 10_000


async def fetch_participantes_str() -> list[dict[str, str]]:
    """Baixa e parseia o CSV de participantes do STR.

    Returns rows como dicts (chaves do header: ISPB, Nome_Reduzido,
    Número_Código, Participa_da_Compe, Acesso_Principal, Nome_Extenso,
    Início_da_Operação). Encoding UTF-8 com BOM.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        resp = await client.get(STR_CSV_URL)
        resp.raise_for_status()
    text = resp.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    logger.info("bacen STR: %d participantes", len(rows))
    return rows


async def fetch_agencias() -> list[dict[str, Any]]:
    """Baixa todas as agencias do Informes_Agencias (OData, paginado)."""
    out: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        skip = 0
        while True:
            resp = await client.get(
                OLINDA_AGENCIAS_URL,
                params={
                    "$format": "json",
                    "$top": str(_PAGE_SIZE),
                    "$skip": str(skip),
                },
            )
            resp.raise_for_status()
            page = resp.json().get("value", [])
            out.extend(page)
            logger.info("bacen agencias: +%d (total %d)", len(page), len(out))
            if len(page) < _PAGE_SIZE:
                break
            skip += _PAGE_SIZE
    return out
