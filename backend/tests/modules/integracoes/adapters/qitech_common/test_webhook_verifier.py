"""Inbound webhook verifier — sub extraction + mismatch detection."""

from __future__ import annotations

import jwt
import pytest

from app.modules.integracoes.adapters._qitech_common.errors import (
    QiTechWebhookVerificationError,
)
from app.modules.integracoes.adapters._qitech_common.signer import sign_request_jwt
from app.modules.integracoes.adapters._qitech_common.webhook_verifier import (
    WebhookPayload,
    verify_inbound_webhook,
)
from tests.modules.integracoes.adapters.qitech_common._fixtures import (
    API_CLIENT_KEY,
    PRIVATE_PEM_P521,
    PUBLIC_PEM_P521,
)


def test_verifies_and_returns_payload_without_expected_key() -> None:
    token = sign_request_jwt(
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        body={"event": "custody.updated"},
    )
    payload = verify_inbound_webhook(
        token=token,
        qi_public_key_pem=PUBLIC_PEM_P521,
    )

    assert isinstance(payload, WebhookPayload)
    assert payload.api_client_key == API_CLIENT_KEY
    assert payload.claims["iss"] == API_CLIENT_KEY


def test_accepts_matching_expected_api_client_key() -> None:
    token = sign_request_jwt(
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        body=None,
    )
    payload = verify_inbound_webhook(
        token=token,
        qi_public_key_pem=PUBLIC_PEM_P521,
        expected_api_client_key=API_CLIENT_KEY,
    )
    assert payload.api_client_key == API_CLIENT_KEY


def test_rejects_mismatched_expected_api_client_key() -> None:
    token = sign_request_jwt(
        api_client_key=API_CLIENT_KEY,
        private_key_pem=PRIVATE_PEM_P521,
        body=None,
    )
    with pytest.raises(QiTechWebhookVerificationError, match="does not match"):
        verify_inbound_webhook(
            token=token,
            qi_public_key_pem=PUBLIC_PEM_P521,
            expected_api_client_key="other-tenant-key",
        )


def test_rejects_missing_sub_claim() -> None:
    # Build a token with no 'sub' but valid iat/exp + ES512 signature.
    from cryptography.hazmat.primitives import serialization

    priv = serialization.load_pem_private_key(
        PRIVATE_PEM_P521.encode("utf-8"), password=None
    )
    import time

    now = int(time.time())
    token = jwt.encode(
        {"iat": now, "exp": now + 60},
        priv,
        algorithm="ES512",
    )
    with pytest.raises(QiTechWebhookVerificationError, match="'sub'"):
        verify_inbound_webhook(token=token, qi_public_key_pem=PUBLIC_PEM_P521)
