"""Swagger/ReDoc/OpenAPI devem ficar DESLIGADOS em producao.

A API e publica atras do gateway (callback.strataai.com.br) — o schema
OpenAPI completo e mapa de reconhecimento pra atacante. `app.main` decide
no import a partir de `APP_ENV`, entao o teste recarrega o modulo com o
env de producao e restaura o estado original no final.
"""

import importlib

import app.main as main_module
from app.core.config import get_settings


def test_docs_desligados_em_producao(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        reloaded = importlib.reload(main_module)
        assert reloaded.app.docs_url is None
        assert reloaded.app.redoc_url is None
        assert reloaded.app.openapi_url is None
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        importlib.reload(main_module)


def test_docs_ligados_fora_de_producao():
    """No ambiente de teste/dev o app atual mantem as docs ativas."""
    assert main_module.app.docs_url == "/docs"
    assert main_module.app.openapi_url == "/openapi.json"
