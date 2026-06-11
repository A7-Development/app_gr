"""Tipa o payload decifrado da credencial BigDataCorp.

Vai e volta entre o JSONB cifrado em `provedor_dados_credencial.encrypted_payload`
(formato opaco do storage) e o dataclass tipado consumido pelo client.

Formato esperado do payload em plaintext:
    {
        "access_token": "...",
        "token_id": "..."
    }

Sem campos opcionais ainda — se o vendor pedir campos novos no futuro,
estende este dataclass + faz o sync de migration de credenciais existentes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.integracoes.adapters.data.bigdatacorp.errors import (
    BigDataCorpConfigError,
)


@dataclass(frozen=True)
class BigDataCorpConfig:
    """Credencial BigDataCorp materializada do envelope decifrado."""

    access_token: str
    token_id: str

    def has_credentials(self) -> bool:
        return bool(self.access_token) and bool(self.token_id)

    @classmethod
    def from_dict(cls, payload: dict) -> BigDataCorpConfig:
        """Materializa de um dict (envelope decifrado).

        Levanta `BigDataCorpConfigError` se faltar campo obrigatorio.
        """
        if not isinstance(payload, dict):
            raise BigDataCorpConfigError(
                f"BDC config: payload nao e dict (tipo {type(payload).__name__})"
            )

        access_token = payload.get("access_token")
        token_id = payload.get("token_id")

        missing = [
            name
            for name, value in (
                ("access_token", access_token),
                ("token_id", token_id),
            )
            if not value
        ]
        if missing:
            raise BigDataCorpConfigError(
                f"BDC config incompleta — falta {', '.join(missing)}"
            )

        return cls(
            access_token=str(access_token),
            token_id=str(token_id),
        )
