"""ES512 JWT sign/verify — QiTech request & webhook authentication.

Pure functions. No I/O, no globals — `now` is injectable for tests.

Outbound request claims (per QiTech developer docs):
    iss         api_client_key (tenant UUID na QiTech)
    sub         api_client_key (mesmo valor; QiTech espera presenca explicita)
    iat         unix timestamp da emissao
    exp         iat + TTL (default 60s — QiTech rejeita tokens velhos)
    md5         md5 hex do body JSON canonicalizado (sempre '{}' quando body=None)

Webhook verification:
    Inbound claim `sub` precisa bater com o `api_client_key` esperado para
    aquele tenant. O caller (webhook_verifier) aplica essa regra; este
    modulo so valida assinatura + expiracao + estrutura.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError

from app.modules.integracoes.adapters._qitech_common.errors import (
    QiTechSigningError,
    QiTechWebhookVerificationError,
)
from app.modules.integracoes.adapters._qitech_common.pem_utils import (
    load_private_key,
    load_public_key,
)

ALGORITHM = "ES512"
DEFAULT_TTL_SECONDS = 60


def _canonical_body(body: dict | None) -> str:
    """Serialize body for hashing — stable key order + no whitespace."""
    if body is None:
        return "{}"
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def sign_request_jwt(
    *,
    api_client_key: str,
    private_key_pem: str,
    body: dict | None = None,
    now: datetime | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Produce the `Authorization: Bearer <jwt>` token for a QiTech request.

    Args:
        api_client_key: tenant UUID on QiTech (iss + sub).
        private_key_pem: tenant's ECDSA P-521 private key as PEM text.
        body: JSON body of the outbound request. For GET, pass None.
        now: injectable current time (UTC) — tests pass a fixed value.
        ttl_seconds: token lifetime in seconds (default 60).

    Raises:
        QiTechSigningError: if the PEM is invalid or the underlying crypto
            library refuses to sign.
    """
    if not api_client_key:
        raise QiTechSigningError("api_client_key must be non-empty")

    private_key = load_private_key(private_key_pem)

    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)

    claims: dict[str, Any] = {
        "iss": api_client_key,
        "sub": api_client_key,
        "iat": int(moment.timestamp()),
        "exp": int((moment + timedelta(seconds=ttl_seconds)).timestamp()),
        "md5": _md5_hex(_canonical_body(body)),
    }
    try:
        return jwt.encode(claims, private_key, algorithm=ALGORITHM)
    except (TypeError, ValueError) as e:  # pragma: no cover — guarded by pem_utils
        raise QiTechSigningError(f"failed to sign JWT: {e}") from e


def verify_webhook_jwt(
    *,
    token: str,
    qi_public_key_pem: str,
    leeway_seconds: int = 30,
) -> dict[str, Any]:
    """Validate an inbound webhook JWT's signature + temporal claims.

    Returns the decoded claims dict for the caller to inspect `sub` etc.

    Args:
        token: compact JWT string.
        qi_public_key_pem: QiTech's public ECDSA P-521 key (signer side).
        leeway_seconds: tolerance for clock skew on iat/exp.

    Raises:
        QiTechWebhookVerificationError: if signature is invalid, token is
            expired beyond leeway, or the algorithm does not match.
    """
    if not token:
        raise QiTechWebhookVerificationError("empty token")

    public_key = load_public_key(qi_public_key_pem)
    try:
        return jwt.decode(
            token,
            public_key,
            algorithms=[ALGORITHM],
            leeway=leeway_seconds,
            options={"require": ["iat", "exp"]},
        )
    except InvalidTokenError as e:
        raise QiTechWebhookVerificationError(str(e)) from e
