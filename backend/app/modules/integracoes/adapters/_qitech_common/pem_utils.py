"""Load and validate ECDSA P-521 PEM keys used by the QiTech signer.

QiTech requires ES512 (ECDSA over the NIST P-521 curve with SHA-512). Other
curves must be rejected early — otherwise `jwt.encode` accepts them and the
API later returns an opaque 401.
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import (
    EllipticCurvePrivateKey,
    EllipticCurvePublicKey,
)

from app.modules.integracoes.adapters._qitech_common.errors import QiTechSigningError

# Canonical curve required by QiTech (RFC 7518 §3.4 — ES512 = P-521 + SHA-512).
_REQUIRED_CURVE = ec.SECP521R1


def load_private_key(pem: str) -> EllipticCurvePrivateKey:
    """Parse a PEM-encoded ECDSA P-521 private key.

    Raises:
        QiTechSigningError: if the PEM is malformed, encrypted, or uses a
            different curve/algorithm.
    """
    try:
        key = serialization.load_pem_private_key(
            pem.encode("utf-8") if isinstance(pem, str) else pem,
            password=None,
        )
    except (ValueError, TypeError) as e:
        raise QiTechSigningError(f"invalid private PEM: {e}") from e

    if not isinstance(key, EllipticCurvePrivateKey):
        raise QiTechSigningError(
            f"private key must be ECDSA (got {type(key).__name__})"
        )
    if not isinstance(key.curve, _REQUIRED_CURVE):
        raise QiTechSigningError(
            f"private key must be on curve P-521 (got {key.curve.name})"
        )
    return key


def load_public_key(pem: str) -> EllipticCurvePublicKey:
    """Parse a PEM-encoded ECDSA P-521 public key.

    Raises:
        QiTechSigningError: if the PEM is malformed or uses a different
            curve/algorithm.
    """
    try:
        key = serialization.load_pem_public_key(
            pem.encode("utf-8") if isinstance(pem, str) else pem,
        )
    except (ValueError, TypeError) as e:
        raise QiTechSigningError(f"invalid public PEM: {e}") from e

    if not isinstance(key, EllipticCurvePublicKey):
        raise QiTechSigningError(
            f"public key must be ECDSA (got {type(key).__name__})"
        )
    if not isinstance(key.curve, _REQUIRED_CURVE):
        raise QiTechSigningError(
            f"public key must be on curve P-521 (got {key.curve.name})"
        )
    return key
