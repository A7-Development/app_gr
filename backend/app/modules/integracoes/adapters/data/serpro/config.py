"""Config do adapter SERPRO -- credencial decifrada + plano contratado.

O secret vem de `tenant_source_config.config` (envelope Fernet, decifrado
por `services.source_config`). Dict plaintext esperado:

    {
      "consumer_key": "...",          # obrigatorio (OAuth2 client_credentials)
      "consumer_secret": "...",       # obrigatorio
      "plan": "df" | "escalonado",    # opcional, default "df"
      "base_url": "https://...",      # opcional, override da base do plano
      "token_url": "https://...",     # opcional, override do endpoint de token
      "timeout_ms": 30000             # opcional
    }

Planos (mesma API, base URL diferente — 403 = plano/caminho errado):
    df          -> https://gateway.apiserpro.serpro.gov.br/consulta-nfe-df/api
    escalonado  -> https://gateway.apiserpro.serpro.gov.br/nfe/1
"""

from __future__ import annotations

from dataclasses import dataclass

GATEWAY = "https://gateway.apiserpro.serpro.gov.br"
DEFAULT_TOKEN_URL = f"{GATEWAY}/token"

PLAN_BASE_URLS = {
    "df": f"{GATEWAY}/consulta-nfe-df/api",
    "escalonado": f"{GATEWAY}/nfe/1",
}

# Ambiente de demonstracao (mock publico do SERPRO, custo zero). O token
# trial e publico e documentado na propria pagina de demonstracao.
TRIAL_BASE_URL = f"{GATEWAY}/consulta-nfe-df-trial/api"
TRIAL_BEARER_TOKEN = "06aef429-a981-3ec5-a1f8-71d38d86481e"  # token publico de demo


@dataclass(slots=True)
class SerproConfig:
    """Credencial decifrada + enderecos resolvidos."""

    consumer_key: str
    consumer_secret: str
    base_url: str
    token_url: str = DEFAULT_TOKEN_URL
    timeout_s: float = 30.0

    @classmethod
    def from_dict(cls, plain: dict) -> SerproConfig:
        consumer_key = str(plain.get("consumer_key") or "").strip()
        consumer_secret = str(plain.get("consumer_secret") or "").strip()
        if not consumer_key or not consumer_secret:
            raise ValueError(
                "Credencial SERPRO sem consumer_key/consumer_secret."
            )

        plan = str(plain.get("plan") or "df").strip().lower()
        if plan not in PLAN_BASE_URLS:
            raise ValueError(
                f"Plano SERPRO desconhecido: {plan!r} (aceitos: df, escalonado)."
            )

        base_url = str(plain.get("base_url") or PLAN_BASE_URLS[plan]).rstrip("/")
        token_url = str(plain.get("token_url") or DEFAULT_TOKEN_URL)
        timeout_ms = plain.get("timeout_ms")

        return cls(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            base_url=base_url,
            token_url=token_url,
            timeout_s=(float(timeout_ms) / 1000.0) if timeout_ms else 30.0,
        )
