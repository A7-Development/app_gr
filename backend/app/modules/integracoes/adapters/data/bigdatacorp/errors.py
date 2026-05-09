"""Excecoes tipadas do adapter BigDataCorp.

Hierarquia mirror do Serasa PJ — caller distingue config/auth/HTTP/payload.
Router de admin captura a base e devolve detalhe pra UI.
"""

from __future__ import annotations


class BigDataCorpAdapterError(Exception):
    """Base para qualquer falha no adapter BigDataCorp."""


class BigDataCorpConfigError(BigDataCorpAdapterError):
    """Config invalida — credencial vazia, formato errado, etc.

    Levantado antes de qualquer chamada de rede. Distinto de
    `BigDataCorpAuthError` (credencial valida em formato, mas recusada pelo
    vendor).
    """


class BigDataCorpAuthError(BigDataCorpAdapterError):
    """Credenciais rejeitadas pelo BDC.

    Detectado em respostas com `Status` indicando erro de auth (BDC nao
    devolve 401 puro — encapsula em payload aplicacional). Tambem cobre
    casos onde header obrigatorio falta.
    """


class BigDataCorpHttpError(BigDataCorpAdapterError):
    """Erro HTTP (5xx, timeout, DNS, 4xx nao-auth).

    Carrega `status_code` (int | None) e `detail` com a resposta truncada
    para debug. Nunca inclui credenciais (filtragem feita no client).
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


class BigDataCorpPayloadError(BigDataCorpAdapterError):
    """Resposta com shape inesperado (nao e dict, falta campo obrigatorio, etc).

    Usado pelo pricing_sync quando o /precos/ devolve estrutura que nao bate
    com o contrato documentado. Sinaliza quebra de contrato do vendor — a
    correcao e atualizar o parser, nao tentar de novo.
    """
