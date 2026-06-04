"""Mapper ocorrencias CNAB (bronze) -> wh_boleto (silver canonico).

Generico por banco: recebe as ocorrencias parseadas (payloads crus do bronze)
+ um `estado_resolver` (o decoder ring do banco, ex.: bradesco.
estado_from_codigo) e produz os value-dicts de `wh_boleto` com tipos
convertidos e **vigencia resolvida** (ultima ocorrencia por numero de
documento). Mantem o mapper agnostico de banco -- a especificidade fica no
parser/decoder do adapter de cada banco.

Conversao de tipos acontece AQUI (nao no parser): DDMMAA -> date, centavos
zero-padded -> Decimal. O parser entrega strings cruas (bronze fiel).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.enums import SourceType, TrustLevel

# Uma ocorrencia parseada minima: o que o mapper consome de cada item. Casa
# com `OcorrenciaParsed.payload` do parser + a linha de origem.
PayloadOcorrencia = dict[str, str]


def parse_ddmmaa(value: str | None) -> date | None:
    """DDMMAA -> date (assume seculo 2000). Retorna None se invalido/vazio."""
    if not value or len(value) != 6 or not value.isdigit():
        return None
    dia, mes, ano = int(value[0:2]), int(value[2:4]), int(value[4:6])
    if dia == 0 or mes == 0:
        return None
    try:
        return date(2000 + ano, mes, dia)
    except ValueError:
        return None


def _parse_centavos(value: str | None) -> Decimal | None:
    """String zero-padded em centavos -> Decimal em reais. None se vazia/zero."""
    if not value or not value.isdigit():
        return None
    cents = int(value)
    if cents == 0:
        return None
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.0001"))


def _vigentes_por_numero(
    ocorrencias: Sequence[tuple[int, PayloadOcorrencia]],
) -> list[tuple[int, PayloadOcorrencia]]:
    """Resolve vigencia: por numero_documento, mantem a ocorrencia mais recente.

    Ordena por (data_ocorrencia, linha_num) e fica com a ultima. Um retorno
    diario costuma ter 1 ocorrencia por titulo, mas o titulo pode aparecer mais
    de uma vez (entrada -> liquidacao no mesmo arquivo) -- vale a mais recente.
    """
    melhor: dict[str, tuple[date | None, int, PayloadOcorrencia]] = {}
    for linha_num, payload in ocorrencias:
        numero = (payload.get("numero_documento") or "").strip()
        if not numero:
            continue
        dt = parse_ddmmaa(payload.get("data_ocorrencia"))
        chave_ordem = (dt or date.min, linha_num)
        atual = melhor.get(numero)
        if atual is None or chave_ordem > (atual[0] or date.min, atual[1]):
            melhor[numero] = (dt, linha_num, payload)
    return [(linha_num, payload) for _, linha_num, payload in melhor.values()]


def map_ocorrencias_to_boletos(
    ocorrencias: Sequence[tuple[int, PayloadOcorrencia]],
    *,
    tenant_id: UUID,
    banco: str,
    data_ref: date,
    source_type: SourceType,
    estado_resolver: Callable[[str | None], str | None],
    ingested_by_version: str,
    arquivo_id: UUID | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Mapeia ocorrencias vigentes para value-dicts de `wh_boleto`.

    `ocorrencias` e uma sequencia de (linha_num, payload). Returns
    (values, ignorados) -- `ignorados` conta ocorrencias cujo codigo nao
    resolveu para um estado conhecido (descartadas do silver, ficam no bronze).
    """
    values: list[dict[str, Any]] = []
    ignorados = 0

    for _linha_num, payload in _vigentes_por_numero(ocorrencias):
        codigo = (payload.get("codigo_ocorrencia") or "").strip() or None
        estado = estado_resolver(codigo)
        if estado is None:
            ignorados += 1
            continue

        numero = (payload.get("numero_documento") or "").strip()
        nosso_numero = (payload.get("nosso_numero") or "").strip() or None
        valor = _parse_centavos(payload.get("valor_titulo"))
        vencimento = parse_ddmmaa(payload.get("data_vencimento"))
        if valor is None or vencimento is None or not numero:
            # Boleto sem valor/vencimento/numero nao concilia -- descarta
            # (fica no bronze para investigacao).
            ignorados += 1
            continue

        values.append(
            {
                "tenant_id": tenant_id,
                "banco_origem": banco,
                "numero_documento": numero,
                "nosso_numero": nosso_numero,
                "sacado_documento": (payload.get("sacado_documento") or "").strip()
                or None,
                "sacado_nome": (payload.get("sacado_nome") or "").strip() or None,
                "valor_boleto": valor,
                "valor_pago": _parse_centavos(payload.get("valor_pago")),
                "data_vencimento": vencimento,
                "data_pagamento": parse_ddmmaa(payload.get("data_pagamento")),
                "estado": estado,
                "codigo_ocorrencia": codigo,
                "data_ocorrencia": parse_ddmmaa(payload.get("data_ocorrencia")),
                "data_ref": data_ref,
                "arquivo_id": arquivo_id,
                # Auditable
                "source_type": source_type,
                "source_id": f"{banco}:{nosso_numero or numero}:{data_ref.isoformat()}",
                "ingested_by_version": ingested_by_version,
                "trust_level": TrustLevel.HIGH,
            }
        )

    return values, ignorados
