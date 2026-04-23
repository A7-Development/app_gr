"""Tests for envelope encryption (app.shared.crypto.envelope)."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.shared.crypto.envelope import (
    ENVELOPE_VERSION,
    EnvelopeError,
    decrypt_envelope,
    encrypt_envelope,
    is_envelope,
    rewrap_envelope,
)


def test_roundtrip_preserves_payload():
    plain = {"api_key": "abc123", "nested": {"k": [1, 2, 3]}, "bool": True}
    env = encrypt_envelope(plain)
    assert is_envelope(env)
    assert env["v"] == ENVELOPE_VERSION
    assert decrypt_envelope(env) == plain


def test_envelope_contains_no_plaintext():
    plain = {"secret_pem": "-----BEGIN PRIVATE KEY-----\nxyzsecret\n-----END PRIVATE KEY-----"}
    env = encrypt_envelope(plain)
    serialized = str(env)
    assert "xyzsecret" not in serialized
    assert "BEGIN PRIVATE KEY" not in serialized


def test_two_encryptions_produce_different_ciphertext():
    plain = {"k": "v"}
    a = encrypt_envelope(plain)
    b = encrypt_envelope(plain)
    assert a["ct"] != b["ct"]  # fresh DEK per call
    assert a["dek"] != b["dek"]
    assert decrypt_envelope(a) == decrypt_envelope(b) == plain


def test_tampered_ciphertext_raises():
    env = encrypt_envelope({"k": "v"})
    env["ct"] = env["ct"][:-4] + "AAAA"
    with pytest.raises(EnvelopeError):
        decrypt_envelope(env)


def test_tampered_dek_raises():
    env = encrypt_envelope({"k": "v"})
    env["dek"] = Fernet.generate_key().decode("ascii")  # unrelated key, wrapped with nothing
    with pytest.raises(EnvelopeError):
        decrypt_envelope(env)


def test_non_envelope_payload_rejected():
    with pytest.raises(EnvelopeError):
        decrypt_envelope({"just": "a dict"})
    assert not is_envelope({"v": 1, "dek": "x"})  # missing ct
    assert not is_envelope({"v": 2, "dek": "x", "ct": "y"})  # wrong version


def test_rewrap_preserves_plaintext_without_touching_ciphertext():
    plain = {"k": "v"}
    env = encrypt_envelope(plain)
    original_ct = env["ct"]

    new_kek = Fernet(Fernet.generate_key())
    rewrapped = rewrap_envelope(env, new_kek)

    assert rewrapped["ct"] == original_ct  # ciphertext untouched
    assert rewrapped["dek"] != env["dek"]  # DEK re-wrapped
