"""System-health guard: bearer-token auth para endpoints de monitoramento.

Diferente do `require_system_maintainer`, este guard NAO depende de JWT/principal
— eh acessivel sem login. Use APENAS em endpoints publicos read-only de
observabilidade que precisam ser chamados por sistemas externos sem VPN
(rotinas Anthropic Cloud, uptime monitors, dashboards externos).

Compor no endpoint:

    @router.get("/api/v1/system/endpoint-sync-status")
    async def endpoint_sync_status(
        _: None = Depends(require_system_health_token),
        ...
    ):
        ...

Configuracao:
    - Setar `SYSTEM_HEALTH_TOKEN` no .env (gerar com `secrets.token_hex(32)`).
    - Vazio/None: endpoint retorna 503 Service Unavailable
      (token nao configurado — mais informativo que 401 generico).
    - Caller manda `Authorization: Bearer <token>`.

Comparacao usa `secrets.compare_digest` (constant-time, evita timing attack).
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


async def require_system_health_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Valida Bearer token contra `SYSTEM_HEALTH_TOKEN` do .env.

    503 se token nao configurado no servidor (operador esqueceu de setar).
    401 se header ausente, malformado, ou token errado.
    """
    if not settings.SYSTEM_HEALTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SYSTEM_HEALTH_TOKEN nao configurado no servidor.",
        )

    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization Bearer token requerido.",
        )

    provided = authorization[len("Bearer ") :].strip()
    if not secrets.compare_digest(provided, settings.SYSTEM_HEALTH_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido.",
        )
