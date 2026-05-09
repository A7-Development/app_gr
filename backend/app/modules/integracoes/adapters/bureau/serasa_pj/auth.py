"""Access token lifecycle — fetch + cache por (tenant_id, environment).

A Serasa emite Access Token via OAuth2 Client Credentials (Basic Auth).
TTL ~1h conforme campo `ExpiresIn` da resposta. O token vai como
`Authorization: Bearer <token>` em chamadas subsequentes.

Modelo: 1 credencial por tenant (sem multi-UA, ao contrario do QiTech).
A chave do cache e `(tenant_id, environment)` apenas.

Particularidades:
    - Resposta da Serasa traz `AcessToken` (sic — typo oficial), nao
      `AccessToken`. O parser tolera ambos por defesa.
    - `ExpiresIn` vem como string em segundos. Limitamos pelo teto de
      `config.token_ttl_seconds` para guardar contra valores anomalos.
    - Reciprocidade silenciosa: pedido pode ser downgrado server-side; a
      logica de detect/raise vive em client.py, nao aqui.

Thread-safety: asyncio.Lock por chave evita N requests de token em paralelo.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from uuid import UUID

import httpx

from app.core.enums import Environment
from app.modules.integracoes.adapters.bureau.serasa_pj.config import (
    SerasaPjConfig,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.endpoints import (
    E_AUTH_LOGIN,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.errors import (
    SerasaPjAuthError,
    SerasaPjConfigError,
    SerasaPjHttpError,
)

logger = logging.getLogger("gr.integracoes.serasa_pj.auth")


@dataclass(frozen=True)
class _CachedToken:
    token: str
    fetched_at: float
    expires_at: float


# Chave: (tenant_id, environment). Nao ha UA aqui — Serasa e 1-credencial-por-tenant.
_CacheKey = tuple[UUID, Environment]

_TOKEN_CACHE: dict[_CacheKey, _CachedToken] = {}
_LOCKS: dict[_CacheKey, asyncio.Lock] = {}


def _get_lock(key: _CacheKey) -> asyncio.Lock:
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock


def _is_fresh(cached: _CachedToken, *, now: float, skew: int) -> bool:
    """Whether the cached token is still usable given refresh skew."""
    return cached.expires_at - skew > now


async def get_access_token(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: SerasaPjConfig,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Retorna um Access Token valido para a tupla (tenant, environment).

    Usa cache em memoria; so chama a Serasa se o cache estiver vazio ou
    expirado (considerando `config.token_refresh_skew_seconds`).

    Raises:
        SerasaPjConfigError: faltam credenciais ou retailer_document_id.
        SerasaPjAuthError: credenciais recusadas ou resposta sem AcessToken.
        SerasaPjHttpError: falha de rede / 5xx.
    """
    key: _CacheKey = (tenant_id, environment)
    now = time.time()

    cached = _TOKEN_CACHE.get(key)
    if cached is not None and _is_fresh(
        cached, now=now, skew=config.token_refresh_skew_seconds
    ):
        return cached.token

    async with _get_lock(key):
        # Re-check apos adquirir lock — outra coroutine pode ter preenchido.
        cached = _TOKEN_CACHE.get(key)
        if cached is not None and _is_fresh(
            cached, now=time.time(), skew=config.token_refresh_skew_seconds
        ):
            return cached.token

        token, ttl_seconds = await _request_access_token(
            config=config, transport=transport
        )
        # Limita ao teto configurado para defender contra ExpiresIn anomalos.
        effective_ttl = min(ttl_seconds, config.token_ttl_seconds)
        fresh = _CachedToken(
            token=token,
            fetched_at=time.time(),
            expires_at=time.time() + effective_ttl,
        )
        _TOKEN_CACHE[key] = fresh
        logger.info(
            "serasa_pj.auth: token emitido tenant=%s env=%s ttl=%ss",
            tenant_id,
            environment.value,
            effective_ttl,
        )
        return fresh.token


