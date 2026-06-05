"""Montagem do payload de faturamento homologado (+ analytics + atestação).

Fonte ÚNICA consumida tanto pela read-tool `get_declaracao_faturamento`
(agente) quanto pelo endpoint `GET /dossies/{id}/faturamento/analytics`
(tela do checkpoint). Mantém o que o agente JULGOU e o que a tela MOSTRA
ancorados no mesmo fato determinístico (CLAUDE.md §14).

Lê hoje o homologado direto do `ai_extraction.extracted_fields` do documento
`revenue_report` (JSONB). Quando a silver canônica de revenue existir, só
este service muda — tool e endpoint não percebem.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DocumentType
from app.modules.credito.services.revenue_analytics import (
    analyze_revenue_series,
    attestation_signals,
)


def _to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


async def build_faturamento_payload(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> dict[str, Any]:
    """Monta série homologada + analytics determinístico + sinais de atestação.

    Returns:
        Dict com `encontrado=False` + mensagem quando não há declaração
        extraída; senão `{encontrado, homologado, fonte, periodo, analytics,
        atestacao}`. Shape estável — é o contrato lido pelo agente e pela UI.
    """
    from app.modules.credito.models.document import CreditDossierDocument
    from app.modules.credito.services.dossier import get_dossier

    row = (
        await db.execute(
            select(CreditDossierDocument)
            .where(
                CreditDossierDocument.tenant_id == tenant_id,
                CreditDossierDocument.dossier_id == dossier_id,
                CreditDossierDocument.doc_type == DocumentType.REVENUE_REPORT,
                CreditDossierDocument.ai_extraction.isnot(None),
            )
            .order_by(desc(CreditDossierDocument.uploaded_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        return {
            "encontrado": False,
            "mensagem": (
                "Nenhuma declaração de faturamento extraída no dossie. "
                "Não há base para análise."
            ),
        }

    extraction = row.ai_extraction or {}
    fields = extraction.get("extracted_fields")
    if not isinstance(fields, dict):
        fields = {}

    declared_total = _to_float(fields.get("revenue"))
    analytics = analyze_revenue_series(
        fields.get("monthly"), declared_total=declared_total
    )

    dossier = await get_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)
    target_cnpj = dossier.target_cnpj if dossier else None

    atestacao = attestation_signals(
        fields.get("documento"),
        target_cnpj=target_cnpj,
        ref_date=date.today(),
    )

    return {
        "encontrado": True,
        "homologado": row.extraction_status == "validated",
        "fonte": {
            "documento_id": str(row.id),
            "arquivo": row.original_filename,
            "status_extracao": row.extraction_status,
            "confianca": (
                float(row.extraction_confidence)
                if row.extraction_confidence is not None
                else None
            ),
            "modelo": row.ai_model_used,
            "prompt": row.ai_prompt_version,
            "enviado_em": row.uploaded_at.isoformat() if row.uploaded_at else None,
            "ajustado_pelo_analista": bool(extraction.get("_analyst_edited")),
        },
        "periodo": {
            "inicio": fields.get("period_start"),
            "fim": fields.get("period_end"),
        },
        "analytics": analytics.to_dict(),
        "atestacao": atestacao,
    }
