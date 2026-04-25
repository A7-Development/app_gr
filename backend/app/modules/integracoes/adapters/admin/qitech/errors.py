"""Typed exceptions raised by the QiTech adapter.

Camada de erro dedicada para que callers distingam "erro de autenticacao"
de "erro de rede" de "erro de contrato". O router de sources captura a
base (`QiTechAdapterError`) e devolve detalhe para a UI.
"""

from __future__ import annotations


class QiTechAdapterError(Exception):
    """Base para qualquer falha no adapter QiTech."""


class QiTechAuthError(QiTechAdapterError):
    """Credenciais rejeitadas ou token nao emitido.

    Gerado quando o endpoint de token responde 4xx OU quando a resposta
    nao traz `apiToken` no payload esperado.
    """


class QiTechHttpError(QiTechAdapterError):
    """Erro HTTP nao relacionado a auth (5xx, timeout, DNS).

    Carrega `status_code` (int | None) e `detail` com a resposta bruta
    truncada para debug, sem vazar credenciais.
    """

    def __init__(
        self, message: str, *, status_code: int | None = None, detail: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
