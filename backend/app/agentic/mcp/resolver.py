"""Resolve a conexao de um McpServer: credencial (decrypt) -> headers.

A credencial vive no store cifrado EXISTENTE (`provedor_dados_credencial`,
envelope Fernet — spec §4.2). O mapeamento payload->headers e config da
row (`auth_header_map`), nunca codigo de vendor:

    BDC: payload {"access_token": "...", "token_id": "..."}
         auth_header_map {"access_token": "AccessToken", "token_id": "TokenId"}
         -> headers {"AccessToken": "...", "TokenId": "..."}

Payload que ja traga {"headers": {...}} e usado direto (shape generico).
Headers decifrados vivem apenas em memoria durante o turno.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.shared.crypto import decrypt_envelope
from app.shared.data_providers.models.credential import DataProviderCredential

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.agentic.mcp.models import McpServer


class McpCredentialError(RuntimeError):
    """Credencial do servidor MCP ausente/invalida."""


@dataclass(frozen=True, slots=True)
class McpConnection:
    """Tudo que o client precisa para falar com o servidor."""

    server_id: str
    name: str
    url: str
    headers: dict[str, str]


async def resolve_connection(db: AsyncSession, server: McpServer) -> McpConnection:
    """Monta a conexao do servidor, decifrando a credencial se houver."""
    headers: dict[str, str] = {}

    if server.credential_id is not None:
        row = (
            await db.execute(
                select(DataProviderCredential).where(
                    DataProviderCredential.id == server.credential_id,
                    DataProviderCredential.active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise McpCredentialError(
                f"Servidor MCP '{server.name}': credencial "
                f"{server.credential_id} inexistente ou inativa."
            )
        payload = decrypt_envelope(row.encrypted_payload)

        if isinstance(payload.get("headers"), dict):
            headers = {str(k): str(v) for k, v in payload["headers"].items()}
        elif server.auth_header_map:
            for payload_key, header_name in server.auth_header_map.items():
                value = payload.get(payload_key)
                if not value:
                    raise McpCredentialError(
                        f"Servidor MCP '{server.name}': campo '{payload_key}' "
                        f"vazio/ausente no payload da credencial."
                    )
                headers[str(header_name)] = str(value)
        else:
            raise McpCredentialError(
                f"Servidor MCP '{server.name}': credencial sem shape "
                f"'headers' e sem auth_header_map configurado."
            )

    return McpConnection(
        server_id=str(server.id),
        name=server.name,
        url=server.url,
        headers=headers,
    )
