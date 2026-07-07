"""Gestao de coletores (Strata Collector) -- CRUD de `agent_credential`.

Endpoints de USUARIO (JWT + require_module INTEGRACOES/ADMIN), diferente do
File Gateway (`routers/filedrop.py`), que e autenticado pelo TOKEN do agente.
Aqui um admin do tenant cria/edita/revoga credenciais e monta a watch_config
(pastas vigiadas -> source_label) que o agente recebe no /ping.

Token plaintext aparece UMA unica vez na resposta do create/rotate — so o
sha256 persiste. Toda mudanca de ciclo de vida grava `decision_log`
(CONFIGURATION_CHANGE, §14.2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.cadastros.models.unidade_administrativa import UnidadeAdministrativa
from app.modules.integracoes.models.agent_credential import AgentCredential
from app.modules.integracoes.models.file_landing import FileLanding
from app.modules.integracoes.services import filedrop as filedrop_svc
from app.shared.audit_log.decision_log import DecisionLog, DecisionType

router = APIRouter(prefix="/coletores", tags=["integracoes:coletores"])
_Guard = Depends(require_module(Module.INTEGRACOES, Permission.ADMIN))


# ---- Schemas -----------------------------------------------------------------


class WatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=512)
    glob: str = Field(default="*", min_length=1, max_length=64)
    source_label: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    # Hint pro consumidor server-side (zip diario e aberto no servidor).
    container: Literal["zip"] | None = None


class WatchConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_interval_minutes: int = Field(default=5, ge=1, le=1440)
    watches: list[WatchItem] = Field(default_factory=list)


class ColetorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    unidade_administrativa_id: UUID | None = None
    watch_config: WatchConfigIn = Field(default_factory=WatchConfigIn)


class ColetorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    unidade_administrativa_id: UUID | None = None
    watch_config: WatchConfigIn | None = None


class ColetorRead(BaseModel):
    id: UUID
    name: str
    unidade_administrativa_id: UUID | None
    watch_config: dict
    agent_version: str | None
    last_seen_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    arquivos_total: int


class ColetorCreated(ColetorRead):
    # Plaintext exibido UMA vez — nunca mais recuperavel (so sha256 no banco).
    token: str


# ---- Helpers -----------------------------------------------------------------


def _read(cred: AgentCredential, arquivos_total: int = 0) -> ColetorRead:
    return ColetorRead(
        id=cred.id,
        name=cred.name,
        unidade_administrativa_id=cred.unidade_administrativa_id,
        watch_config=cred.watch_config or {},
        agent_version=cred.agent_version,
        last_seen_at=cred.last_seen_at,
        revoked_at=cred.revoked_at,
        created_at=cred.created_at,
        arquivos_total=arquivos_total,
    )


async def _get_owned(
    db: AsyncSession, tenant_id: UUID, coletor_id: UUID
) -> AgentCredential:
    """Carrega a credencial JA escopada por tenant — 404 se de outro tenant."""
    cred = (
        await db.execute(
            select(AgentCredential).where(
                AgentCredential.id == coletor_id,
                AgentCredential.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if cred is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coletor nao encontrado."
        )
    return cred


async def _validate_ua(db: AsyncSession, tenant_id: UUID, ua_id: UUID | None) -> None:
    if ua_id is None:
        return
    ok = (
        await db.execute(
            select(UnidadeAdministrativa.id).where(
                UnidadeAdministrativa.id == ua_id,
                UnidadeAdministrativa.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if ok is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unidade administrativa nao encontrada neste tenant.",
        )


def _log_change(
    db: AsyncSession,
    principal: RequestPrincipal,
    cred: AgentCredential,
    *,
    action: str,
    detail: dict,
) -> None:
    db.add(
        DecisionLog(
            tenant_id=principal.tenant_id,
            decision_type=DecisionType.CONFIGURATION_CHANGE,
            rule_or_model="coletor_credential",
            rule_or_model_version=filedrop_svc.GATEWAY_VERSION,
            endpoint_name=f"coletores.{action}",
            triggered_by=f"user:{principal.user_id}",
            inputs_ref={"coletor_id": str(cred.id), "name": cred.name},
            output=detail,
            explanation=f"Coletor '{cred.name}': {action}.",
        )
    )


# ---- Endpoints ----------------------------------------------------------------


@router.get("", response_model=list[ColetorRead])
async def list_coletores(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> list[ColetorRead]:
    creds = (
        (
            await db.execute(
                select(AgentCredential)
                .where(AgentCredential.tenant_id == principal.tenant_id)
                .order_by(AgentCredential.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    counts = dict(
        (
            await db.execute(
                select(FileLanding.agent_credential_id, func.count())
                .where(FileLanding.tenant_id == principal.tenant_id)
                .group_by(FileLanding.agent_credential_id)
            )
        ).all()
    )
    return [_read(c, counts.get(c.id, 0)) for c in creds]


@router.post("", response_model=ColetorCreated, status_code=status.HTTP_201_CREATED)
async def create_coletor(
    body: ColetorCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> ColetorCreated:
    await _validate_ua(db, principal.tenant_id, body.unidade_administrativa_id)
    token = filedrop_svc.generate_token()
    cred = AgentCredential(
        tenant_id=principal.tenant_id,
        unidade_administrativa_id=body.unidade_administrativa_id,
        name=body.name,
        token_hash=filedrop_svc.hash_token(token),
        watch_config=body.watch_config.model_dump(exclude_none=True),
    )
    db.add(cred)
    await db.flush()
    _log_change(
        db, principal, cred, action="create",
        detail={"watches": len(body.watch_config.watches)},
    )
    await db.commit()
    await db.refresh(cred)
    return ColetorCreated(**_read(cred).model_dump(), token=token)


@router.put("/{coletor_id}", response_model=ColetorRead)
async def update_coletor(
    coletor_id: UUID,
    body: ColetorUpdate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> ColetorRead:
    cred = await _get_owned(db, principal.tenant_id, coletor_id)
    changed: dict = {}
    if body.name is not None and body.name != cred.name:
        changed["name"] = {"de": cred.name, "para": body.name}
        cred.name = body.name
    if body.unidade_administrativa_id != cred.unidade_administrativa_id:
        await _validate_ua(db, principal.tenant_id, body.unidade_administrativa_id)
        changed["unidade_administrativa_id"] = str(body.unidade_administrativa_id)
        cred.unidade_administrativa_id = body.unidade_administrativa_id
    if body.watch_config is not None:
        new_config = body.watch_config.model_dump(exclude_none=True)
        if new_config != cred.watch_config:
            changed["watches"] = len(body.watch_config.watches)
            cred.watch_config = new_config
    if changed:
        _log_change(db, principal, cred, action="update", detail=changed)
        await db.commit()
        await db.refresh(cred)
    return _read(cred)


@router.post("/{coletor_id}/rotate", response_model=ColetorCreated)
async def rotate_token(
    coletor_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> ColetorCreated:
    """Gera token novo (o antigo para de funcionar na hora). Tambem REATIVA
    uma credencial revogada — revogar + rotate = 'trocar a fechadura'."""
    cred = await _get_owned(db, principal.tenant_id, coletor_id)
    token = filedrop_svc.generate_token()
    cred.token_hash = filedrop_svc.hash_token(token)
    reativado = cred.revoked_at is not None
    cred.revoked_at = None
    _log_change(
        db, principal, cred, action="rotate", detail={"reativado": reativado}
    )
    await db.commit()
    await db.refresh(cred)
    return ColetorCreated(**_read(cred).model_dump(), token=token)


@router.post("/{coletor_id}/revoke", response_model=ColetorRead)
async def revoke_coletor(
    coletor_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _Guard,
) -> ColetorRead:
    """Revoga a credencial (agente passa a receber 401). Linha nao e deletada:
    file_landing/decision_log referenciam a historia. Reativar = /rotate."""
    cred = await _get_owned(db, principal.tenant_id, coletor_id)
    if cred.revoked_at is None:
        cred.revoked_at = datetime.now(UTC)
        _log_change(db, principal, cred, action="revoke", detail={})
        await db.commit()
        await db.refresh(cred)
    return _read(cred)
