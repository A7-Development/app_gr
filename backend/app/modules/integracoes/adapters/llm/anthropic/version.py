"""Adapter version — recorded in decision_log + ai_usage_event for every call.

Increment per semver:
    MAJOR — breaks the AdapterCallResult contract or stream protocol.
    MINOR — adds new optional behavior (e.g. tool use support).
    PATCH — bug fix, no contract change.
"""

from __future__ import annotations

ADAPTER_VERSION = "anthropic_adapter_v1.0.0"
