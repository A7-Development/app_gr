"""QiTechConfig.from_dict — defaults, normalizacao, validacao."""

from __future__ import annotations

import pytest

from app.modules.integracoes.adapters.admin.qitech.config import (
    DEFAULT_BASE_URL,
    DEFAULT_TOKEN_TTL_SECONDS,
    QiTechConfig,
)


def test_from_dict_applies_defaults() -> None:
    cfg = QiTechConfig.from_dict(
        {"client_id": "x", "client_secret": "y"}
    )
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.token_ttl_seconds == DEFAULT_TOKEN_TTL_SECONDS
    assert cfg.client_id == "x"
    assert cfg.client_secret == "y"
    assert cfg.has_credentials()


def test_from_dict_strips_trailing_slash() -> None:
    cfg = QiTechConfig.from_dict(
        {
            "base_url": "https://api.test/",
            "client_id": "id",
            "client_secret": "secret",
        }
    )
    assert cfg.base_url == "https://api.test"


def test_from_dict_allows_empty_for_draft_configs() -> None:
    # UI pode salvar so a base_url antes de preencher credenciais.
    # Erro so ocorre na hora de autenticar (get_api_token).
    cfg = QiTechConfig.from_dict({"base_url": "https://x"})
    assert cfg.client_id == ""
    assert cfg.client_secret == ""
    assert not cfg.has_credentials()


def test_from_dict_accepts_legacy_credentials_dict() -> None:
    # Retrocompat: configs gravadas antes de 2026-04-24 usavam `credentials`.
    cfg = QiTechConfig.from_dict(
        {"credentials": {"client_id": "legacy-id", "client_secret": "legacy-secret"}}
    )
    assert cfg.client_id == "legacy-id"
    assert cfg.client_secret == "legacy-secret"


def test_from_dict_top_level_wins_over_legacy() -> None:
    # Se as duas formas coexistirem, `client_id` / `client_secret` top-level
    # ganham — o envelope recem-gravado sobrescreve o legacy.
    cfg = QiTechConfig.from_dict(
        {
            "credentials": {"client_id": "old", "client_secret": "old"},
            "client_id": "new",
            "client_secret": "new",
        }
    )
    assert cfg.client_id == "new"
    assert cfg.client_secret == "new"


def test_from_dict_rejects_non_string_client_id() -> None:
    with pytest.raises(ValueError, match="client_id"):
        QiTechConfig.from_dict({"client_id": 42, "client_secret": "x"})
