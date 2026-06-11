"""Config do adapter Infosimples — credencial decifrada e famílias de login.

O secret da credencial (`provedor_dados_credencial.encrypted_payload`,
Fernet) é um dict FLAT com o token da API + logins POR FAMÍLIA de consulta
(detalhe operacional do Infosimples: JUCESP e protestos têm CPF/senha
próprios, distintos entre si):

    {
      "api_key": "...",                      # token Infosimples (obrigatório)
      "jucesp_login_cpf": "...",             # família JUCESP (opcional)
      "jucesp_login_senha": "...",
      "protesto_login_cpf": "...",           # família protestos (opcional)
      "protesto_login_senha": "..."
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.integracoes.adapters.data.infosimples.errors import (
    InfosimplesMissingFamilyCredentialError,
)

DEFAULT_BASE_URL = "https://api.infosimples.com"


@dataclass(slots=True)
class InfosimplesConfig:
    """Credencial decifrada + endereço base."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout_s: float = 60.0
    # Logins por família: {"jucesp": {"login_cpf": ..., "login_senha": ...}}
    families: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        plain: dict[str, str],
        *,
        base_url: str | None = None,
        timeout_ms: int | None = None,
    ) -> InfosimplesConfig:
        api_key = (plain.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("Credencial Infosimples sem api_key.")

        families: dict[str, dict[str, str]] = {}
        for key, value in plain.items():
            if not isinstance(value, str) or not value.strip():
                continue
            # `<familia>_login_cpf` / `<familia>_login_senha`
            for suffix in ("_login_cpf", "_login_senha"):
                if key.endswith(suffix):
                    family = key[: -len(suffix)]
                    families.setdefault(family, {})[suffix[1:]] = value.strip()

        return cls(
            api_key=api_key,
            base_url=(base_url or DEFAULT_BASE_URL).rstrip("/"),
            timeout_s=(timeout_ms / 1000.0) if timeout_ms else 60.0,
            families=families,
        )

    def family_login(self, family: str) -> dict[str, str]:
        """Params de login da família (`login_cpf`, `login_senha`).

        Raises:
            InfosimplesMissingFamilyCredentialError: família não cadastrada.
        """
        creds = self.families.get(family) or {}
        if not creds.get("login_cpf") or not creds.get("login_senha"):
            raise InfosimplesMissingFamilyCredentialError(family)
        return {
            "login_cpf": creds["login_cpf"],
            "login_senha": creds["login_senha"],
        }
