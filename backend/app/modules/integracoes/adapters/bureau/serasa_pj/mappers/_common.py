"""Helpers compartilhados pelos mappers Serasa PJ.

Conversoes idempotentes (numero/string/iso -> tipos canonicos) + builder
de proveniencia para o mixin `Auditable`. Todos os helpers sao puros —
sem I/O.

Por que extrair: 5 mappers (consulta + socio + restricao + participacao
+ endereco) reutilizam o mesmo padrao de conversao + parsing tolerante
de chaves camelCase/PascalCase variantes da Serasa.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.bureau.serasa_pj.hashing import (
    sha256_of_row,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.version import (
    ADAPTER_VERSION,
)

# ─── Conversoes ────────────────────────────────────────────────────────────


def to_decimal_or_none(value: Any) -> Decimal | None:
    """Converte number/str para Decimal sem perda. None preserva None.

    Serasa devolve numericos ora como float ora como str. Normalizamos via
    `str(value)` antes de Decimal pra evitar ruido de round-trip float.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool e subclass de int em Python
        return None
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def normalize_str_or_none(value: Any) -> str | None:
    """Canoniza string vazia / whitespace / None em None."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    return str(value)


def parse_date_or_none(value: Any) -> date | None:
    """Parse tolerante de data — aceita ISO `YYYY-MM-DD`, `YYYY-MM-DDTHH:...`
    ou `DD/MM/YYYY` (formato BR comum em payloads da Serasa).

    Retorna None em qualquer falha — proveniencia nao deve derrubar mapper.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value.strip():
        return None

    s = value.strip()
    # ISO com tempo opcional.
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass

    # BR DD/MM/YYYY.
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        try:
            return datetime.strptime(s, "%d/%m/%Y").date()
        except ValueError:
            return None
    return None


def parse_datetime_or_none(value: Any) -> datetime | None:
    """Parse tolerante de ISO-8601 (com Z opcional)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def strip_non_digits(value: Any) -> str:
    """Remove tudo que nao for digito. None / nao-string -> string vazia."""
    if value is None:
        return ""
    s = str(value)
    return "".join(ch for ch in s if ch.isdigit())


def classify_documento(documento: str) -> str:
    """Classifica string-de-digitos em 'cpf' (11) | 'cnpj' (14) | 'unknown'."""
    if len(documento) == 11:
        return "cpf"
    if len(documento) == 14:
        return "cnpj"
    return "unknown"


# ─── Acesso flexivel a chaves camelCase / PascalCase ───────────────────────


def get_block(payload: dict[str, Any], *keys: str) -> Any:
    """Tenta varias chaves de `payload` em ordem; retorna a primeira nao-None.

    Serasa as vezes muda capitalizacao entre versoes da API. Em vez de
    falhar quando encontra `RegistrationData` em vez de `registrationData`,
    o mapper testa ambas.
    """
    if not isinstance(payload, dict):
        return None
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def as_list(value: Any) -> list:
    """Coerce para list — tolera valor singular ou None."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ─── Proveniencia ──────────────────────────────────────────────────────────


def build_provenance(
    *,
    source_id: str,
    item: Any,
    ingested_at: datetime,
    source_updated_at: datetime | None = None,
    trust_level: TrustLevel = TrustLevel.HIGH,
) -> dict[str, Any]:
    """Monta os campos do mixin Auditable pra uma linha silver.

    `source_type` e fixo: `BUREAU_SERASA_PJ`.
    `hash_origem` e SHA256 do `item` cru (chaves preservadas) — detecta
    mudanca byte-perfect quando re-mapeamos.
    """
    return {
        "source_type": SourceType.BUREAU_SERASA_PJ,
        "source_id": source_id,
        "source_updated_at": source_updated_at,
        "ingested_at": ingested_at,
        "hash_origem": sha256_of_row(item) if item is not None else None,
        "ingested_by_version": ADAPTER_VERSION,
        "trust_level": trust_level,
        "collected_by": None,
    }
