"""Cliente HTTP da API SERPRO Consulta NF-e.

Fluxo OAuth2 client_credentials:

    POST {token_url}
        Authorization: Basic base64(consumer_key:consumer_secret)
        body: grant_type=client_credentials
    -> {"access_token": "...", "expires_in": 3295, ...}

Token cacheado em memoria ate `expires_in - 60s`; renovado sob demanda.
O ambiente trial usa bearer estatico (sem OAuth) — passe `static_token`.

Consulta:

    GET {base_url}/v1/nfe/{chave}
        Authorization: Bearer <token>
        Accept: application/json
        x-request-tag: <rateio por tenant, max 32 chars>  (opcional)

GOTCHA da API: campos numericos vem como JSON number e valores grandes
podem chegar em NOTACAO CIENTIFICA. O parse usa `parse_float=Decimal`
para nao perder precisao — NUNCA re-parsear o body com float ingenuo.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from app.modules.integracoes.adapters.data.serpro.config import SerproConfig
from app.modules.integracoes.adapters.data.serpro.errors import (
    SerproAuthError,
    SerproHttpError,
    SerproInvalidKeyError,
    SerproNotFoundError,
    SerproPayloadError,
    SerproThrottledError,
    SerproWrongPathError,
)

_TOKEN_SAFETY_MARGIN_S = 60.0
_CHAVE_LEN = 44


@dataclass(slots=True)
class SerproNfeResponse:
    """Resposta normalizada de GET /v1/nfe/{chave}."""

    chave: str
    raw: dict[str, Any]
    # Body EXATO da resposta — o bronze persiste este texto via CAST(jsonb)
    # para nao perder precisao numerica em round-trip por float do Python.
    text: str
    http_status: int
    latency_ms: float
    request_tag: str | None = None

    @property
    def nfe_proc(self) -> dict[str, Any]:
        proc = self.raw.get("nfeProc")
        return proc if isinstance(proc, dict) else {}

    @property
    def prot_nfe(self) -> dict[str, Any]:
        """infProt do protocolo (cStat/xMotivo/nProt/dhRecbto)."""
        prot = self.nfe_proc.get("protNFe")
        inf = prot.get("infProt") if isinstance(prot, dict) else None
        return inf if isinstance(inf, dict) else {}

    @property
    def cstat(self) -> int | None:
        value = self.prot_nfe.get("cStat")
        if value is None:
            return None
        return int(value)

    @property
    def eventos(self) -> list[dict[str, Any]]:
        """Lista de eventos (vazia quando a nota nao tem eventos).

        A API REAL retorna a chave `procEventoNFe` (singular, null quando
        sem eventos) — a spec OpenAPI documenta `procEventosNFe` (plural).
        Validado contra o trial em 2026-07-10; aceitamos ambas.
        """
        eventos = self.raw.get("procEventoNFe") or self.raw.get("procEventosNFe")
        return eventos if isinstance(eventos, list) else []


@dataclass
class SerproClient:
    """Cliente com cache de bearer token. Um por (credencial, base_url)."""

    config: SerproConfig
    # Trial/demonstracao: bearer estatico, pula o fluxo OAuth.
    static_token: str | None = None
    # Injetavel em teste (httpx.MockTransport); None = rede real.
    transport: httpx.AsyncBaseTransport | None = None

    _client: httpx.AsyncClient | None = field(default=None, repr=False)
    _token: str | None = field(default=None, repr=False)
    _token_expires_at: float = field(default=0.0, repr=False)

    async def __aenter__(self) -> SerproClient:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.timeout_s, connect=10.0),
            headers={"Accept": "application/json"},
            transport=self.transport,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("SerproClient usado fora de `async with`.")
        return self._client

    async def _bearer_token(self) -> str:
        """Retorna token valido, renovando via OAuth quando expirado."""
        if self.static_token:
            return self.static_token
        now = time.monotonic()
        if self._token and now < self._token_expires_at:
            return self._token

        basic = base64.b64encode(
            f"{self.config.consumer_key}:{self.config.consumer_secret}".encode()
        ).decode()
        resp = await self._http().post(
            self.config.token_url,
            data={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        if resp.status_code in (400, 401, 403):
            raise SerproAuthError(
                f"Falha ao obter token (HTTP {resp.status_code})."
            )
        if resp.status_code >= 400:
            raise SerproHttpError(resp.status_code, "token endpoint")

        try:
            payload = resp.json()
            token = str(payload["access_token"])
            expires_in = float(payload.get("expires_in") or 3300)
        except (ValueError, KeyError) as e:
            raise SerproPayloadError("Resposta do /token fora do contrato.") from e

        self._token = token
        self._token_expires_at = (
            time.monotonic() + expires_in - _TOKEN_SAFETY_MARGIN_S
        )
        return token

    async def consulta_nfe(
        self, chave: str, *, request_tag: str | None = None
    ) -> SerproNfeResponse:
        """GET /v1/nfe/{chave} -- nota + protocolo + eventos.

        Args:
            chave: chave de acesso (44 digitos, sem espacos).
            request_tag: valor do header `x-request-tag` (rateio na fatura
                SERPRO, max 32 chars). Convencao: slug do tenant.

        Raises:
            SerproInvalidKeyError / SerproNotFoundError / SerproAuthError /
            SerproWrongPathError / SerproHttpError / SerproPayloadError.
        """
        chave = chave.strip()
        if len(chave) != _CHAVE_LEN:
            raise SerproInvalidKeyError(
                f"Chave deve ter {_CHAVE_LEN} caracteres (veio {len(chave)})."
            )

        token = await self._bearer_token()
        headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
        if request_tag:
            headers["x-request-tag"] = request_tag[:32]

        started = time.monotonic()
        resp = await self._http().get(
            f"{self.config.base_url}/v1/nfe/{chave}", headers=headers
        )
        latency_ms = round((time.monotonic() - started) * 1000.0, 1)

        if resp.status_code == 400:
            raise SerproInvalidKeyError(f"Chave invalida: {chave}")
        if resp.status_code == 401:
            # Token pode ter sido revogado no gateway antes do expires_in
            # local — invalida o cache pra proxima chamada renovar.
            self._token = None
            raise SerproAuthError("HTTP 401 na consulta (token rejeitado).")
        if resp.status_code == 403:
            raise SerproWrongPathError(
                f"HTTP 403 em {self.config.base_url} — confira o plano "
                "(df vs escalonado) da credencial."
            )
        if resp.status_code == 404:
            raise SerproNotFoundError(f"NF-e nao encontrada: {chave}")
        if resp.status_code == 429:
            raise SerproThrottledError(f"Quota excedida no gateway ({chave}).")
        if resp.status_code >= 400:
            raise SerproHttpError(resp.status_code, resp.text)

        try:
            # parse_float=Decimal: valores grandes podem vir em notacao
            # cientifica — float perderia precisao em valores monetarios.
            payload = json.loads(resp.text, parse_float=Decimal)
        except ValueError as e:
            raise SerproPayloadError(f"Resposta nao-JSON para {chave}.") from e
        if not isinstance(payload, dict) or "nfeProc" not in payload:
            raise SerproPayloadError(
                f"Shape inesperado para {chave}: sem 'nfeProc'."
            )

        return SerproNfeResponse(
            chave=chave,
            raw=payload,
            text=resp.text,
            http_status=resp.status_code,
            latency_ms=latency_ms,
            request_tag=request_tag,
        )

    async def status(self) -> bool:
        """GET /v1/nfe/status -- health check (sem custo)."""
        token = await self._bearer_token()
        resp = await self._http().get(
            f"{self.config.base_url}/v1/nfe/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp.status_code == 200
