"""McpRegistry — resolucao de Servidores MCP por escopo (spec §5.2).

RBAC no nivel do SERVIDOR: a tag `module` do `mcp_server` e comparada com
as permissoes do usuario no `ScopedContext`. Servidor com `module=NULL` e
cross-module (entra sempre que concedido ao agente). O wrapper de tool
NAO repete a checagem (spec §4.3).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from app.agentic.mcp.models import McpServer, McpServerActive
from app.core.enums import Module, Permission

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.agentic._scope import ScopedContext

logger = logging.getLogger(__name__)


class McpServerNotFoundError(LookupError):
    """Servidor MCP nao registrado/ativo para o nome pedido."""


class McpRegistry:
    """Namespace de resolucao (staticmethods, espelha AgentRegistry)."""

    @staticmethod
    async def resolve(
        db: AsyncSession, *, name: str, scope: ScopedContext
    ) -> McpServer | None:
        """Resolve a versao ativa de `name` para o scope.

        Tenant-especifico ganha de global. Retorna None quando o usuario
        nao tem permissao no modulo do servidor (filtragem silenciosa —
        capability fora de permissao simplesmente nao entra no cardapio,
        spec §6.3). Raises McpServerNotFoundError se nao ha registro ativo.
        """
        stmt = (
            select(McpServerActive)
            .where(McpServerActive.name == name)
            .where(
                or_(
                    McpServerActive.tenant_id == scope.tenant_id,
                    McpServerActive.tenant_id.is_(None),
                )
            )
            .order_by(McpServerActive.tenant_id.nulls_last())
            .limit(1)
        )
        active = (await db.execute(stmt)).scalar_one_or_none()
        if active is None:
            raise McpServerNotFoundError(
                f"Servidor MCP '{name}' nao tem registro ativo (mcp_server_active)."
            )

        server = await db.get(McpServer, active.server_id)
        if server is None:
            raise McpServerNotFoundError(
                f"mcp_server_active aponta para id={active.server_id} mas a row "
                f"nao existe em mcp_server. DB inconsistente."
            )
        if server.archived_at is not None:
            raise McpServerNotFoundError(
                f"Servidor MCP '{name}' esta arquivado (versao ativa v{server.version})."
            )

        # RBAC por module tag (NULL = cross-module, entra sempre).
        if server.module is not None:
            try:
                module = Module(server.module)
            except ValueError:
                logger.error(
                    "mcp_server '%s' com module invalido '%s' — fora do cardapio",
                    name,
                    server.module,
                )
                return None
            if not scope.has_permission(module, Permission.READ):
                logger.debug(
                    "MCP '%s' (module=%s) fora do cardapio: user sem permissao",
                    name,
                    server.module,
                )
                return None

        return server
