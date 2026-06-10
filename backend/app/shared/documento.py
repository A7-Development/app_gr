"""Documento (CPF/CNPJ) normalization — identity resolution primitives.

Canonical identity policy (party model, see CLAUDE.md keyword
"modelo canonico entity-centric"):

- 1 canonical entity per (tenant, documento) where documento is the
  NORMALIZED digit string: 14 digits (CNPJ) or 11 digits (CPF).
- CNPJ hierarchy is DERIVED from the document itself (deterministic,
  no curation): digits 1-8 = `raiz` (the legal person), digits 9-12 =
  `filial_numero` ("0001" = matriz), digits 13-14 = check digits.
  Branches of the same company share the raiz — risk views consolidate
  by raiz for PJ; the per-establishment row is kept (address, titles
  and ocorrencias are per-branch facts).
- Documents that fail normalization/check digits do NOT become entities.
  They land in quarantine (crosswalk row with `entidade_id IS NULL`) so
  nothing disappears silently (CLAUDE.md §14.6 spirit).

Source quirks handled here:
- Bitfin stores `Entidade.Documento` left-zero-padded to 15 chars for PJ
  (e.g. Banco do Brasil = "000000000000191") and 11 chars for PF.
  Rightmost 14/11 digits are the real document.
- Bureaus (Serasa/BDC) use unpadded digit strings or masked formats.

Pure functions only — no I/O, no DB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.enums import TipoPessoa

_NON_DIGITS = re.compile(r"\D")

MATRIZ_FILIAL_NUMERO = "0001"


@dataclass(frozen=True)
class DocumentoNormalizado:
    """Result of normalizing a raw CPF/CNPJ string."""

    documento: str
    """Normalized digits: 14 (CNPJ) or 11 (CPF)."""

    tipo_pessoa: TipoPessoa

    valido: bool
    """Check digits verified. Invalid documents are quarantined upstream."""

    raiz: str | None
    """CNPJ only: first 8 digits — identifies the legal person across
    branches. None for CPF."""

    filial_numero: str | None
    """CNPJ only: digits 9-12 ("0001" = matriz). None for CPF."""

    is_matriz: bool | None
    """CNPJ only: filial_numero == "0001". None for CPF."""


def _cpf_check_digits_ok(d: str) -> bool:
    if len(d) != 11 or len(set(d)) == 1:
        return False
    digits = [int(c) for c in d]
    s1 = sum(v * w for v, w in zip(digits[:9], range(10, 1, -1), strict=True))
    if (s1 * 10) % 11 % 10 != digits[9]:
        return False
    s2 = sum(v * w for v, w in zip(digits[:10], range(11, 1, -1), strict=True))
    return (s2 * 10) % 11 % 10 == digits[10]


def _cnpj_check_digits_ok(d: str) -> bool:
    if len(d) != 14 or len(set(d)) == 1:
        return False
    digits = [int(c) for c in d]
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s1 = sum(v * w for v, w in zip(digits[:12], weights1, strict=True))
    d1 = 0 if s1 % 11 < 2 else 11 - s1 % 11
    if d1 != digits[12]:
        return False
    weights2 = [6, *weights1]
    s2 = sum(v * w for v, w in zip(digits[:13], weights2, strict=True))
    d2 = 0 if s2 % 11 < 2 else 11 - s2 % 11
    return d2 == digits[13]


def normalizar_documento(
    raw: str | None, tipo_hint: TipoPessoa | None = None
) -> DocumentoNormalizado | None:
    """Normalize a raw CPF/CNPJ string into the canonical identity key.

    `tipo_hint` disambiguates when the source declares the person type
    (e.g. Bitfin `Entidade.Tipo`). Without a hint, the type is inferred
    from digit length, accepting left-zero padding: <=11 digits tries CPF
    first, then CNPJ (zero-padded); 12-15 digits is CNPJ (rightmost 14,
    requiring any extra leading chars to be zeros).

    Returns None when the input has no digits or cannot fit either shape
    (caller decides quarantine). A well-shaped document with BAD check
    digits is returned with `valido=False` — shape and validity are
    different facts, both useful for quarantine reporting.
    """
    if raw is None:
        return None
    digits = _NON_DIGITS.sub("", raw)
    if not digits:
        return None

    def _fit(d: str, width: int) -> str | None:
        """Zero-pad up to width; accept longer only if extra lead is zeros."""
        if len(d) <= width:
            return d.zfill(width)
        extra = len(d) - width
        if d[:extra] == "0" * extra:
            return d[extra:]
        return None

    candidates: list[TipoPessoa] = (
        [tipo_hint]
        if tipo_hint is not None
        else ([TipoPessoa.PF, TipoPessoa.PJ] if len(digits) <= 11 else [TipoPessoa.PJ])
    )

    result: DocumentoNormalizado | None = None
    for tipo in candidates:
        width = 11 if tipo == TipoPessoa.PF else 14
        fitted = _fit(digits, width)
        if fitted is None:
            continue
        valido = (
            _cpf_check_digits_ok(fitted)
            if tipo == TipoPessoa.PF
            else _cnpj_check_digits_ok(fitted)
        )
        candidate = DocumentoNormalizado(
            documento=fitted,
            tipo_pessoa=tipo,
            valido=valido,
            raiz=fitted[:8] if tipo == TipoPessoa.PJ else None,
            filial_numero=fitted[8:12] if tipo == TipoPessoa.PJ else None,
            is_matriz=(fitted[8:12] == MATRIZ_FILIAL_NUMERO)
            if tipo == TipoPessoa.PJ
            else None,
        )
        if valido:
            return candidate
        if result is None:
            result = candidate
    return result
