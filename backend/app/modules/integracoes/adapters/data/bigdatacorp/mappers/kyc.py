"""Mappers KYC (API de Empresas) -> sujeitos + ocorrencias canonicos.

    kyc         -> map_kyc        -> 1 sujeito (a propria empresa)
    owners_kyc  -> map_owners_kyc -> N sujeitos (cada socio, keyed por CPF)

Funcoes PURAS. Cada ocorrencia (SanctionsHistory/PEPHistory) carrega
`MatchRate` (BDC casa por NOME — sem threshold enche de falso-positivo) e
`LastUpdateDate` -> frescor POR REGISTRO (source_updated_at). O header
(flags/contadores) representa o "nada consta" explicito; e dataset COMPUTADO
-> sem data de fonte (source_updated_at NULL).

Envelope:
    kyc:        Result[0].KycData
    owners_kyc: Result[0].OwnersKycData.PeopleOwnersKycData{<cpf>: KycRecord}
                Result[0].OwnersKycData.CompanyOwnersKycData{<cnpj>: KycRecord}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

_START_SENTINEL_YEARS = {1, 1900}
_END_SENTINEL_YEAR = 9999


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


def _parse_datetime(raw: Any) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s[:19])
        except ValueError:
            return None
    if dt.year in _START_SENTINEL_YEARS or dt.year == _END_SENTINEL_YEAR:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _parse_date(raw: Any) -> date | None:
    dt = _parse_datetime(raw)
    return dt.date() if dt is not None else None


@dataclass(frozen=True)
class KycOcorrenciaFields:
    categoria: str  # SANCTION | PEP
    fonte: str | None
    tipo: str | None
    match_rate: Decimal | None
    name_uniqueness_score: Decimal | None
    nome_original: str | None
    nome_sancao: str | None
    is_current: bool
    data_inicio: date | None
    data_fim: date | None
    detalhe: dict[str, Any] | None
    source_updated_at: datetime | None


@dataclass(frozen=True)
class KycSubjectFields:
    subject_documento: str | None
    subject_tipo: str | None  # PF | PJ
    subject_nome: str | None
    is_currently_pep: bool
    is_currently_sanctioned: bool
    was_previously_sanctioned: bool
    count_sanctions: int
    count_peps: int
    last_30_days_sanctions: int | None
    last_90_days_sanctions: int | None
    last_180_days_sanctions: int | None
    last_365_days_sanctions: int | None
    last_year_pep: int | None = None
    last_3y_pep: int | None = None
    last_5y_pep: int | None = None
    last_5plus_pep: int | None = None
    ocorrencias: list[KycOcorrenciaFields] = field(default_factory=list)


@dataclass(frozen=True)
class KycMapResult:
    found: bool
    dataset_status_code: int | None
    query_id: str | None
    subjects: list[KycSubjectFields]


def _status_code(payload: dict[str, Any], dataset: str) -> int | None:
    block = payload.get("Status")
    if isinstance(block, dict):
        entries = block.get(dataset)
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            code = entries[0].get("Code")
            if isinstance(code, int):
                return code
    return None


def _occurrence(item: dict[str, Any], categoria: str) -> KycOcorrenciaFields:
    details = item.get("Details") if isinstance(item.get("Details"), dict) else {}
    return KycOcorrenciaFields(
        categoria=categoria,
        fonte=_str_or_none(item.get("Source")),
        tipo=_str_or_none(
            item.get("StandardizedSanctionType") or item.get("Type")
        ),
        match_rate=_parse_decimal(item.get("MatchRate")),
        name_uniqueness_score=_parse_decimal(item.get("NameUniquenessScore")),
        nome_original=_str_or_none(details.get("OriginalName")),
        nome_sancao=_str_or_none(details.get("SanctionName")),
        is_current=bool(item.get("IsCurrentlyPresentOnSource", True)),
        data_inicio=_parse_date(item.get("StartDate")),
        data_fim=_parse_date(item.get("EndDate")),
        detalhe=details or None,
        source_updated_at=_parse_datetime(item.get("LastUpdateDate")),
    )


def _subject_from_record(
    record: dict[str, Any], *, documento: str | None, tipo: str | None
) -> KycSubjectFields:
    sanctions = record.get("SanctionsHistory")
    peps = record.get("PEPHistory")
    sanctions = sanctions if isinstance(sanctions, list) else []
    peps = peps if isinstance(peps, list) else []
    ocorrencias = [
        _occurrence(s, "SANCTION") for s in sanctions if isinstance(s, dict)
    ] + [_occurrence(p, "PEP") for p in peps if isinstance(p, dict)]
    return KycSubjectFields(
        subject_documento=documento,
        subject_tipo=tipo,
        subject_nome=next(
            (o.nome_original for o in ocorrencias if o.nome_original), None
        ),
        is_currently_pep=bool(record.get("IsCurrentlyPEP", False)),
        is_currently_sanctioned=bool(record.get("IsCurrentlySanctioned", False)),
        was_previously_sanctioned=bool(record.get("WasPreviouslySanctioned", False)),
        count_sanctions=len(sanctions),
        count_peps=len(peps),
        last_30_days_sanctions=_parse_int(record.get("Last30DaysSanctions")),
        last_90_days_sanctions=_parse_int(record.get("Last90DaysSanctions")),
        last_180_days_sanctions=_parse_int(record.get("Last180DaysSanctions")),
        last_365_days_sanctions=_parse_int(record.get("Last365DaysSanctions")),
        last_year_pep=_parse_int(record.get("LastYearPEPOccurence")),
        last_3y_pep=_parse_int(record.get("Last3YearsPEPOccurence")),
        last_5y_pep=_parse_int(record.get("Last5YearsPEPOccurence")),
        last_5plus_pep=_parse_int(record.get("Last5PlusYearsPEPOccurence")),
        ocorrencias=ocorrencias,
    )


def map_kyc(
    payload: dict[str, Any], *, cnpj: str, dataset: str = "kyc"
) -> KycMapResult:
    """KYC do sujeito-empresa: 1 subject (a propria PJ consultada)."""
    query_id = _str_or_none(payload.get("QueryId"))
    status_code = _status_code(payload, dataset)
    results = payload.get("Result")
    if not isinstance(results, list) or not results:
        return KycMapResult(False, status_code, query_id, [])
    kyc_data = results[0].get("KycData")
    if not isinstance(kyc_data, dict):
        return KycMapResult(False, status_code, query_id, [])
    digits = "".join(ch for ch in (cnpj or "") if ch.isdigit())
    subject = _subject_from_record(kyc_data, documento=digits, tipo="PJ")
    return KycMapResult(True, status_code, query_id, [subject])


def map_owners_kyc(
    payload: dict[str, Any], *, dataset: str = "owners_kyc"
) -> KycMapResult:
    """KYC dos socios: N subjects (keyed por documento)."""
    query_id = _str_or_none(payload.get("QueryId"))
    status_code = _status_code(payload, dataset)
    results = payload.get("Result")
    if not isinstance(results, list) or not results:
        return KycMapResult(False, status_code, query_id, [])
    owners = results[0].get("OwnersKycData")
    if not isinstance(owners, dict):
        return KycMapResult(False, status_code, query_id, [])

    subjects: list[KycSubjectFields] = []
    for bucket, tipo in (
        ("PeopleOwnersKycData", "PF"),
        ("CompanyOwnersKycData", "PJ"),
    ):
        block = owners.get(bucket)
        if not isinstance(block, dict):
            continue
        for doc, record in block.items():
            if isinstance(record, dict):
                digits = "".join(ch for ch in str(doc) if ch.isdigit())
                subjects.append(
                    _subject_from_record(record, documento=digits, tipo=tipo)
                )
    return KycMapResult(True, status_code, query_id, subjects)
