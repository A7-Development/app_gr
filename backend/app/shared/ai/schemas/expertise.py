"""Pydantic schemas (DTOs) para endpoints de /admin/ia/expertises.

Expertise = knowledge pack injetado no system prompt (CLAUDE.md §19.12).
Define O QUE o agente sabe — embasamento teorico aplicado, vocabulario
tecnico, heuristicas profissionais, referencias regulatorias.

Versionamento espelha persona/prompt: edicao = nova versao; active
pointer seleciona qual roda; rollback = 1 click.

Endpoints REST (em `app/modules/admin/api/ai_expertises.py`):
    GET    /admin/ia/expertises         lista (com flag is_active)
    GET    /admin/ia/expertises/{id}    detalhe (knowledge_text completo)
    POST   /admin/ia/expertises         cria nova familia (vira v1, ativa)
    PUT    /admin/ia/expertises/{id}    cria nova versao copiando + patches
    PUT    /admin/ia/expertises/{name}/active   promove versao
    POST   /admin/ia/expertises/{id}/archive    soft-delete (nao ativa)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ─── Reference URLs ──────────────────────────────────────────────────────


class ExpertiseReference(BaseModel):
    """Uma referencia (norma, doc, link) anexada a expertise."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=500)
    label: str = Field(min_length=1, max_length=200)
    kind: str | None = Field(default=None, max_length=32)


# ─── Read DTOs ────────────────────────────────────────────────────────────


class ExpertiseVersionInfo(BaseModel):
    """Linha enxuta pra listagens. `knowledge_text` NAO incluso."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    version: int
    display_name: str
    domain: str
    is_active: bool
    # quantos agent_definition referenciam esta expertise (via expertise_ids array)
    usage_count: int = 0
    created_at: datetime
    archived_at: datetime | None = None


class ExpertiseDetail(BaseModel):
    """Detalhe completo de uma versao — usado no editor."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    version: int
    display_name: str
    domain: str
    knowledge_text: str  # markdown
    reference_urls: list[ExpertiseReference] | None = None
    is_active: bool
    usage_count: int = 0
    created_at: datetime
    archived_at: datetime | None = None


# ─── Write DTOs ───────────────────────────────────────────────────────────


class ExpertiseCreate(BaseModel):
    """Cria nova familia de expertise. Vira v1 e e ativada automaticamente."""

    model_config = ConfigDict(extra="forbid")

    # Nome canonico: lowercase + digits + `.` (entre segmentos) + `_`
    # (dentro de segmento). SEM espacos, SEM maiusculas, SEM caracteres
    # especiais. Defesa em profundidade — frontend tem Zod, este pattern
    # garante que curl direto tambem nao passa.
    # Ex valido: "contabilidade.fidc", "regulatorio.cmn_4966"
    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9]+(\.[a-z0-9_]+)*$",
    )
    display_name: str = Field(min_length=1, max_length=200)
    # Dominio segue mesma convencao (lowercase, sem espacos) — pra
    # filtros e badges consistentes.
    domain: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9_]+$",
    )
    knowledge_text: str = Field(min_length=1)
    reference_urls: list[ExpertiseReference] | None = None


class ExpertiseUpdate(BaseModel):
    """Cria nova versao a partir de uma existente.

    Campos nao informados sao herdados da versao base. A nova versao NAO
    e ativada automaticamente.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    domain: str | None = None
    knowledge_text: str | None = None
    reference_urls: list[ExpertiseReference] | None = None


class ExpertiseActivate(BaseModel):
    """Promove uma versao a ativa pra `name`."""

    model_config = ConfigDict(extra="forbid")

    version_id: UUID