async def _request_access_token(
    *,
    config: SerasaPjConfig,
    transport: httpx.AsyncBaseTransport | None,
) -> tuple[str, int]:
    """Executa o POST de login e extrai (AcessToken, ExpiresIn).

    Autenticacao: HTTP Basic com base64(client_id:client_secret) no header
    `Authorization`. Retorna tupla (token, ttl_em_segundos).

    Raises:
        SerasaPjConfigError: credenciais ausentes.
        SerasaPjAuthError: resposta 4xx ou payload sem token.
        SerasaPjHttpError: 5xx, timeout, DNS.
    """
    if not config.has_credentials():
        raise SerasaPjConfigError(
            "Serasa PJ config sem client_id/client_secret/retailer_document_id "
            "— configure o tenant antes de autenticar"
        )

    url = f"{config.base_url}{E_AUTH_LOGIN.path}"
    last_error: httpx.HTTPError | None = None
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        transport=transport,
    ) as client:
        for attempt in range(2):
            try:
                resp = await client.request(
                    E_AUTH_LOGIN.method,
                    url,
                    auth=httpx.BasicAuth(
                        config.client_id, config.client_secret
                    ),
                )
                last_error = None
                break
            except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                last_error = e
                if attempt == 0:
                    logger.warning(
                        "serasa_pj.auth: timeout transitorio em %s (%s); retry em 1s",
                        E_AUTH_LOGIN.path,
                        type(e).__name__,
                    )
                    await asyncio.sleep(1.0)
                    continue
            except httpx.HTTPError as e:
                last_error = e
                break
        if last_error is not None:
            raise SerasaPjHttpError(
                f"falha de rede ao chamar {E_AUTH_LOGIN.path}: "
                f"{type(last_error).__name__}({last_error!r})",
                status_code=None,
                detail=f"{type(last_error).__name__}: {last_error!r}",
            ) from last_error

    if resp.status_code >= 500:
        raise SerasaPjHttpError(
            f"Serasa devolveu {resp.status_code} em {E_AUTH_LOGIN.path}",
            status_code=resp.status_code,
            detail=resp.text[:500],
        )
    if resp.status_code >= 400:
        raise SerasaPjAuthError(
            f"credenciais rejeitadas ({resp.status_code}): {resp.text[:500]}"
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise SerasaPjAuthError(
            f"resposta de login nao-JSON: {resp.text[:500]}"
        ) from e

    if not isinstance(payload, dict):
        raise SerasaPjAuthError(
            f"payload de login inesperado: {type(payload).__name__}"
        )

    # Tolera 3 grafias do campo de token observadas em diferentes versoes
    # da API Serasa:
    #   - `accessToken`  (atual em prod 2026-05-01, camelCase OAuth2 padrao)
    #   - `AccessToken`  (PascalCase)
    #   - `AcessToken`   (sic — typo historico em UAT, possivelmente removido
    #                    em prod mas mantido aqui por compat)
    token = (
        payload.get("accessToken")
        or payload.get("AccessToken")
        or payload.get("AcessToken")
    )
    if not isinstance(token, str) or not token:
        raise SerasaPjAuthError(
            f"resposta sem campo de access token: chaves={list(payload)}"
        )

    expires_in_raw = (
        payload.get("expiresIn")
        or payload.get("ExpiresIn")
        or 0
    )
    try:
        expires_in = int(str(expires_in_raw))
    except (TypeError, ValueError):
        expires_in = 0
    if expires_in <= 0:
        # Sem ExpiresIn confiavel, assume default conservador.
        expires_in = 3600

    return token, expires_in


def invalidate_token(tenant_id: UUID, environment: Environment) -> None:
    """Remove o token do cache — usado pelo connection em 401."""
    _TOKEN_CACHE.pop((tenant_id, environment), None)


def _clear_cache_for_tests() -> None:
    """Utility para tests — nao exposto no __init__ publico."""
    _TOKEN_CACHE.clear()
    _LOCKS.clear()
