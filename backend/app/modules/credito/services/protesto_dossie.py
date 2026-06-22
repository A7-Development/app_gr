"""Protestos -- consulta Infosimples + silver + views (avulso, dossie, agente).

Duas fontes (ver integracoes/infosimples_protesto):
  - cenprot_sp   (default): robusta, sem login, traz cancelamento/quitacao, sem credor.
  - ieptb_credor (gated):   com credor (cedente/apresentante), via login gov.br.

Materializa o canonico em `wh_protesto_consulta` + `wh_protesto_titulo` (silver,
idempotente por source_id = str(raw_id)). Silver-first (§13.2.1): tool/UI leem do
silver. Reconciliacao §14.6: a soma dos titulos exibidos bate com o headline; a
flag `completo` avisa quando a fonte so devolveu a 1a pagina.
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
    ESCOPO_CENPROT_SP,
    ESCOPO_IEPTB_DETALHE,
    ESCOPO_IEPTB_NACIONAL,
    ESCOPOS_POR_FONTE,
    FONTE_CENPROT_SP,
    ProtestoConsultaResult,
    ProtestoParte,
    fetch_protestos,
)
from app.warehouse import WhProtestoConsulta, WhProtestoTitulo

# Escopos cujo header carrega os totais "headline" (vs os detalhe-SP, que so
# trazem os titulos com credor).
_PRIMARY_ESCOPOS = (ESCOPO_CENPROT_SP, ESCOPO_IEPTB_NACIONAL)

_NOTA_POR_FONTE = {
    "cenprot_sp": (
        "Protesto via CENPROT-SP (protestosp.com.br). Traz cartório, valor "
        "protestado e os valores de cancelamento e quitação por título "
        "(tipicamente o custo para cancelar/quitar o protesto) — NÃO são status: "
        "o protesto pode estar ABERTO mesmo com esses valores preenchidos. NÃO "
        "identifica o credor e retorna só os protestos da 1ª página do site — "
        "quando `completo`=false, a lista é parcial vs o total. Só cobre SP. "
        "Protesto é dívida levada a cartório: pesa na análise do sacado/cedente."
    ),
    "ieptb_credor": (
        "Protesto via IEPTB/CENPROT (gov.br). O detalhe de cartórios de SP traz o "
        "CREDOR (cedente/apresentante). titulos[].credor nulo = fonte não "
        "identificou, NÃO 'sem credor'. Cobertura nacional para existência."
    ),
}


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
) -> None:
    """Materializa uma 'perna' no silver. Idempotente por source_id=str(raw_id):
    re-persistir o mesmo raw apaga o header anterior (cascade nas filhas)."""
    if part.fields is None or part.raw_id is None:
        return
    source_id = str(part.raw_id)
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
        completo=f.completo,
        com_credor=f.com_credor,
        observacoes=f.observacoes,
        source_type=SourceType.DATA_INFOSIMPLES_PROTESTO,
        source_id=source_id,
        source_updated_at=consultado_em,
        ingested_by_version=adapter_version,
        trust_level=TrustLevel.HIGH,
    )
    db.add(header)
    await db.flush()

    for idx, t in enumerate(f.titulos):
        db.add(
            WhProtestoTitulo(
                tenant_id=tenant_id,
                consulta_id=header.id,
                # No detalhe-SP do IEPTB o response nao repete o cartorio — herda
                # do contexto da perna (part.cartorio/cidade/uf).
                cartorio=t.cartorio or part.cartorio,
                cartorio_numero=t.cartorio_numero,
                cidade=t.cidade or part.cidade,
                uf=t.uf or part.uf,
                data_protesto=t.data_protesto,
                data_vencimento=t.data_vencimento,
                valor=t.valor,
                valor_cancelamento=t.valor_cancelamento,
                valor_quitacao=t.valor_quitacao,
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


async def _persist_result(
    db: AsyncSession, *, tenant_id: UUID, result: ProtestoConsultaResult
) -> datetime:
    """Materializa todas as pernas no silver. Retorna o consultado_em
    compartilhado (agrupa o 'run')."""
    consultado_em = datetime.now(UTC)
    for part in result.partes:
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


async def build_protesto_view_by_documento(
    db: AsyncSession, *, tenant_id: UUID, documento: str, fonte: str | None = None
) -> dict[str, Any]:
    """Visão de protestos de um CNPJ/CPF (silver, último 'run' da `fonte`).

    `fonte=None` = qualquer fonte (último run de qualquer escopo). Quando uma
    fonte é dada, filtra pelos escopos dela.
    """
    cnpj = documento
    escopos = ESCOPOS_POR_FONTE.get(fonte) if fonte else None

    base = select(WhProtestoConsulta.consultado_em).where(
        WhProtestoConsulta.tenant_id == tenant_id,
        WhProtestoConsulta.documento == cnpj,
    )
    if escopos:
        base = base.where(WhProtestoConsulta.escopo.in_(escopos))
    ultimo = (
        await db.execute(
            base.order_by(WhProtestoConsulta.consultado_em.desc()).limit(1)
        )
    ).scalar_one_or_none()

    if ultimo is None:
        return {
            "encontrado": False,
            "documento": cnpj,
            "fonte": fonte,
            "mensagem": "Sem consulta de protesto para este documento nesta fonte.",
        }

    hq = select(WhProtestoConsulta).where(
        WhProtestoConsulta.tenant_id == tenant_id,
        WhProtestoConsulta.documento == cnpj,
        WhProtestoConsulta.consultado_em == ultimo,
    )
    if escopos:
        hq = hq.where(WhProtestoConsulta.escopo.in_(escopos))
    headers = (await db.execute(hq)).scalars().all()

    # Header headline = o primario (cenprot_sp ou ieptb_nacional); fallback 1o.
    primary = next((h for h in headers if h.escopo in _PRIMARY_ESCOPOS), headers[0])
    fonte_efetiva = (
        FONTE_CENPROT_SP if primary.escopo == ESCOPO_CENPROT_SP else "ieptb_credor"
    )

    # Titulos exibidos: os do detalhe-SP (com credor) quando houver; senao os do
    # header primario. Evita dupla contagem nacional+detalhe (§14.6).
    detalhe_ids = [h.id for h in headers if h.escopo == ESCOPO_IEPTB_DETALHE]
    title_header_ids = detalhe_ids or [primary.id]

    titulos_rows = (
        (
            await db.execute(
                select(WhProtestoTitulo)
                .where(
                    WhProtestoTitulo.tenant_id == tenant_id,
                    WhProtestoTitulo.consulta_id.in_(title_header_ids),
                )
                .order_by(WhProtestoTitulo.valor.desc().nullslast())
            )
        )
        .scalars()
        .all()
    )

    titulos = [
        {
            "cartorio": t.cartorio,
            "cidade": t.cidade,
            "uf": t.uf,
            "data_protesto": _jsonable(t.data_protesto),
            "valor": _jsonable(t.valor),
            "valor_cancelamento": _jsonable(t.valor_cancelamento),
            "valor_quitacao": _jsonable(t.valor_quitacao),
            "credor": t.credor,
            "documento_credor": t.documento_credor,
            "especie": t.especie,
        }
        for t in titulos_rows
    ]
    return {
        "encontrado": True,
        "documento": cnpj,
        "fonte": fonte_efetiva,
        "consultado_em": _jsonable(ultimo),
        "constam_protestos": primary.constam_protestos,
        "qtd_total": primary.qtd_total,
        "valor_total": _jsonable(primary.valor_total),
        "completo": primary.completo,
        "observacoes": primary.observacoes,
        "titulos_com_credor": sum(1 for t in titulos if t["credor"]),
        "titulos": titulos,
        "nota": _NOTA_POR_FONTE.get(fonte_efetiva, ""),
    }


async def build_protesto_agent_view(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID, fonte: str | None = None
) -> dict[str, Any] | None:
    """Visão de protestos da empresa-alvo do dossiê (silver). None se não há
    empresa-alvo. Thin wrapper sobre `build_protesto_view_by_documento`."""
    cnpj = await _target_cnpj(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if cnpj is None:
        return None
    return await build_protesto_view_by_documento(
        db, tenant_id=tenant_id, documento=cnpj, fonte=fonte
    )


async def consultar_protesto_avulso(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    documento: str,
    fonte: str = FONTE_CENPROT_SP,
    initiated_by: UUID | None = None,
) -> dict[str, Any]:
    """Consulta protestos de um CNPJ/CPF AVULSO (sem dossiê) na `fonte` + silver +
    view. Base das páginas `/credito/consultas/protestos*`. Caller commita."""
    doc = "".join(ch for ch in (documento or "") if ch.isdigit())
    if len(doc) not in (11, 14):
        return {
            "encontrado": False,
            "documento": doc,
            "fonte": fonte,
            "message": "Informe um CNPJ (14 dígitos) ou CPF (11 dígitos) válido.",
        }

    result = await fetch_protestos(
        db,
        tenant_id=tenant_id,
        documento=doc,
        fonte=fonte,
        triggered_by=f"consulta_avulsa:{initiated_by or '-'}",
    )
    if not result.found:
        return {
            "encontrado": False,
            "documento": doc,
            "fonte": fonte,
            "transitorio": result.transient,
            "message": result.message or "Consulta não completou.",
        }

    await _persist_result(db, tenant_id=tenant_id, result=result)
    return await build_protesto_view_by_documento(
        db, tenant_id=tenant_id, documento=result.documento, fonte=fonte
    )


async def consultar_e_persistir_protestos(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    fonte: str = FONTE_CENPROT_SP,
    initiated_by: UUID | None = None,
) -> dict[str, Any]:
    """Consulta protestos da empresa-alvo do dossiê e materializa o silver +
    devolve a view. Caller commita."""
    cnpj = await _target_cnpj(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if cnpj is None:
        return {
            "encontrado": False,
            "fonte": fonte,
            "message": (
                "O dossiê não tem CNPJ/CPF da empresa-alvo — preencha a "
                "identificação antes de consultar protestos."
            ),
        }
    return await consultar_protesto_avulso(
        db, tenant_id=tenant_id, documento=cnpj, fonte=fonte, initiated_by=initiated_by
    )
