"""CRUD da UnidadeAdministrativa.

Funcoes puras de servico (sem classe). Recebem AsyncSession + tenant_id
explicit. Toda query escopa por tenant_id (CLAUDE.md secao 10).

Tradutores de erro: as constraints uniques de DB viram `ValueError` com
mensagem em pt-BR pra UI. A camada API converte ValueError -> 409.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.models.unidade_administrativa import (
    TipoUnidadeAdministrativa,
    UnidadeAdministrativa,
)
from app.modules.cadastros.schemas.unidade_administrativa import (
    UnidadeAdministrativaCreate,
    UnidadeAdministrativaUpdate,
)


class UAConflictError(ValueError):
    """Violacao de constraint (nome ou CNPJ duplicado no tenant)."""


async def list_uas(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ativa: bool | None = None,
    tipo: TipoUnidadeAdministrativa | None = None,
) -> Sequence[UnidadeAdministrativa]:
    """Lista UAs do tenant com filtros opcionais. Ordenacao por nome."""
    stmt = select(UnidadeAdministrativa).where(
        UnidadeAdministrativa.tenant_id == tenant_id
    )
    if ativa is not None:
        stmt = stmt.where(UnidadeAdministrativa.ativa == ativa)
    if tipo is not None:
        stmt = stmt.where(UnidadeAdministrativa.tipo == tipo)
    stmt = stmt.order_by(UnidadeAdministrativa.nome)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_ua(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
) -> UnidadeAdministrativa | None:
    """Busca UA por id no escopo do tenant. Retorna None se nao existir
    ou se existir em outro tenant (isolamento)."""
    stmt = select(UnidadeAdministrativa).where(
        UnidadeAdministrativa.tenant_id == tenant_id,
        UnidadeAdministrativa.id == ua_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_ua(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    payload: UnidadeAdministrativaCreate,
) -> UnidadeAdministrativa:
    """Cria UA. Levanta UAConflictError se nome ou CNPJ ja existem no tenant."""
    ua = UnidadeAdministrativa(
        tenant_id=tenant_id,
        **payload.model_dump(),
    )
    db.add(ua)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise UAConflictError(_translate_integrity_error(e, payload)) from e
    await db.refresh(ua)
    return ua


async def update_ua(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    payload: UnidadeAdministrativaUpdate,
) -> UnidadeAdministrativa | None:
    """Atualiza UA. Merge semantics -- campo omitido preserva valor atual."""
    ua = await get_ua(db, tenant_id=tenant_id, ua_id=ua_id)
    if ua is None:
        return None
    diff = payload.model_dump(exclude_unset=True)
    if not diff:
        return ua
    for k, v in diff.items():
        setattr(ua, k, v)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise UAConflictError(_translate_integrity_error(e, payload)) from e
    await db.refresh(ua)
    return ua


async def delete_ua(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
) -> bool:
    """Remove UA. Retorna False se nao existir (idempotencia do DELETE)."""
    ua = await get_ua(db, tenant_id=tenant_id, ua_id=ua_id)
    if ua is None:
        return False
    await db.delete(ua)
    await db.commit()
    return True


def _translate_integrity_error(
    e: IntegrityError,
    payload: UnidadeAdministrativaCreate | UnidadeAdministrativaUpdate,
) -> str:
    """Mapeia constraint violada para mensagem amigavel pt-BR."""
    msg = str(e.orig) if e.orig else str(e)
    if "uq_cadastros_ua_tenant_nome" in msg:
        nome = getattr(payload, "nome", None)
        return f"Ja existe uma UA com o nome {nome!r} neste tenant."
    if "uq_cadastros_ua_tenant_cnpj" in msg:
        cnpj = getattr(payload, "cnpj", None)
        return f"Ja existe uma UA com o CNPJ {cnpj!r} neste tenant."
    return f"Conflito ao gravar UA: {msg}"
