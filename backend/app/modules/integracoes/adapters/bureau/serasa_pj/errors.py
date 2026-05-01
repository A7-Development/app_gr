"""Excecoes tipadas do adapter Serasa PJ.

Camada dedicada para que callers distingam "credencial recusada" de
"erro de rede" de "downgrade de reciprocidade" de "config invalida".
O router de sources captura a base (`SerasaPjAdapterError`) e devolve
detalhe para a UI.
"""

from __future__ import annotations


class SerasaPjAdapterError(Exception):
    """Base para qualquer falha no adapter Serasa PJ."""


class SerasaPjConfigError(SerasaPjAdapterError):
    """Config invalida — falta client_id, client_secret ou retailer_document_id.

    Levantado antes de qualquer chamada de rede. Diferente de
    `SerasaPjAuthError` (credenciais validas mas recusadas pelo bureau).
    """


class SerasaPjAuthError(SerasaPjAdapterError):
    """Credenciais rejeitadas ou token nao emitido.

    Gerado quando o endpoint de login responde 4xx OU quando a resposta
    nao traz `AcessToken` (sic — typo da Serasa) no payload esperado.
    """


class SerasaPjHttpError(SerasaPjAdapterError):
    """Erro HTTP nao relacionado a auth (5xx, timeout, DNS).

    Carrega `status_code` (int | None) e `detail` com a resposta bruta
    truncada para debug, sem vazar credenciais.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class SerasaPjReciprocityDowngradeError(SerasaPjAdapterError):
    """Reciprocidade A7 quebrou — Serasa devolveu relatorio sintetico em vez de analitico.

    Nao e um erro fatal; o caller pode optar por aceitar o sintetico ou
    abortar. Carrega `requested` (o que pedimos) e `received` (o que veio).

    Detectado pos-resposta no client.py comparando `reportName` no body
    enviado vs no body retornado.
    """

    def __init__(
        self,
        message: str,
        *,
        requested: str,
        received: str,
    ) -> None:
        super().__init__(message)
        self.requested = requested
        self.received = received
