"""Exceptions do adapter SERPRO Consulta NF-e.

Mapa dos HTTP codes da API (documentacao oficial, 2026-07):
    400 -> chave invalida (SerproInvalidKeyError)
    401 -> falha de autenticacao (SerproAuthError)
    403 -> caminho/plano errado, NAO permissao (SerproWrongPathError)
    404 -> NF-e inexistente para a chave (SerproNotFoundError)
    406 -> formato de saida invalido (SerproPayloadError)
    5xx -> erro do servidor/gateway (SerproHttpError)

Apenas HTTP 200 e cobrado pelo SERPRO — erros nao geram custo.
"""

from __future__ import annotations


class SerproError(Exception):
    """Base de todos os erros do adapter SERPRO."""


class SerproAuthError(SerproError):
    """401 -- consumer key/secret invalidos ou bearer token expirado/errado."""


class SerproWrongPathError(SerproError):
    """403 -- caminho incorreto (pegadinha da API: nao e permissao).

    Quase sempre significa que o plano configurado (df vs escalonado) nao
    bate com o contratado — a base URL muda por plano.
    """


class SerproInvalidKeyError(SerproError):
    """400 -- a chave de acesso informada nao e valida (formato/digito)."""


class SerproNotFoundError(SerproError):
    """404 -- nao existe NF-e com a chave informada."""


class SerproThrottledError(SerproError):
    """429 -- quota/rate limit excedido no gateway ("Message throttled out").

    Observado no trial em 2026-07-10 (burst de ~4 chamadas). Caller deve
    aplicar backoff e retentar — a chamada nao foi cobrada.
    """


class SerproHttpError(SerproError):
    """Demais erros HTTP (406, 408, 5xx)."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {detail[:200]}")


class SerproPayloadError(SerproError):
    """Resposta 200 mas payload fora do contrato (nao-JSON, sem nfeProc)."""
