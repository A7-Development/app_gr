"""PII redaction for prompts/messages going to LLM providers.

MVP: regex-based CPF / CNPJ / conta-agencia detection with check-digit
validation for CPF and CNPJ to minimize false positives.

Phase 2 will replace this with Microsoft Presidio for multi-category PII
(names, emails, addresses) using Brazilian recognizers.

Output:
    redact(text) -> (redacted_text, pii_map)

Where `pii_map` is `{placeholder -> original}` so audit logs can recover the
original text via a separate (admin-only) endpoint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# Strict CPF: ddd.ddd.ddd-dd  OR  loose 11 digits in a row.
_CPF_RE = re.compile(r"\b(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})[-\s]?(\d{2})\b")
# Strict CNPJ: dd.ddd.ddd/dddd-dd  OR  loose 14 digits.
_CNPJ_RE = re.compile(r"\b(\d{2})[.\s]?(\d{3})[.\s]?(\d{3})[/\s]?(\d{4})[-\s]?(\d{2})\b")
# Conta-agencia: 4-12 digits, dash, single check digit.
_CONTA_RE = re.compile(r"\b(\d{4,12})-(\d)\b")
# Email — basic.
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


@dataclass(slots=True)
class RedactionResult:
    """Output of `redact()`."""

    text: str
    pii_map: dict[str, str]

    @property
    def has_pii(self) -> bool:
        return bool(self.pii_map)


def _cpf_check_digit_valid(cpf_digits: str) -> bool:
    """Validate Brazilian CPF check digits (mod 11)."""
    if len(cpf_digits) != 11 or len(set(cpf_digits)) == 1:
        return False
    digits = [int(c) for c in cpf_digits]
    s1 = sum(d * w for d, w in zip(digits[:9], range(10, 1, -1), strict=True))
    d1 = (s1 * 10) % 11 % 10
    if d1 != digits[9]:
        return False
    s2 = sum(d * w for d, w in zip(digits[:10], range(11, 1, -1), strict=True))
    d2 = (s2 * 10) % 11 % 10
    return d2 == digits[10]


def _cnpj_check_digit_valid(cnpj_digits: str) -> bool:
    """Validate Brazilian CNPJ check digits (mod 11)."""
    if len(cnpj_digits) != 14 or len(set(cnpj_digits)) == 1:
        return False
    digits = [int(c) for c in cnpj_digits]
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s1 = sum(d * w for d, w in zip(digits[:12], weights1, strict=True))
    d1 = 0 if (r := s1 % 11) < 2 else 11 - r
    if d1 != digits[12]:
        return False
    s2 = sum(d * w for d, w in zip(digits[:13], weights2, strict=True))
    d2 = 0 if (r := s2 % 11) < 2 else 11 - r
    return d2 == digits[13]


def _make_replacer(pii_map: dict[str, str], prefix: str) -> Final:
    counter = {"n": 0}

    def replace(original: str) -> str:
        counter["n"] += 1
        placeholder = f"[{prefix}_{counter['n']}]"
        pii_map[placeholder] = original
        return placeholder

    return replace


def redact(text: str, *, preserve_query_identifiers: bool = False) -> RedactionResult:
    """Replace CPF, CNPJ, conta-agencia and emails with placeholders.

    Validation: CPF and CNPJ matches are kept only if check digits are valid
    (avoids false positives on random number runs). Conta-agencia and emails
    are pattern-only.

    `preserve_query_identifiers=True` keeps CPF/CNPJ intact — used by the
    Copiloto (Strata AI), where the identifier IS the query input: masking
    it would break the tool call (spec copiloto-mcp §12.7; redaction stays
    reserved for PII the model does NOT need — emails, contas). The AIPanel
    chat path keeps the full redaction (default).

    Returns redacted text plus a map for audit recovery.
    """
    pii_map: dict[str, str] = {}

    if not preserve_query_identifiers:
        # CPF
        cpf_replacer = _make_replacer(pii_map, "CPF")

        def cpf_sub(match: re.Match[str]) -> str:
            full = match.group(0)
            digits = "".join(c for c in full if c.isdigit())
            if _cpf_check_digit_valid(digits):
                return cpf_replacer(full)
            return full

        text = _CPF_RE.sub(cpf_sub, text)

        # CNPJ
        cnpj_replacer = _make_replacer(pii_map, "CNPJ")

        def cnpj_sub(match: re.Match[str]) -> str:
            full = match.group(0)
            digits = "".join(c for c in full if c.isdigit())
            if _cnpj_check_digit_valid(digits):
                return cnpj_replacer(full)
            return full

        text = _CNPJ_RE.sub(cnpj_sub, text)

    # Conta-agencia (no check digit; pattern-only)
    conta_replacer = _make_replacer(pii_map, "CONTA")
    text = _CONTA_RE.sub(lambda m: conta_replacer(m.group(0)), text)

    # Email
    email_replacer = _make_replacer(pii_map, "EMAIL")
    text = _EMAIL_RE.sub(lambda m: email_replacer(m.group(0)), text)

    return RedactionResult(text=text, pii_map=pii_map)


def restore(text: str, pii_map: dict[str, str]) -> str:
    """Reverse the redaction (audit only)."""
    for placeholder, original in pii_map.items():
        text = text.replace(placeholder, original)
    return text
