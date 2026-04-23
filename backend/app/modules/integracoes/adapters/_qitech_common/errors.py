"""Typed exceptions raised by the QiTech shared primitives.

Callers in BU adapters catch the narrow subclasses; `QiTechError` is the
base for "any QiTech integration failure" when a broader catch is desired.
"""

from __future__ import annotations


class QiTechError(Exception):
    """Base class for all QiTech integration failures."""


class QiTechSigningError(QiTechError):
    """Raised when sign_request_jwt fails (bad PEM, bad claims, crypto error)."""


class QiTechAuthError(QiTechError):
    """Raised when an outbound response surfaces an authentication error.

    QiTech typically returns 401 with a structured body when the JWT is
    rejected. HTTP client wraps those for callers.
    """


class QiTechWebhookVerificationError(QiTechError):
    """Raised when an inbound webhook JWT fails signature / claim checks."""
