"""Helpers compartilhados pelos mappers QiTech.

Conversoes idempotentes (numero/string/iso -> tipos canonicos) + builder
de proveniencia. Todos os helpers sao puros — sem I/O.

Por que extrair:
- 9 mappers vao reusar o mesmo padrao de conversao Decimal/iso/None.
- Mudar regra de normalizacao (ex.: tratar string vazia em mais campos)
  fica em 1 lugar so.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.hashing import sha256_of_row
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION


def to_decimal(value: Any) -> Decimal:
    """Converte number/str QiTech para Decimal sem perda.

    QiTech devolve ora int (0), ora float (82.140195), ora string — todos
    aceitaveis. Normalizamos via `str(value)` antes de Decimal pra evitar
    round-trip float->Decimal introduzir ruido em 1e-10.

    None vira `Decimal("0")` — caller pode preferir tratar None separadamente
    se semantica for "nao se aplica" vs "zero".
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def to_decimal_or_none(value: Any) -> Decimal | None:
    """Como `to_decimal`, mas preserva `None` em vez de virar zero.

    Util quando 0 e Null sao distintos (ex.: `mtm` que pode ser legitimamente 0
    ou pode ser "nao calculado"; o segundo deve ficar Null no warehouse).
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def to_decimal_or_none_within(value: Any, *, max_abs: Decimal) -> Decimal | None:
    """Como `to_decimal_or_none`, mas vira None quando `|value| > max_abs`.

    Why: QiTech as vezes devolve lixo numerico (~1e18) em campos percentuais
    quando o denominador da carteira e zero — float divide-by-near-zero do
    lado deles. Validado em 2026-04-26 com REALINVEST (saldo conta-corrente
    liquido = 0): pct chegou como -6.234.570.403.704.996.000 enquanto o
    schema canonico (`NUMERIC(8,4)`) so aceita ate 9999.9999.

    How to apply: passe `max_abs` igual ao limite real do schema. Lixo da
    fonte vira None — quem consumir o warehouse recalcula a partir do
    `valor_total` se precisar. Melhor None que corromper canonico.
    """
    if value is None:
        return None
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    if abs(d) > max_abs:
        return None
    return d


def normalize_str_or_none(value: Any) -> str | None:
    """Canoniza string vazia / whitespace / None em None.

    QiTech usa `""` em alguns campos opcionais (ex.: `códigoDoClienteNoSAC`)
    e `null` em outros (ex.: `mtm`) — uniformiza pra None e mantem queries
    consistentes.
    """
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return str(value)


def parse_iso_or_none(value: Any) -> datetime | None:
    """Parse tolerante de ISO-8601 da QiTech ("2026-01-13T00:00:00.000Z").

    Retorna None se parse falhar — proveniencia nao deve derrubar ETL.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        # datetime.fromisoformat aceita o sufixo Z desde 3.11.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_provenance(
    *,
    source_id: str,
    item: dict[str, Any],
    ingested_at: datetime,
    source_updated_at: datetime | None,
) -> dict[str, Any]:
    """Monta os campos do mixin Auditable pra uma linha canonica.

    `source_updated_at` precisa ser parseado pelo caller pq cada endpoint
    QiTech usa uma chave de data diferente (`dataDaPosição`, `dataLiquidação`,
    `dataAquisição`, etc).

    `hash_origem` e SHA256 do `item` cru (chaves acentuadas preservadas) —
    detecta mudanca byte-perfect entre re-fetches.
    """
    return {
        "source_type": SourceType.ADMIN_QITECH,
        "source_id": source_id,
        "source_updated_at": source_updated_at,
        "ingested_at": ingested_at,
        "hash_origem": sha256_of_row(item),
        "ingested_by_version": ADAPTER_VERSION,
        "trust_level": TrustLevel.HIGH,
        "collected_by": None,
    }
