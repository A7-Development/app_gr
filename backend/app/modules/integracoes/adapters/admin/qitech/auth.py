"""API token lifecycle — fetch + cache por (tenant_id, environment, ua_id).

Apesar de `/v2/painel/token/api` emitir algo que parece Bearer-OAuth, o
token e usado como header `x-api-key` em todas as chamadas subsequentes
(ver `connection.py`).

Responsabilidades:
    1. Chamar `POST {base_url}/v2/painel/token/api` com o payload de
       credenciais do tenant e extrair `apiToken` da resposta.
    2. Guardar o token em memoria com TTL, chaveado por
       (tenant_id, environment, unidade_administrativa_id). Tenants/UAs
       distintos sao isoladas — multi-UA (CLAUDE.md secao 13, 2026-04-25)
       exige que dois FIDCs do mesmo tenant tenham caches separados, ja que
       cada UA tem seu proprio par client_id+client_secret na QiTech.
       UA `None` e a chave usada por configs legacy (pre-Phase-F) — nao
       conflita com nenhuma UA real.
    3. Renovar antes da expiracao (com `token_refresh_skew_seconds` de folga).

Nao toca em I/O de banco; o estado e um dict em memoria que vive no processo
do backend. Ao reiniciar, todos os tenants refetcham — aceito para MVP.

Thread-safety: FastAPI roda requests concorrentes no mesmo event loop.
O cache usa asyncio.Lock por chave para evitar N tenants baterem o endpoint
de token em paralelo.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from uuid import UUID

import httpx

from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.endpoints import E_AUTH_TOKEN
from app.modules.integracoes.adapters.admin.qitech.errors import (
    QiTechAuthError,
    QiTechHttpError,
)

logger = logging.getLogger("gr.integracoes.qitech.auth")


@dataclass(frozen=True)
class _CachedToken:
    token: str
    fetched_at: float
    expires_at: float


# Chave: (tenant_id, environment, ua_id). Isolamento multi-tenant: o valor de
# um tenant nao e visivel nas consultas de outro. Multi-UA: dois FIDCs do
# mesmo tenant tem credenciais distintas e portanto tokens distintos.
_CacheKey = tuple[UUID, Environment, UUID | None]

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


async def get_api_token(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    transport: httpx.AsyncBaseTransport | None = None,
    unidade_administrativa_id: UUID | None = None,
) -> str:
    """Retorna um token valido para a tupla (tenant, environment, ua).

    Usa cache em memoria; so chama a QiTech se o cache estiver vazio ou
    expirado (considerando `config.token_refresh_skew_seconds`).

    Args:
        tenant_id: UUID do tenant dono do token.
        environment: sandbox ou production — caches separados por ambiente.
        config: config ja materializada a partir de tenant_source_config.
        transport: override opcional (tests via MockTransport).
        unidade_administrativa_id: UA dona desta credencial. Multi-UA exige
            cache separado porque cada UA tem seu proprio par client_id+
            client_secret na QiTech. None mantem retrocompat com configs
            legacy pre-Phase-F.

    Raises:
        QiTechAuthError: credenciais recusadas ou resposta sem `apiToken`.
        QiTechHttpError: falha de rede / 5xx.
    """
    key: _CacheKey = (tenant_id, environment, unidade_administrativa_id)
    now = time.time()

    cached = _TOKEN_CACHE.get(key)
    if cached is not None and _is_fresh(
        cached, now=now, skew=config.token_refresh_skew_seconds
    ):
        return cached.token

    # Serializa concorrentes sobre a mesma chave — evita N requests de
    # token em paralelo quando o cache expira sob carga.
    async with _get_lock(key):
        # Re-check: outra coroutine pode ter preenchido enquanto esperavamos.
        cached = _TOKEN_CACHE.get(key)
        if cached is not None and _is_fresh(
            cached, now=time.time(), skew=config.token_refresh_skew_seconds
        ):
            return cached.token

        token = await _request_token(config=config, transport=transport)
        fresh = _CachedToken(
            token=token,
            fetched_at=time.time(),
            expires_at=time.time() + config.token_ttl_seconds,
        )
        _TOKEN_CACHE[key] = fresh
        logger.info(
            "qitech.auth: token emitido tenant=%s env=%s ua=%s ttl=%ss",
            tenant_id,
            environment.value,
            unidade_administrativa_id,
            config.token_ttl_seconds,
        )
        return fresh.token


async def _request_token(
    *,
    config: QiTechConfig,
    transport: httpx.AsyncBaseTransport | None,
) -> str:
    """Executa o POST de autenticacao e extrai `apiToken`.

    Autenticacao: HTTP Basic com base64(client_id:client_secret) no header
    `Authorization`, conforme doc Singulare/QiTech em
    https://api-portal.singulare.com.br/painel/token/api.

    Mantido async e isolado para facilitar teste com MockTransport.
    """
    if not config.has_credentials():
        raise QiTechAuthError(
            "QiTech config sem client_id/client_secret — configure o tenant antes "
            "de autenticar"
        )

    url = f"{config.base_url}{E_AUTH_TOKEN.path}"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        transport=transport,
    ) as client:
        try:
            resp = await client.request(
                E_AUTH_TOKEN.method,
                url,
                auth=httpx.BasicAuth(config.client_id, config.client_secret),
            )
        except httpx.HTTPError as e:
            # {e} de varias httpx exceptions stringifica vazio ("''") — incluir
            # o tipo ajuda a diferenciar ConnectTimeout vs ReadTimeout vs
            # ConnectError sem precisar de traceback.
            raise QiTechHttpError(
                f"falha de rede ao chamar {E_AUTH_TOKEN.path}: "
                f"{type(e).__name__}({e!r})",
                status_code=None,
                detail=f"{type(e).__name__}: {e!r}",
            ) from e

    if resp.status_code >= 500:
        raise QiTechHttpError(
            f"QiTech devolveu {resp.status_code} em {E_AUTH_TOKEN.path}",
            status_code=resp.status_code,
            detail=resp.text[:500],
        )
    if resp.status_code >= 400:
        raise QiTechAuthError(
            f"credenciais rejeitadas ({resp.status_code}): {resp.text[:500]}"
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise QiTechAuthError(
            f"resposta de token nao-JSON: {resp.text[:500]}"
        ) from e

    token = payload.get("apiToken") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise QiTechAuthError(
            f"resposta sem campo 'apiToken': chaves={list(payload) if isinstance(payload, dict) else type(payload).__name__}"
        )
    return token


def invalidate_token(
    tenant_id: UUID,
    environment: Environment,
    unidade_administrativa_id: UUID | None = None,
) -> None:
    """Remove o token do cache — usado pelo connection em 401."""
    _TOKEN_CACHE.pop((tenant_id, environment, unidade_administrativa_id), None)


def _clear_cache_for_tests() -> None:
    """Utility para tests — nao exposto no __init__ publico."""
    _TOKEN_CACHE.clear()
    _LOCKS.clear()
