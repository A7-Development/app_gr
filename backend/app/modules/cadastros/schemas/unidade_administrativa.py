"""Schemas Pydantic da UnidadeAdministrativa.

Tres formas:
- `*Create`: payload de POST. Campos obrigatorios + validacao de CNPJ.
- `*Update`: payload de PATCH. Tudo opcional (merge semantics).
- `*Out`: response. Inclui id + audit timestamps.

Validacao de CNPJ: 14 digitos, sem mascara. Sem checksum CVM/RFB pra nao
gerar fricao em UAs em formacao com CNPJ provisorio. Validacao formal
fica no servico de cadastro de pessoa juridica (futuro).
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.cadastros.models.unidade_administrativa import (
    TipoUnidadeAdministrativa,
)

_CNPJ_RE = re.compile(r"^\d{14}$")


def _normalize_cnpj(value: str | None) -> str | None:
    """Remove pontuacao e valida 14 digitos. None passa."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if not _CNPJ_RE.match(digits):
        raise ValueError(
            f"CNPJ deve ter 14 digitos (recebido: {len(digits)} digitos apos remover pontuacao)"
        )
    return digits


class UnidadeAdministrativaCreate(BaseModel):
    """Payload de criacao de UA."""

    nome: str = Field(min_length=1, max_length=200)
    cnpj: str | None = Field(default=None, max_length=18)
    tipo: TipoUnidadeAdministrativa
    ativa: bool = True
    bitfin_ua_id: int | None = None

    @field_validator("cnpj", mode="before")
    @classmethod
    def _v_cnpj(cls, v: str | None) -> str | None:
        return _normalize_cnpj(v)

    @field_validator("nome", mode="before")
    @classmethod
    def _v_nome(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        return v


class UnidadeAdministrativaUpdate(BaseModel):
    """Payload de atualizacao parcial. Campo omitido = preserva valor atual."""

    nome: str | None = Field(default=None, min_length=1, max_length=200)
    cnpj: str | None = Field(default=None, max_length=18)
    tipo: TipoUnidadeAdministrativa | None = None
    ativa: bool | None = None
    bitfin_ua_id: int | None = None

    # Sentinel: campo omitido vs explicit None (limpar valor). Pydantic trata
    # isso via `model_dump(exclude_unset=True)` no servico.

    @field_validator("cnpj", mode="before")
    @classmethod
    def _v_cnpj(cls, v: str | None) -> str | None:
        return _normalize_cnpj(v)

    @field_validator("nome", mode="before")
    @classmethod
    def _v_nome(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            return v.strip()
        return v


class UnidadeAdministrativaOut(BaseModel):
    """Response payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    nome: str
    cnpj: str | None
    tipo: TipoUnidadeAdministrativa
    ativa: bool
    bitfin_ua_id: int | None
    created_at: datetime
    updated_at: datetime
