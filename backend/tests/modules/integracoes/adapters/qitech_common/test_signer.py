"""ES512 signer — round-trip, claim shape, tampering, expiry."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.modules.integracoes.adapters._qitech_common.errors import (
    QiTechSigningError,
    QiTechWebhookVerificationError,
)
from app.modules.integracoes.adapters._qitech_common.signer import (
    ALGORITHM,
    sign_request_jwt,
    verify_webhook_jwt,
)
from tests.modules.integracoes.adapters.qitech_common._fixtures import (
    API_CLIENT_KEY,
    PRIVATE_PEM_P521,
    PUBLIC_PEM_P521,
)


def _decode_unverified(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def test_sign_produces_es512_token_with_expected_claims() -> None:
    body = {"b": 2, "a": 1}  # intentionally unsorted; canonicalization must sort
    token = sign_request_jwt(
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        body=body,
    )

    header = jwt.get_unverified_header(token)
    assert header["alg"] == "ES512"

    claims = _decode_unverified(token)
    assert claims["iss"] == API_CLIENT_KEY
    assert claims["sub"] == API_CLIENT_KEY
    assert claims["exp"] > claims["iat"]

    # md5 is over the canonical JSON — keys sorted, no whitespace.
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    assert claims["md5"] == hashlib.md5(canonical.encode()).hexdigest()


def test_sign_with_none_body_hashes_empty_object() -> None:
    token = sign_request_jwt(
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        body=None,
    )
    claims = _decode_unverified(token)
    assert claims["md5"] == hashlib.md5(b"{}").hexdigest()


def test_sign_respects_injected_now_and_ttl() -> None:
    fixed = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    token = sign_request_jwt(
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        body={"x": 1},
        now=fixed,
        ttl_seconds=120,
    )
    claims = _decode_unverified(token)
    assert claims["iat"] == int(fixed.timestamp())
    assert claims["exp"] == int(fixed.timestamp()) + 120


def test_sign_rejects_empty_api_client_key() -> None:
    with pytest.raises(QiTechSigningError, match="api_client_key"):
        sign_request_jwt(
            api_client_key="",
            private_key_pem=PRIVATE_PEM_P521,
            body=None,
        )


def test_round_trip_verify_webhook() -> None:
    # Simulate QiTech signing a webhook: same algorithm, their private key
    # = our test PRIVATE_PEM, their public key = our test PUBLIC_PEM.
    token = sign_request_jwt(
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        body={"event": "custody.updated"},
    )
    claims = verify_webhook_jwt(
        token=token,
        qi_public_key_pem=PUBLIC_PEM_P521,
    )
    assert claims["sub"] == API_CLIENT_KEY


def test_verify_rejects_tampered_token() -> None:
    token = sign_request_jwt(
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        body=None,
    )
    # Flip one char in the payload segment.
    header, payload, sig = token.split(".")
    tampered = f"{header}.{payload[:-2]}XX.{sig}"

    with pytest.raises(QiTechWebhookVerificationError):
        verify_webhook_jwt(token=tampered, qi_public_key_pem=PUBLIC_PEM_P521)


def test_verify_rejects_expired_token() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    token = sign_request_jwt(
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        body=None,
        now=past,
        ttl_seconds=60,
    )
    with pytest.raises(QiTechWebhookVerificationError):
        verify_webhook_jwt(
            token=token,
            qi_public_key_pem=PUBLIC_PEM_P521,
            leeway_seconds=0,
        )


def test_verify_rejects_empty_token() -> None:
    with pytest.raises(QiTechWebhookVerificationError, match="empty token"):
        verify_webhook_jwt(token="", qi_public_key_pem=PUBLIC_PEM_P521)


def test_verify_rejects_wrong_algorithm() -> None:
    # HS256 token should not be accepted when we only allow ES512.
    hs_token = jwt.encode(
        {"iat": 1_700_000_000, "exp": 9_999_999_999, "sub": API_CLIENT_KEY},
        "secret",
        algorithm="HS256",
    )
    assert ALGORITHM == "ES512"
    with pytest.raises(QiTechWebhookVerificationError):
        verify_webhook_jwt(token=hs_token, qi_public_key_pem=PUBLIC_PEM_P521)
