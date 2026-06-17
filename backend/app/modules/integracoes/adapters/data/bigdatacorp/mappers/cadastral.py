"""Mapper do dataset `basic_data` (API de Empresas) -> campos cadastrais.

Le o envelope BDC cru e extrai os campos canonicos consumidos pelo gate
A2 do credito (CLAUDE.md secao 19, esteira de credito):

    TaxIdStatus                       -> tax_status        (check company_status_active)
    Activities[]{IsMain,Code,Activity}-> cnaes             (check cnae_permitido)
    AdditionalOutputData.CapitalRS    -> capital_social    (cross-check proporcionalidade)
    FoundedDate                       -> founding_date     (check company_founding_age)
    OfficialName / TradeName          -> official_name / trade_name

Funcao PURA — sem DB, sem rede. Shape de referencia validado contra o
exemplo "Com dados" da doc oficial:
https://docs.bigdatacorp.com.br/plataforma/reference/empresas-dados-cadastrais-basicos

Envelope esperado:
    {
      "Result": [ { "MatchKeys": "doc{...}", "BasicData": { ... } } ],
      "Status": { "basic_data": [ { "Code": 0, "Message": "OK" } ] },
      "QueryId": "...", ...
    }
`Result: []` = "sem dados" (CNPJ nao encontrado) -> found=False.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class CadastralFields:
    """Campos cadastrais canonicos extraidos de `basic_data`."""

    tax_status: str | None
    cnaes: list[dict[str, Any]]
    capital_social: Decimal | None
    founding_date: date | None
    official_name: str | None
    trade_name: str | None
    tax_id_number: str | None
    # BasicData cru — vai pra credit_dossier_company.receita_data (preserva
    # tudo que nao virou coluna).
    basic_data: dict[str, Any] = field(default_factory=dict)
    # ── Campos promovidos do basic_data (selecao Ricardo 2026-06-17) ──
    regime_tributario: str | None = None  # TaxRegime
    porte: str | None = None  # CompanyType_ReceitaFederal (ME/EPP/Demais)
    optante_simples: bool | None = None  # TaxRegimes.Simples
    natureza_juridica_codigo: str | None = None  # LegalNature.Code
    natureza_juridica: str | None = None  # LegalNature.Activity
    situacao_especial: str | None = None  # SpecialSituation (RJ/falida)
    situacao_cadastral_desde: date | None = None  # TaxIdStatusDate
    data_inicio_atividade: date | None = None  # TaxIdStatusRegistrationDate
    origem_cadastral: str | None = None  # TaxIdOrigin
    mudou_nome: bool | None = None  # HistoricalData.HasChangedTradeName
    mudou_regime: bool | None = None  # HistoricalData.HasChangedTaxRegime
    # [{valor, desde, ate}] de HistoricalDataEvolution.TradeName
    historico_nomes: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class CadastralMapResult:
    """Resultado do mapper sobre um envelope BDC."""

    found: bool
    # Code do Status.<dataset>[0] (0 = OK). None quando o envelope nao trouxe.
    dataset_status_code: int | None
    query_id: str | None
    fields: CadastralFields | None


def _parse_capital(raw: Any) -> Decimal | None:
    """CapitalRS vem como string dot-decimal (ex.: "8385000.00")."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        value = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    # Capital negativo ou absurdo nao faz sentido — descarta valor sentinela.
    return value if value > 0 else None


# Datas-sentinela do BDC (campo "vazio") — nao viram founding_date real.
_SENTINEL_YEARS = {1, 1900}


def _parse_iso_date(raw: Any) -> date | None:
    """FoundedDate vem ISO com sufixo Z (ex.: "2007-04-03T00:00:00Z")."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Normaliza Z -> +00:00 para fromisoformat (py 3.11 aceita Z, mas defensivo).
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Tenta so a parte de data.
        try:
            dt = datetime.fromisoformat(s[:10])
        except ValueError:
            return None
    if dt.year in _SENTINEL_YEARS:
        return None
    return dt.date()


def _parse_activities(raw: Any) -> list[dict[str, Any]]:
    """Activities[] -> [{code, is_main, name}] (normalizado, sem mascara)."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = item.get("Code")
        if code is None:
            continue
        out.append(
            {
                "code": str(code).strip(),
                "is_main": bool(item.get("IsMain", False)),
                "name": item.get("Activity"),
            }
        )
    return out


