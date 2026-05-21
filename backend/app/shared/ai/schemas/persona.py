"""Pydantic schemas (DTOs) para endpoints de /admin/ia/personas.

Persona = papel reutilizavel injetado no system prompt (CLAUDE.md §19.12).
Versionamento espelha `ai_prompt`: edicao = nova versao; active pointer
seleciona qual versao roda; rollback = 1 click.

Endpoints REST (em `app/modules/admin/api/ai_personas.py`):
    GET    /admin/ia/personas         lista (com flag is_active)
    GET    /admin/ia/personas/{id}    detalhe (texto completo)
    POST   /admin/ia/personas         cria nova familia (vira v1, ativa)
    PUT    /admin/ia/personas/{id}    cria nova versao copiando + patches
    PUT    /admin/ia/personas/{name}/active   promove versao
    POST   /admin/ia/personas/{id}/archive    soft-delete (nao ativa)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ─── Read DTOs ────────────────────────────────────────────────────────────


class PersonaVersionInfo(BaseModel):
    """Linha enxuta pra listagens. Texto completo (`role_block`) NAO incluso."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    version: int
    display_name: str
    is_active: bool
    expertise_domains: list[str] | None = None
    description: str | None = None
    usage_count: int = 0  # quantos agent_definition referenciam esta persona
    created_at: datetime
    archived_at: datetime | None = None


class PersonaDetail(BaseModel):
    """Detalhe completo de uma versao — usado no editor."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    version: int
    display_name: str
    role_block: str  # markdown
    description: str | None = None
    expertise_domains: list[str] | None = None
    is_active: bool
    usage_count: int = 0
    created_at: datetime
    archived_at: datetime | None = None


# ─── Write DTOs ───────────────────────────────────────────────────────────


class PersonaCreate(BaseModel):
    """Cria nova familia de persona. Vira v1 e e ativada automaticamente."""

    model_config = ConfigDict(extra="forbid")

    # Nome canonico: lowercase + digits + `.` (entre segmentos) + `_`
    # (dentro de segmento). SEM espacos, SEM maiusculas, SEM caracteres
    # especiais. Pattern e validacao em DB (defesa em profundidade —
    # frontend tem Zod mas curl direto poderia contornar).
    # Ex valido: "credito.analista_financial", "controladoria.controller_senior"
    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9]+(\.[a-z0-9_]+)*$",
    )
    display_name: str = Field(min_length=1, max_length=200)
    role_block: str = Field(min_length=1)  # markdown
    description: str | None = None
    expertise_domains: list[str] | None = None


class PersonaUpdate(BaseModel):
    """Cria nova versao a partir de uma existente.

    Campos nao informados sao herdados da versao base. A nova versao NAO
    e ativada automaticamente — chame PUT /{name}/active pra promover.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    role_block: str | None = None
    description: str | None = None
    expertise_domains: list[str] | None = None


class PersonaActivate(BaseModel):
    """Promove uma versao a ativa pra `name`."""

    model_config = ConfigDict(extra="forbid")

    version_id: UUID
