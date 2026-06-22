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
from app.modules.integracoes.public import FONTE_CENPROT_SP, FONTES_VALIDAS

router = APIRouter()


class ConsultaProtestoIn(BaseModel):
    """Corpo da consulta avulsa de protesto (página Consultas)."""

    documento: str = Field(..., description="CNPJ (14) ou CPF (11) — com ou sem máscara.")
    # 'cenprot_sp' (robusta, sem login, com cancelamento/quitacao, sem credor) |
    # 'ieptb_credor' (com credor, via login gov.br — gated).
    fonte: str = Field(default=FONTE_CENPROT_SP)


def _valida_fonte(fonte: str) -> str:
    if fonte not in FONTES_VALIDAS:
        raise HTTPException(
            status_code=422,
            detail=f"fonte inválida: {fonte!r}. Use uma de {list(FONTES_VALIDAS)}.",
        )
    return fonte


@router.post("/dossies/{dossier_id}/protestos/consultar")
async def consultar_protestos(
    dossier_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fonte: Annotated[str, Query(description="cenprot_sp | ieptb_credor")] = FONTE_CENPROT_SP,
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> dict[str, Any]:
    """Consulta protestos da empresa-alvo na `fonte` e materializa o silver.
    Bronze de cada chamada em wh_infosimples_raw_consulta."""
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
            fonte=_valida_fonte(fonte),
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


@router.post("/consultas/protesto")
async def consultar_protesto_avulso_endpoint(
    body: ConsultaProtestoIn,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = Depends(require_module(Module.CREDITO, Permission.WRITE)),
) -> dict[str, Any]:
    """Consulta protestos de um CNPJ/CPF avulso (sem dossiê) na `fonte` e devolve
    a view. Materializa silver + bronze (auditável)."""
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
            fonte=_valida_fonte(body.fonte),
            initiated_by=principal.user_id,
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
    fonte: Annotated[str, Query(description="cenprot_sp | ieptb_credor")] = FONTE_CENPROT_SP,
    _: None = Depends(require_module(Module.CREDITO, Permission.READ)),
) -> dict[str, Any]:
    """Última consulta de protesto de um CNPJ/CPF na `fonte` (silver). Vazio =
    nunca consultado."""
    from app.modules.credito.services.protesto_dossie import (
        build_protesto_view_by_documento,
    )

    doc = "".join(ch for ch in (documento or "") if ch.isdigit())
    if len(doc) not in (11, 14):
        return {"encontrado": False, "documento": doc, "mensagem": "Documento inválido."}
    return await build_protesto_view_by_documento(
        db, tenant_id=principal.tenant_id, documento=doc, fonte=_valida_fonte(fonte)
    )
