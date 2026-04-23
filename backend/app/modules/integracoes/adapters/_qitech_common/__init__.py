"""QiTech shared primitives — BU-agnostic foundation.

Shared across all QiTech BU adapters (custody, banking, lending, kyc).
Each BU adapter composes these primitives; none of them lives inside a BU.

Contents:
    errors            — typed exceptions raised by the shared primitives.
    pem_utils         — load / validate ECDSA P-521 PEM keys.
    signer            — ES512 sign_request_jwt / verify_webhook_jwt (pure).
    http_client       — async httpx client with signer injection.
    webhook_verifier  — facade to authenticate inbound webhooks.

Public API: import from this package only — internal helpers are not re-exported.
"""

from app.modules.integracoes.adapters._qitech_common.errors import (
    QiTechAuthError,
    QiTechError,
    QiTechSigningError,
    QiTechWebhookVerificationError,
)
from app.modules.integracoes.adapters._qitech_common.http_client import (
    build_async_client,
)
from app.modules.integracoes.adapters._qitech_common.pem_utils import (
    load_private_key,
    load_public_key,
)
from app.modules.integracoes.adapters._qitech_common.signer import (
    sign_request_jwt,
    verify_webhook_jwt,
)
from app.modules.integracoes.adapters._qitech_common.webhook_verifier import (
    WebhookPayload,
    verify_inbound_webhook,
)

__all__ = [
    "QiTechAuthError",
    "QiTechError",
    "QiTechSigningError",
    "QiTechWebhookVerificationError",
    "WebhookPayload",
    "build_async_client",
    "load_private_key",
    "load_public_key",
    "sign_request_jwt",
    "verify_inbound_webhook",
    "verify_webhook_jwt",
]