def _str_or_none(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _bool_or_none(raw: Any) -> bool | None:
    """None quando ausente; senao coage o JSON bool da fonte."""
    return None if raw is None else bool(raw)


def _parse_nome_evolucao(raw: Any) -> list[dict[str, Any]] | None:
    """HistoricalDataEvolution.TradeName[] -> [{valor, desde, ate}]."""
    if not isinstance(raw, list):
        return None
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        desde = _parse_iso_date(item.get("StartDate"))
        ate = _parse_iso_date(item.get("EndDate"))
        out.append(
            {
                "valor": _str_or_none(item.get("Value")),
                "desde": desde.isoformat() if desde else None,
                "ate": ate.isoformat() if ate else None,
            }
        )
    return out or None


def map_basic_data(payload: dict[str, Any], *, dataset: str = "basic_data") -> CadastralMapResult:
    """Extrai campos cadastrais do envelope BDC `basic_data`.

    Args:
        payload: envelope cru devolvido pelo BDC em POST /empresas.
        dataset: nome tecnico do dataset (para ler `Status.<dataset>`).

    Returns:
        `CadastralMapResult`. `found=False` quando `Result` veio vazio.
    """
    query_id = _str_or_none(payload.get("QueryId"))

    status_code: int | None = None
    status_block = payload.get("Status")
    if isinstance(status_block, dict):
        entries = status_block.get(dataset)
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            code = entries[0].get("Code")
            if isinstance(code, int):
                status_code = code

    results = payload.get("Result")
    if not isinstance(results, list) or not results:
        return CadastralMapResult(
            found=False,
            dataset_status_code=status_code,
            query_id=query_id,
            fields=None,
        )

    first = results[0]
    basic = first.get("BasicData") if isinstance(first, dict) else None
    if not isinstance(basic, dict):
        return CadastralMapResult(
            found=False,
            dataset_status_code=status_code,
            query_id=query_id,
            fields=None,
        )

    additional = basic.get("AdditionalOutputData")
    capital_raw = (
        additional.get("CapitalRS") if isinstance(additional, dict) else None
    )
    legal = basic.get("LegalNature")
    legal = legal if isinstance(legal, dict) else {}
    historical = basic.get("HistoricalData")
    historical = historical if isinstance(historical, dict) else {}
    evolution = historical.get("HistoricalDataEvolution")
    evolution = evolution if isinstance(evolution, dict) else {}
    tax_regimes = basic.get("TaxRegimes")
    tax_regimes = tax_regimes if isinstance(tax_regimes, dict) else {}

    fields = CadastralFields(
        tax_status=_str_or_none(basic.get("TaxIdStatus")),
        cnaes=_parse_activities(basic.get("Activities")),
        capital_social=_parse_capital(capital_raw),
        founding_date=_parse_iso_date(basic.get("FoundedDate")),
        official_name=_str_or_none(basic.get("OfficialName")),
        trade_name=_str_or_none(basic.get("TradeName")),
        tax_id_number=_str_or_none(basic.get("TaxIdNumber")),
        basic_data=basic,
        regime_tributario=_str_or_none(basic.get("TaxRegime")),
        porte=_str_or_none(basic.get("CompanyType_ReceitaFederal")),
        optante_simples=_bool_or_none(tax_regimes.get("Simples")),
        natureza_juridica_codigo=_str_or_none(legal.get("Code")),
        natureza_juridica=_str_or_none(legal.get("Activity")),
        situacao_especial=_str_or_none(basic.get("SpecialSituation")),
        situacao_cadastral_desde=_parse_iso_date(basic.get("TaxIdStatusDate")),
        data_inicio_atividade=_parse_iso_date(
            basic.get("TaxIdStatusRegistrationDate")
        ),
        origem_cadastral=_str_or_none(basic.get("TaxIdOrigin")),
        mudou_nome=_bool_or_none(historical.get("HasChangedTradeName")),
        mudou_regime=_bool_or_none(historical.get("HasChangedTaxRegime")),
        historico_nomes=_parse_nome_evolucao(evolution.get("TradeName")),
    )

    return CadastralMapResult(
        found=True,
        dataset_status_code=status_code,
        query_id=query_id,
        fields=fields,
    )
