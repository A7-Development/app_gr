"""Protestos no dossie -- consulta Infosimples (CENPROT) + silver + view do agente.

Orquestra (consumindo `integracoes/public.py`, §11.3):
  1. fetch_protestos (nacional + detalhe SP) do CNPJ/CPF da empresa-alvo
  2. materializa o canonico em `wh_protesto_consulta` + `wh_protesto_titulo`
     (silver, idempotente por source_id = str(raw_id))
  3. expoe `build_protesto_agent_view` -> a read-tool `get_protestos` le daqui

Silver-first (§13.2.1): a tool/UI le SEMPRE do silver, nunca do raw. Re-mapear e
barato (raw imutavel) -> bug no mapper se corrige sem novo round-trip pago.

Provimento CNJ 225/2026: a consulta nacional NAO traz credor; o detalhe SP traz
(`nome_cedente`/`nome_apresentante`). A view sinaliza `com_credor` por titulo.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CompanyRole, SourceType, TrustLevel
from app.modules.credito.models.company import CreditDossierCompany
from app.modules.integracoes.public import (
    ProtestoConsultaResult,
    ProtestoParte,
    fetch_protestos,
)
from app.warehouse import WhProtestoConsulta, WhProtestoTitulo


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime | date):
        return v.isoformat()
    return v


async def _target_cnpj(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> str | None:
    doc = (
        await db.execute(
            select(CreditDossierCompany.cnpj).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()
    if not doc:
        return None
    digits = "".join(ch for ch in doc if ch.isdigit())
    return digits if len(digits) in (11, 14) else None


async def _persist_parte(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    part: ProtestoParte,
    documento: str,
    documento_tipo: str,
    consultado_em: datetime,
    adapter_version: str,
) -> WhProtestoConsulta | None:
    """Materializa uma 'perna' (nacional ou detalhe SP) no silver.

    Idempotente: source_id = str(raw_id). Re-persistir o mesmo raw apaga o
    header anterior (cascade nas filhas) e reescreve.
    """
    if part.fields is None or part.raw_id is None:
        return None
    source_id = str(part.raw_id)

    # Re-map idempotente: limpa o header anterior deste raw (cascade nos titulos).
    await db.execute(
        delete(WhProtestoConsulta).where(
            WhProtestoConsulta.tenant_id == tenant_id,
            WhProtestoConsulta.source_id == source_id,
        )
    )

    f = part.fields
    header = WhProtestoConsulta(
        tenant_id=tenant_id,
        raw_id=part.raw_id,
        documento=documento,
        documento_tipo=documento_tipo,
        escopo=part.escopo,
        uf_consultada=part.uf,
        consultado_em=consultado_em,
        constam_protestos=f.constam_protestos,
        qtd_total=f.qtd_total,
        valor_total=f.valor_total,
        com_credor=f.com_credor,
        observacoes=f.observacoes,
        source_type=SourceType.DATA_INFOSIMPLES_PROTESTO,
        source_id=source_id,
        source_updated_at=consultado_em,
        ingested_by_version=adapter_version,
        trust_level=TrustLevel.HIGH,
    )
    db.add(header)
    await db.flush()  # header.id

    for idx, t in enumerate(f.titulos):
        db.add(
            WhProtestoTitulo(
                tenant_id=tenant_id,
                consulta_id=header.id,
                cartorio=t.cartorio,
                cartorio_numero=t.cartorio_numero,
                cidade=t.cidade,
                uf=t.uf,
                data_protesto=t.data_protesto,
                data_vencimento=t.data_vencimento,
                valor=t.valor,
                credor=t.credor,
                documento_credor=t.documento_credor,
                especie=t.especie,
                detalhe=t.detalhe or None,
                source_type=SourceType.DATA_INFOSIMPLES_PROTESTO,
                source_id=f"{source_id}:{idx}",
                source_updated_at=consultado_em,
                ingested_by_version=adapter_version,
                trust_level=TrustLevel.HIGH,
            )
        )
    await db.flush()
    return header


async def _persist_result(
    db: AsyncSession, *, tenant_id: UUID, result: ProtestoConsultaResult
) -> datetime:
    """Materializa todas as pernas (nacional + SP) no silver. Retorna o
    `consultado_em` compartilhado (agrupa o 'run' das pernas)."""
    consultado_em = datetime.now(UTC)
    for part in (result.nacional, *result.detalhes_sp):
        if part is not None:
            await _persist_parte(
                db,
                tenant_id=tenant_id,
                part=part,
                documento=result.documento,
                documento_tipo=result.documento_tipo,
                consultado_em=consultado_em,
                adapter_version=result.adapter_version,
            )
    return consultado_em


async def consultar_e_persistir_protestos(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    initiated_by: UUID | None = None,
    incluir_detalhe_sp: bool = True,
) -> dict[str, Any]:
    """Consulta protestos da empresa-alvo e materializa o silver. Caller commita.

    Returns: resumo (encontrado, documento, qtd_total, valor_total, com_credor,
    cartorios_sp_detalhados, message).
    """
    cnpj = await _target_cnpj(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if cnpj is None:
        return {
            "encontrado": False,
            "message": (
                "O dossiê não tem CNPJ/CPF da empresa-alvo — preencha a "
                "identificação antes de consultar protestos."
            ),
        }

    result = await fetch_protestos(
        db,
        tenant_id=tenant_id,
        documento=cnpj,
        documento_tipo="cpf" if len(cnpj) == 11 else "cnpj",
        incluir_detalhe_sp=incluir_detalhe_sp,
        triggered_by=f"dossie:{dossier_id}",
    )

    if not result.found:
        return {
            "encontrado": False,
            "documento": cnpj,
            "transitorio": result.transient,
            "message": result.message or "Consulta não completou.",
        }

    consultado_em = await _persist_result(db, tenant_id=tenant_id, result=result)
    partes = [result.nacional, *result.detalhes_sp]

    nac = result.nacional.fields if result.nacional else None
    com_credor = any(
        p.fields and p.fields.com_credor for p in partes if p is not None
    )
    return {
        "encontrado": True,
        "documento": result.documento,
        "consultado_em": consultado_em.isoformat(),
        "constam_protestos": bool(nac and nac.constam_protestos),
        "qtd_total": (nac.qtd_total if nac else 0),
        "valor_total": _jsonable(nac.valor_total) if nac else None,
        "com_credor": com_credor,
        "cartorios_sp_detalhados": len(result.detalhes_sp),
        "message": None,
    }


async def build_protesto_view_by_documento(
    db: AsyncSession, *, tenant_id: UUID, documento: str
) -> dict[str, Any]:
    """Visão de protestos de um CNPJ/CPF (silver, último 'run')."""
    cnpj = documento

    # Último 'run' = consultado_em mais recente do documento (nacional + SP
    # compartilham o mesmo timestamp por consulta).
    ultimo = (
        await db.execute(
            select(WhProtestoConsulta.consultado_em)
            .where(
                WhProtestoConsulta.tenant_id == tenant_id,
                WhProtestoConsulta.documento == cnpj,
            )
            .order_by(WhProtestoConsulta.consultado_em.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if ultimo is None:
        return {
            "encontrado": False,
            "documento": cnpj,
            "mensagem": (
                "Sem consulta de protesto para esta empresa. Rode a consulta "
                "antes (botão Consultar protestos / endpoint)."
            ),
        }

    headers = (
        (
            await db.execute(
                select(WhProtestoConsulta).where(
                    WhProtestoConsulta.tenant_id == tenant_id,
                    WhProtestoConsulta.documento == cnpj,
                    WhProtestoConsulta.consultado_em == ultimo,
                )
            )
        )
        .scalars()
        .all()
    )
    consulta_ids = [h.id for h in headers]
    titulos_rows = (
        (
            await db.execute(
                select(WhProtestoTitulo)
                .where(
                    WhProtestoTitulo.tenant_id == tenant_id,
                    WhProtestoTitulo.consulta_id.in_(consulta_ids),
                )
                .order_by(
                    WhProtestoTitulo.data_protesto.desc().nullslast(),
                )
            )
        )
        .scalars()
        .all()
    )

    nac = next((h for h in headers if h.escopo == "nacional"), None)
    titulos = [
        {
            "cartorio": t.cartorio,
            "cidade": t.cidade,
            "uf": t.uf,
            "data_protesto": _jsonable(t.data_protesto),
            "data_vencimento": _jsonable(t.data_vencimento),
            "valor": _jsonable(t.valor),
            "credor": t.credor,
            "documento_credor": t.documento_credor,
            "especie": t.especie,
        }
        for t in titulos_rows
    ]
    # Reconciliacao (§14.6): a soma dos titulos exibidos bate com o headline
    # quando a fonte deu detalhe por titulo. Quando so veio agregado nacional,
    # `titulos` vem vazio e o headline carrega qtd/valor (sem tabela conflitante).
    com_credor = sum(1 for t in titulos if t["credor"])
    return {
        "encontrado": True,
        "documento": cnpj,
        "consultado_em": _jsonable(ultimo),
        "constam_protestos": bool(nac and nac.constam_protestos),
        "qtd_total": (nac.qtd_total if nac else len(titulos)),
        "valor_total": _jsonable(nac.valor_total) if nac else None,
        "observacoes": (nac.observacoes if nac else None),
        "cartorios_sp_detalhados": sum(
            1 for h in headers if h.escopo == "sp_detalhe"
        ),
        "titulos_com_credor": com_credor,
        "titulos": titulos,
        "nota": (
            "Protesto via CENPROT/IEPTB. A consulta NACIONAL não identifica o "
            "credor (Provimento CNJ 225/2026); o credor (cedente/apresentante) "
            "só aparece no detalhe de cartórios de SP. titulos[].credor nulo = "
            "fonte não identificou, NÃO 'sem credor'. Protesto é dívida não "
            "paga levada a cartório: pesa na análise do sacado/cedente."
        ),
    }


async def build_protesto_agent_view(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> dict[str, Any] | None:
    """Visão de protestos da empresa-alvo do dossiê (silver). None se não há
    empresa-alvo. Thin wrapper sobre `build_protesto_view_by_documento`."""
    cnpj = await _target_cnpj(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if cnpj is None:
        return None
    return await build_protesto_view_by_documento(
        db, tenant_id=tenant_id, documento=cnpj
    )


async def consultar_protesto_avulso(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    documento: str,
    initiated_by: UUID | None = None,
    incluir_detalhe_sp: bool = True,
) -> dict[str, Any]:
    """Consulta protestos de um CNPJ/CPF AVULSO (sem dossiê) + materializa silver
    + devolve a view completa. Base da página `/credito/consultas/protestos`.
    Caller commita.
    """
    doc = "".join(ch for ch in (documento or "") if ch.isdigit())
    if len(doc) not in (11, 14):
        return {
            "encontrado": False,
            "documento": doc,
            "message": "Informe um CNPJ (14 dígitos) ou CPF (11 dígitos) válido.",
        }

    result = await fetch_protestos(
        db,
        tenant_id=tenant_id,
        documento=doc,
        documento_tipo="cpf" if len(doc) == 11 else "cnpj",
        incluir_detalhe_sp=incluir_detalhe_sp,
        triggered_by=f"consulta_avulsa:{initiated_by or '-'}",
    )
    if not result.found:
        return {
            "encontrado": False,
            "documento": doc,
            "transitorio": result.transient,
            "message": result.message or "Consulta não completou.",
        }

    await _persist_result(db, tenant_id=tenant_id, result=result)
    return await build_protesto_view_by_documento(
        db, tenant_id=tenant_id, documento=result.documento
    )
