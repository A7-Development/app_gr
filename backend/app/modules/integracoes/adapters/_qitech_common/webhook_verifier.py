"""Authenticate inbound QiTech webhooks and resolve the originating tenant.

QiTech signs webhook deliveries with its own ES512 key (not the tenant's).
The `sub` claim inside the JWT carries the tenant's `api_client_key`, which
is how we map an inbound delivery to a row in `tenant_source_config`.

Responsibilities:
    1. Validate signature + temporal claims (delegated to `signer.verify_webhook_jwt`).
    2. Enforce that `sub` matches the expected `api_client_key` for the target
       tenant — otherwise a tenant A webhook could be replayed into tenant B.
    3. Return a typed payload with tenant-ident claims extracted, so the
       router layer does not re-decode the JWT.

This module is intentionally thin. The router (webhooks.py, Fase 5) still owns
tenant resolution (lookup by api_client_key) — we only provide the verified
claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.integracoes.adapters._qitech_common.errors import (
    QiTechWebhookVerificationError,
)
from app.modules.integracoes.adapters._qitech_common.signer import verify_webhook_jwt


@dataclass(frozen=True)
class WebhookPayload:
    """Verified webhook envelope ready for router-level dispatch.

    Attributes:
        api_client_key: tenant identifier extracted from the JWT `sub` claim.
        claims: full decoded claims dict (iat, exp, sub, plus any QiTech extras).
    """

    api_client_key: str
    claims: dict[str, Any]


def verify_inbound_webhook(
    *,
    token: str,
    qi_public_key_pem: str,
    expected_api_client_key: str | None = None,
    leeway_seconds: int = 30,
) -> WebhookPayload:
    """Verify a QiTech webhook JWT and return tenant-scoped claims.

    Args:
        token: compact JWT from the `Authorization: Bearer <...>` header (or
            wherever QiTech places it for the given BU).
        qi_public_key_pem: QiTech's ES512 public key (per BU / per environment).
        expected_api_client_key: if provided, enforce `claims["sub"]` equals
            this value. Use when the router has already resolved the tenant
            via path / config and wants a second check. Pass `None` when the
            router wants to use `sub` for tenant lookup instead.
        leeway_seconds: tolerance for clock skew on iat/exp (default 30s).

    Returns:
        WebhookPayload with `api_client_key` and the full decoded claims dict.

    Raises:
        QiTechWebhookVerificationError: signature invalid, token expired,
            missing `sub`, or `sub` mismatch when `expected_api_client_key`
            is supplied.
    """
    claims = verify_webhook_jwt(
        token=token,
        qi_public_key_pem=qi_public_key_pem,
        leeway_seconds=leeway_seconds,
    )

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise QiTechWebhookVerificationError("webhook JWT missing 'sub' claim")

    if expected_api_client_key is not None and sub != expected_api_client_key:
        raise QiTechWebhookVerificationError(
            "webhook 'sub' does not match expected api_client_key"
        )

    return WebhookPayload(api_client_key=sub, claims=claims)
