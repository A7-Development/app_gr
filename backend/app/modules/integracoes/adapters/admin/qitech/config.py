"""QiTechConfig: parametros de integracao lidos de `tenant_source_config.config`.

Cada tenant tem seu proprio contrato com a QiTech — base_url, credenciais
(client_id + client_secret) e (opcionalmente) lifetime do token. O adapter
recebe o dict decifrado do envelope e materializa essa dataclass; zero leitura
de variavel de ambiente.

Auth model: OAuth2 Client Credentials via HTTP Basic Authentication.
    POST {base_url}/v2/painel/token/api
    Header: Authorization: Basic base64(client_id:client_secret)
    Response: { "apiToken": "..." }
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BASE_URL = "https://api-portal.singulare.com.br"
# Margem de seguranca para trocar o token antes de expirar (em segundos).
# Muitas APIs emitem tokens de 1h; 60s de folga evita race condition na virada.
DEFAULT_TOKEN_TTL_SECONDS = 3600
DEFAULT_TOKEN_REFRESH_SKEW_SECONDS = 60


@dataclass(frozen=True)
class QiTechConfig:
    """Config por tenant para o adapter QiTech.

    Attributes:
        base_url: URL raiz da API QiTech. Cada tenant pode apontar para
            producao ou homologacao independentemente.
        client_id: identificador emitido pela QiTech ao tenant. Vai no
            Basic Auth do request de token.
        client_secret: secret correspondente ao client_id. Tratado como
            credencial sensivel (cifrada em rest via envelope).
        token_ttl_seconds: quanto tempo o token permanece no cache antes
            do refresh forcado. Override so se a QiTech confirmar TTL
            diferente para o tenant.
        token_refresh_skew_seconds: janela de folga antes da expiracao para
            disparar refresh antecipado.
    """

    base_url: str = DEFAULT_BASE_URL
    client_id: str = ""
    client_secret: str = ""
    token_ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS
    token_refresh_skew_seconds: int = DEFAULT_TOKEN_REFRESH_SKEW_SECONDS

    def has_credentials(self) -> bool:
        """True quando client_id e client_secret estao ambos preenchidos."""
        return bool(self.client_id) and bool(self.client_secret)

    @classmethod
    def from_dict(cls, data: dict) -> QiTechConfig:
        """Materializa a config a partir do dict decifrado do envelope.

        Aceita base_url sem credenciais (draft configs). A validacao de
        presenca das credenciais acontece no primeiro uso (get_api_token),
        nao aqui — assim a UI consegue salvar uma config parcial.
        """
        # Retrocompat: ate 2026-04-24 gravavamos `credentials: {...}` em
        # vez de client_id/client_secret. Se vier, mergeia antes de ler.
        legacy = data.get("credentials")
        if isinstance(legacy, dict):
            merged: dict = {**legacy, **data}
        else:
            merged = dict(data)

        client_id = merged.get("client_id") or ""
        client_secret = merged.get("client_secret") or ""

        if client_id and not isinstance(client_id, str):
            raise ValueError("QiTech config.client_id deve ser string")
        if client_secret and not isinstance(client_secret, str):
            raise ValueError("QiTech config.client_secret deve ser string")

        return cls(
            base_url=str(merged.get("base_url") or DEFAULT_BASE_URL).rstrip("/"),
            client_id=str(client_id),
            client_secret=str(client_secret),
            token_ttl_seconds=int(
                merged.get("token_ttl_seconds") or DEFAULT_TOKEN_TTL_SECONDS
            ),
            token_refresh_skew_seconds=int(
                merged.get("token_refresh_skew_seconds")
                or DEFAULT_TOKEN_REFRESH_SKEW_SECONDS
            ),
        )
