"""Protesto endpoints — consulta CENPROT/IEPTB (Infosimples) no dossie.

  POST /dossies/{id}/protestos/consultar   dispara a consulta (paga) + silver
  GET  /dossies/{id}/protestos             le a ultima consulta (silver)

Consultar e WRITE (dispara round-trip pago + materializa silver); ler e READ.
Guardados por require_module(Module.CREDITO, ...).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal

router = APIRouter()


class ConsultaProtestoIn(BaseModel):
    """Corpo da consulta avulsa de protesto (página Consultas)."""

    documento: str = Field(..., description="CNPJ (14) ou CPF (11) — com ou sem máscara.")
    incluir_detalhe_sp: bool = Field(
        default=True,
        description="Buscar o detalhe por cartório de SP (onde aparece o credor).",
    )


@router.post("/dossies/{dossier_id}/protestos/consultar")
async def consultar_protestos(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> dict[str, Any]:
    """Consulta protestos da empresa-alvo (nacional + detalhe SP) e materializa
    o silver. O credor (cedente/apresentante) entra onde a fonte identificar
    (detalhe de cartorios de SP). Bronze de cada chamada em
    wh_infosimples_raw_consulta.
    """
    from app.modules.credito.services.protesto_dossie import (
        consultar_e_persistir_protestos,
    )
    from app.modules.integracoes.adapters.data.infosimples.errors import (
        InfosimplesAdapterError,
    )

    try:
        summary = await consultar_e_persistir_protestos(
            db,
            tenant_id=principal.tenant_id,
            dossier_id=dossier_id,
            initiated_by=principal.user_id,
        )
    except InfosimplesAdapterError as e:
        # Infra (credencial ausente, provedor fora do ar). Bronze, se houve,
        # persiste para auditoria.
        await db.commit()
        raise HTTPException(status_code=424, detail=str(e)) from e
    await db.commit()
    return summary


@router.get("/dossies/{dossier_id}/protestos")
async def listar_protestos(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> dict[str, Any]:
    """Ultima consulta de protesto da empresa-alvo (silver). Vazio = nunca
    consultado (dispara em POST .../consultar)."""
    from app.modules.credito.services.protesto_dossie import (
        build_protesto_agent_view,
    )

    view = await build_protesto_agent_view(
        db, tenant_id=principal.tenant_id, dossier_id=dossier_id
    )
    if view is None:
        return {
            "encontrado": False,
            "mensagem": "Empresa-alvo não encontrada no dossiê.",
        }
    return view


# ─── Consulta AVULSA (pagina Credito > Consultas > Protestos) ────────────────


@router.post("/consultas/protesto")
async def consultar_protesto_avulso_endpoint(
    body: ConsultaProtestoIn,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> dict[str, Any]:
    """Consulta protestos de um CNPJ/CPF avulso (sem dossiê) e devolve a view
    completa. Materializa silver + bronze (auditável). O credor só vem no
    detalhe de cartórios de SP (Provimento CNJ 225/2026)."""
    from app.modules.credito.services.protesto_dossie import (
        consultar_protesto_avulso,
    )
    from app.modules.integracoes.adapters.data.infosimples.errors import (
        InfosimplesAdapterError,
    )

    try:
        view = await consultar_protesto_avulso(
            db,
            tenant_id=principal.tenant_id,
            documento=body.documento,
            initiated_by=principal.user_id,
            incluir_detalhe_sp=body.incluir_detalhe_sp,
        )
    except InfosimplesAdapterError as e:
        await db.commit()  # bronze (se houve) persiste para auditoria
        raise HTTPException(status_code=424, detail=str(e)) from e
    await db.commit()
    return view


@router.get("/consultas/protesto")
async def historico_protesto_avulso(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    documento: Annotated[str, Query(description="CNPJ/CPF")],
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> dict[str, Any]:
    """Última consulta de protesto de um CNPJ/CPF (silver). Vazio = nunca
    consultado."""
    from app.modules.credito.services.protesto_dossie import (
        build_protesto_view_by_documento,
    )

    doc = "".join(ch for ch in (documento or "") if ch.isdigit())
    if len(doc) not in (11, 14):
        return {"encontrado": False, "documento": doc, "mensagem": "Documento inválido."}
    return await build_protesto_view_by_documento(
        db, tenant_id=principal.tenant_id, documento=doc
    )
