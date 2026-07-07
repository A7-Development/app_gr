"""ScopedContext — contexto canonico injetado em tools e agents (CLAUDE.md §19.0).

Substitui closure-based scoping. Tools nao mais fechadas sobre
`(tenant_id, dossier_id, db)` — recebem `ScopedContext` como primeiro
parametro em runtime. LLM nao pode mentir sobre escopo: tenant_id,
empresa_id, dossier_id viajam em campos seguros preenchidos pelo
invocador, nao parametros expostos ao modelo.

Campos fixos (sempre presentes):
    tenant_id, empresa_id, user_id, module, permissions, db

`extras: dict` — bag de runtime-specific values (dossier_id, run_id,
parent_decision_log_id, etc). Inicialmente flexivel; pode evoluir pra
typed extras quando o vocabulario estabilizar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Module, Permission


@dataclass(frozen=True, slots=True)
class ScopedContext:
    """Contexto de execucao escopado por tenant + empresa + user + module.

    Frozen porque deve ser tratado como imutavel apos criacao — tools nao
    devem alterar scope a meio caminho. Para "trocar de modulo" durante
    uma cadeia agentica (delegacao cross-modulo), o invocador cria um
    novo ScopedContext explicitamente.

    Attributes:
        tenant_id: UUID do tenant ativo.
        empresa_id: UUID da empresa ativa (None apenas para tools globais
            que nao operam em dados de empresa, raro).
        user_id: UUID do usuario que iniciou a chamada agentica.
        module: Modulo de origem da invocacao (define scope default de
            tools/workflows disponiveis).
        permissions: dict de Module -> Permission do usuario. Usado pelo
            registry pra filtrar tools que o usuario nao pode chamar.
        db: AsyncSession SQLAlchemy. Vive durante a chamada agentica.
        extras: bag de runtime-specific values. Convencoes:
            - `dossier_id`: UUID do dossie de credito (workflow Credito)
            - `run_id`: UUID da execucao atual (audit)
            - `parent_decision_log_id`: UUID do decision_log pai (delegacao)
            - `cross_module`: bool, true se agente foi invocado cross-modulo
            - outros conforme caso de uso.
    """

    tenant_id: UUID
    empresa_id: UUID | None
    user_id: UUID
    module: Module
    permissions: dict[Module, Permission]
    db: AsyncSession
    extras: dict[str, Any] = field(default_factory=dict)

    def has_permission(self, module: Module, required: Permission) -> bool:
        """Check if user has at least `required` permission for `module`."""
        owned = self.permissions.get(module, Permission.NONE)
        # Permission e StrEnum (value = 'none'/'read'/'write'/'admin'): comparar
        # `.value` daria ordem ALFABETICA ('admin' < 'read' -> ADMIN nao satisfaz
        # READ). Usa `.satisfies()` do enum, que compara pela ESCALA correta.
        return owned.satisfies(required)
