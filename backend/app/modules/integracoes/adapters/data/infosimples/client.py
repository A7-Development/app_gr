"""Cliente HTTP da API Infosimples (api.infosimples.com).

Contrato da API v2 (padrão Infosimples):

    POST {base_url}/api/v2/consultas/{consulta_path}
    body (form): token=<api_key>&timeout=<s>&<params...>

    Response JSON:
    {
      "code": 200,                # aplicacional: 200=ok; 6xx falha de consulta
      "code_message": "...",
      "data": [...],              # resultados (lista; consultas single = [0])
      "data_count": 1,
      "errors": [...],
      "site_receipts": ["https://..."],   # PDFs/comprovantes gerados
      "header": {...}             # parâmetros ecoados, billing etc.
    }

O `consulta_path` NÃO é hardcoded aqui — vem de
`provedor_dados_dataset.provider_query_name` (curado no DB), então um path
divergente da doc se corrige com UPDATE, sem deploy.

PII: o body do request carrega logins de portal (JUCESP) — NUNCA logar o
body nem persisti-lo no bronze (o bronze guarda só o RESPONSE).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.modules.integracoes.adapters.data.infosimples.errors import (
    InfosimplesAuthError,
    InfosimplesHttpError,
    InfosimplesPayloadError,
)

_AUTH_CODES = {401, 403}


@dataclass(slots=True)
class InfosimplesResponse:
    """Resposta normalizada de uma consulta."""

    code: int
    code_message: str
    data: list[Any] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)
    site_receipts: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    http_status: int = 200
    latency_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.code == 200

    @property
    def first(self) -> dict[str, Any] | None:
        item = self.data[0] if self.data else None
        return item if isinstance(item, dict) else None


def build_async_client(*, base_url: str, timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(timeout_s, connect=10.0),
        headers={"Accept": "application/json"},
    )


async def consulta(
    client: httpx.AsyncClient,
    *,
    path: str,
    api_key: str,
    params: dict[str, Any],
    timeout_s: float = 60.0,
) -> InfosimplesResponse:
    """Executa uma consulta. `path` ex.: "junta-comercial/sp/completa"."""
    body: dict[str, Any] = {
        "token": api_key,
        "timeout": int(timeout_s),
        **{k: v for k, v in params.items() if v is not None},
    }
    started = time.monotonic()
    resp = await client.post(f"/api/v2/consultas/{path.strip('/')}", data=body)
    latency_ms = (time.monotonic() - started) * 1000.0

    if resp.status_code in _AUTH_CODES:
        raise InfosimplesAuthError(f"HTTP {resp.status_code} em {path}")
    if resp.status_code >= 400:
        raise InfosimplesHttpError(resp.status_code, resp.text)

    try:
        payload = resp.json()
    except ValueError as e:  # pragma: no cover - vendor fora do contrato
        raise InfosimplesPayloadError(f"Resposta não-JSON em {path}") from e
    if not isinstance(payload, dict) or "code" not in payload:
        raise InfosimplesPayloadError(f"Shape inesperado em {path}: sem 'code'")

    data = payload.get("data")
    receipts = payload.get("site_receipts")
    errors = payload.get("errors")
    return InfosimplesResponse(
        code=int(payload.get("code") or 0),
        code_message=str(payload.get("code_message") or ""),
        data=data if isinstance(data, list) else ([data] if data else []),
        errors=errors if isinstance(errors, list) else [],
        site_receipts=receipts if isinstance(receipts, list) else [],
        raw=payload,
        http_status=resp.status_code,
        latency_ms=round(latency_ms, 1),
    )


async def download_binary(
    client: httpx.AsyncClient, url: str, *, max_bytes: int = 30 * 1024 * 1024
) -> tuple[bytes, str | None]:
    """Baixa um binário (PDF de documento/comprovante). Retorna (bytes, mime)."""
    resp = await client.get(url, follow_redirects=True)
    if resp.status_code >= 400:
        raise InfosimplesHttpError(resp.status_code, f"download {url}")
    content = resp.content
    if len(content) > max_bytes:
        raise InfosimplesPayloadError(
            f"Download excede {max_bytes} bytes ({len(content)})."
        )
    return content, resp.headers.get("content-type")
