"""Envelope encryption for JSON payloads (tenant_source_config.config).

Design:
    - KEK (Key Encryption Key): single process-wide Fernet key read from
      `settings.APP_CONFIG_KEK`. In production this is the swap point for
      AWS KMS / GCP KMS (wrap/unwrap DEKs remotely, ciphertexts stay local).
    - DEK (Data Encryption Key): fresh Fernet key per payload. Cipher the
      JSON body with the DEK, then wrap the DEK with the KEK.
    - Envelope: dict `{"v": 1, "dek": "<b64-kek-wrapped>", "ct": "<b64-fernet-ciphertext>"}`
      stored as-is in the JSONB column.

Rotation:
    Rotating the KEK only requires unwrap-with-old + wrap-with-new of each DEK
    (`rewrap_envelope`). Ciphertexts are untouched — cheap and safe.
"""

from __future__ import annotations

import json
from typing import Any, Final

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

ENVELOPE_VERSION: Final[int] = 1


class EnvelopeError(Exception):
    """Raised when an envelope payload cannot be produced or consumed."""


def _kek() -> Fernet:
    """Load the process-wide KEK from settings."""
    key = get_settings().APP_CONFIG_KEK
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as e:
        raise EnvelopeError(f"APP_CONFIG_KEK is not a valid Fernet key: {e}") from e


def is_envelope(payload: Any) -> bool:
    """Whether `payload` looks like an envelope produced by `encrypt_envelope`."""
    return (
        isinstance(payload, dict)
        and payload.get("v") == ENVELOPE_VERSION
        and isinstance(payload.get("dek"), str)
        and isinstance(payload.get("ct"), str)
    )


def encrypt_envelope(plaintext: dict) -> dict:
    """Serialize `plaintext` (JSON dict) and encrypt into an envelope.

    Raises EnvelopeError on any failure.
    """
    try:
        body = json.dumps(plaintext, ensure_ascii=False, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as e:
        raise EnvelopeError(f"payload is not JSON-serializable: {e}") from e

    dek_key = Fernet.generate_key()
    dek = Fernet(dek_key)
    ct = dek.encrypt(body)
    wrapped_dek = _kek().encrypt(dek_key)

    return {
        "v": ENVELOPE_VERSION,
        "dek": wrapped_dek.decode("ascii"),
        "ct": ct.decode("ascii"),
    }


def decrypt_envelope(envelope: dict) -> dict:
    """Decrypt an envelope back into the original dict.

    Raises EnvelopeError if the envelope is malformed, tampered with, or the
    current KEK cannot unwrap the DEK.
    """
    if not is_envelope(envelope):
        raise EnvelopeError("payload is not an envelope (missing v/dek/ct)")
    try:
        dek_key = _kek().decrypt(envelope["dek"].encode("ascii"))
    except InvalidToken as e:
        raise EnvelopeError(
            "cannot unwrap DEK — KEK mismatch or envelope tampered"
        ) from e
    try:
        body = Fernet(dek_key).decrypt(envelope["ct"].encode("ascii"))
    except InvalidToken as e:
        raise EnvelopeError("ciphertext invalid — envelope tampered") from e
    return json.loads(body.decode("utf-8"))


def rewrap_envelope(envelope: dict, new_kek: Fernet) -> dict:
    """Rotate the KEK: unwrap DEK with the current KEK, re-wrap with `new_kek`.

    Ciphertext is left untouched. Used by a future `rotate-kek` CLI command.
    """
    if not is_envelope(envelope):
        raise EnvelopeError("payload is not an envelope")
    try:
        dek_key = _kek().decrypt(envelope["dek"].encode("ascii"))
    except InvalidToken as e:
        raise EnvelopeError("cannot unwrap DEK with current KEK") from e
    new_wrapped = new_kek.encrypt(dek_key)
    return {
        "v": ENVELOPE_VERSION,
        "dek": new_wrapped.decode("ascii"),
        "ct": envelope["ct"],
    }
