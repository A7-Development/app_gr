"""Map document extraction -> structured credit_dossier_financial (silver).

The document_extractor agent EXTRACTS raw values (DRE / Balance / Revenue);
this service computes the DETERMINISTIC indicators (margins, liquidity,
leverage) in Python — handoff esteira-credito §7: "o numero critico e Python
puro; o LLM le, o codigo calcula". Idempotente por documento de origem.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DocumentType
from app.modules.credito.models.dossier import CreditDossier
from app.modules.credito.models.financial import CreditDossierFinancial

# So estes tipos alimentam o silver financeiro.
_FINANCIAL_DOC_TYPES = {
    DocumentType.DRE.value,
    DocumentType.BALANCE_SHEET.value,
    DocumentType.REVENUE_REPORT.value,
}

_FOUR = Decimal("0.0001")


def _to_decimal(v: Any) -> Decimal | None:
    """Parse number/str (inclui formato BR '1.234.567,00') -> Decimal."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            return Decimal(str(v))
        except InvalidOperation:
            return None
    if isinstance(v, str):
        s = v.strip().replace("R$", "").replace(" ", "")
        if not s:
            return None
        # BR: virgula decimal -> remove pontos de milhar, troca virgula por ponto.
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        try:
            return Decimal(s)
        except InvalidOperation:
            return None
    return None


def _to_date(v: Any) -> date | None:
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        return date.fromisoformat(v.strip()[:10])
    except ValueError:
        return None


def _pct(num: Decimal | None, den: Decimal | None) -> Decimal | None:
    if num is None or den is None or den == 0:
        return None
    try:
        return (num / den * Decimal(100)).quantize(_FOUR)
    except (InvalidOperation, ZeroDivisionError):
        return None


def _ratio(num: Decimal | None, den: Decimal | None) -> Decimal | None:
    if num is None or den is None or den == 0:
        return None
    try:
        return (num / den).quantize(_FOUR)
    except (InvalidOperation, ZeroDivisionError):
        return None


async def persist_financial_from_extraction(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    document: Any,  # CreditDossierDocument com ai_extraction preenchido
) -> CreditDossierFinancial | None:
    """Grava credit_dossier_financial a partir de document.ai_extraction.

    No-op (None) quando: o tipo nao e financeiro, nao ha extracted_fields, ou
    falta periodo (period_start/end sao NOT NULL). Idempotente: substitui a
    linha do mesmo documento de origem (suporta reprocessar).
    """
    doc_type = (
        document.doc_type.value
        if hasattr(document.doc_type, "value")
        else str(document.doc_type)
    )
    if doc_type not in _FINANCIAL_DOC_TYPES:
        return None

    extraction = document.ai_extraction or {}
    fields = extraction.get("extracted_fields") if isinstance(extraction, dict) else None
    if not isinstance(fields, dict):
        return None

    period_start = _to_date(fields.get("period_start"))
    period_end = _to_date(fields.get("period_end"))
    if period_start is None or period_end is None:
        # Sem periodo nao da pra gravar (colunas NOT NULL). ai_extraction
        # permanece salvo no documento; o analista pode reprocessar.
        return None

    dossier = (
        await db.execute(
            select(CreditDossier).where(
                CreditDossier.tenant_id == tenant_id,
                CreditDossier.id == dossier_id,
            )
        )
    ).scalar_one_or_none()
    cnpj_raw = fields.get("cnpj") or (dossier.target_cnpj if dossier else None) or ""
    cnpj = str(cnpj_raw)[:20]

    revenue = _to_decimal(fields.get("revenue"))
    cogs = _to_decimal(fields.get("cogs"))
    gross_profit = _to_decimal(fields.get("gross_profit"))
    if gross_profit is None and revenue is not None and cogs is not None:
        gross_profit = revenue - cogs
    operating_expenses = _to_decimal(fields.get("operating_expenses"))
    ebitda = _to_decimal(fields.get("ebitda"))
    financial_result = _to_decimal(fields.get("financial_result"))
    net_income = _to_decimal(fields.get("net_income"))

    total_assets = _to_decimal(fields.get("total_assets"))
    current_assets = _to_decimal(fields.get("current_assets"))
    total_liabilities = _to_decimal(fields.get("total_liabilities"))
    current_liabilities = _to_decimal(fields.get("current_liabilities"))
    equity = _to_decimal(fields.get("equity"))

    # Idempotencia: remove linha previa deste documento (reprocessar).
    await db.execute(
        delete(CreditDossierFinancial).where(
            CreditDossierFinancial.tenant_id == tenant_id,
            CreditDossierFinancial.source_document_id == document.id,
        )
    )

    row = CreditDossierFinancial(
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        cnpj=cnpj,
        period_start=period_start,
        period_end=period_end,
        revenue=revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        operating_expenses=operating_expenses,
        ebitda=ebitda,
        financial_result=financial_result,
        net_income=net_income,
        total_assets=total_assets,
        current_assets=current_assets,
        total_liabilities=total_liabilities,
        current_liabilities=current_liabilities,
        equity=equity,
        # Indicadores DETERMINISTICOS (Python, nao o LLM).
        gross_margin_pct=_pct(gross_profit, revenue),
        ebitda_margin_pct=_pct(ebitda, revenue),
        net_margin_pct=_pct(net_income, revenue),
        current_ratio=_ratio(current_assets, current_liabilities),
        debt_to_equity=_ratio(total_liabilities, equity),
        source_type="self_declared",
        source_document_id=document.id,
    )
    db.add(row)
    await db.flush()
    return row
