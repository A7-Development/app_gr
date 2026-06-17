"""Mapper do dataset `company_evolution` (COMPANY_EVOLUTION_V1).

    company_evolution -> map_company_evolution -> header + serie mensal

Funcao PURA. O header agrega trajetoria (funcionarios/socios atual+max+min+
media + media 1/3/5a, YoY growth, atividade, qsa_mudou, faturamento atual); a
serie e a CURVA mensal (funcionarios + faixa de faturamento por mes). O
`atual` e o `faturamento_faixa_atual` saem do ULTIMO ponto da serie.

Envelope: Result[0].CompanyEvolutionData{ ...agregados..., DataHistoryOverTime[] }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def _str_or_none(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _parse_int(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_decimal(raw: Any) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def _parse_date(raw: Any) -> date | None:
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        try:
            return datetime.fromisoformat(s[:10]).date()
        except ValueError:
            return None


@dataclass(frozen=True)
class EvolucaoMensalFields:
    mes: date | None
    funcionarios: int | None
    faturamento_faixa: str | None


@dataclass(frozen=True)
class EvolucaoHeaderFields:
    funcionarios_atual: int | None
    funcionarios_max: int | None
    funcionarios_min: int | None
    funcionarios_media: int | None
    funcionarios_distintos: int | None
    funcionarios_media_1a: int | None
    funcionarios_media_3a: int | None
    funcionarios_media_5a: int | None
    crescimento_yoy_1a: str | None
    crescimento_yoy_3a: str | None
    crescimento_yoy_5a: str | None
    qsa_mudou: bool | None
    faturamento_faixa_atual: str | None
    socios_max: int | None
    socios_min: int | None
    socios_media: int | None
    socios_distintos: int | None
    socios_media_1a: int | None
    socios_media_3a: int | None
    socios_media_5a: int | None
    atividade_max: Decimal | None
    atividade_min: Decimal | None
    atividade_media: Decimal | None


@dataclass(frozen=True)
class EvolucaoMapResult:
    found: bool
    dataset_status_code: int | None
    query_id: str | None
    header: EvolucaoHeaderFields | None
    serie: list[EvolucaoMensalFields] = field(default_factory=list)


def _status_code(payload: dict[str, Any], dataset: str) -> int | None:
    block = payload.get("Status")
    if isinstance(block, dict):
        entries = block.get(dataset)
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            code = entries[0].get("Code")
            if isinstance(code, int):
                return code
    return None


def map_company_evolution(
    payload: dict[str, Any], *, dataset: str = "company_evolution"
) -> EvolucaoMapResult:
    query_id = _str_or_none(payload.get("QueryId"))
    status_code = _status_code(payload, dataset)

    results = payload.get("Result")
    if not isinstance(results, list) or not results:
        return EvolucaoMapResult(False, status_code, query_id, None)
    e = results[0].get("CompanyEvolutionData")
    if not isinstance(e, dict):
        return EvolucaoMapResult(False, status_code, query_id, None)

    hist = e.get("DataHistoryOverTime")
    hist = [p for p in hist if isinstance(p, dict)] if isinstance(hist, list) else []
    serie = [
        EvolucaoMensalFields(
            mes=_parse_date(p.get("Reference")),
            funcionarios=_parse_int(p.get("QtyEmployees")),
            faturamento_faixa=_str_or_none(p.get("IncomeRange")),
        )
        for p in hist
    ]
    ultimo = hist[-1] if hist else {}

    header = EvolucaoHeaderFields(
        funcionarios_atual=_parse_int(ultimo.get("QtyEmployees")),
        funcionarios_max=_parse_int(e.get("MaxQtyEmployees")),
        funcionarios_min=_parse_int(e.get("MinQtyEmployees")),
        funcionarios_media=_parse_int(e.get("AverageQtyEmployees")),
        funcionarios_distintos=_parse_int(e.get("DistinctQtyEmployees")),
        funcionarios_media_1a=_parse_int(e.get("AverageQtyEmployees1YearAgo")),
        funcionarios_media_3a=_parse_int(e.get("AverageQtyEmployees3YearsAgo")),
        funcionarios_media_5a=_parse_int(e.get("AverageQtyEmployees5YearsAgo")),
        crescimento_yoy_1a=_str_or_none(e.get("YearOverYearGrowthRateStatus1YearAgo")),
        crescimento_yoy_3a=_str_or_none(e.get("YearOverYearGrowthRateStatus3YearsAgo")),
        crescimento_yoy_5a=_str_or_none(e.get("YearOverYearGrowthRateStatus5YearsAgo")),
        qsa_mudou=(
            None
            if e.get("HasQSAChangedAnytime") is None
            else bool(e.get("HasQSAChangedAnytime"))
        ),
        faturamento_faixa_atual=_str_or_none(ultimo.get("IncomeRange")),
        socios_max=_parse_int(e.get("MaxQtyQSA")),
        socios_min=_parse_int(e.get("MinQtyQSA")),
        socios_media=_parse_int(e.get("AverageQtyQSA")),
        socios_distintos=_parse_int(e.get("DistinctQtyQSA")),
        socios_media_1a=_parse_int(e.get("AverageQtyQSA1YearAgo")),
        socios_media_3a=_parse_int(e.get("AverageQtyQSA3YearsAgo")),
        socios_media_5a=_parse_int(e.get("AverageQtyQSA5YearsAgo")),
        atividade_max=_parse_decimal(e.get("MaxActivityLevel")),
        atividade_min=_parse_decimal(e.get("MinActivityLevel")),
        atividade_media=_parse_decimal(e.get("AverageActivityLevel")),
    )
    return EvolucaoMapResult(True, status_code, query_id, header, serie)
