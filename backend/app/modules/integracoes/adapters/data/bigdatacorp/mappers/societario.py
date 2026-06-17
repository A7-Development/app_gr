"""Mappers do Quadro Societario (API de Empresas) -> campos canonicos.

Cobre dois datasets de saida do pacote Quadro Societario:

    relationships / dynamic_qsa_data  -> map_relationships -> [VinculoFields]
    economic_group_first_level        -> map_economic_group -> GrupoIndicadorFields

Funcoes PURAS — sem DB, sem rede. Shape validado contra captura real
(`tests/.../bigdatacorp/fixtures/*.26239451000170.json`).

Frescor (§14): cada aresta em `relationships`/`dynamic_qsa_data` carrega
`LastUpdateDate` proprio (dataset de EVENTO) -> vira `source_updated_at` da
linha. O `economic_group` e DERIVADO (recalculado por consulta, sem
`LastUpdateDate`) -> `source_updated_at` fica NULL, idade = data da consulta.

Envelope esperado (POST /empresas):
    relationships:      Result[0].Relationships.Relationships[]
    dynamic_qsa_data:   Result[0].DynamicQSAData.Relationships.Relationships[]
    economic_group_*:   Result[0].NewEconomicGroups[0]
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# Datas-sentinela do BDC: inicio "vazio" (0001/1900) e fim "em aberto" (9999).
_START_SENTINEL_YEARS = {1, 1900}
_END_SENTINEL_YEAR = 9999


def _str_or_none(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _digits(raw: Any) -> str | None:
    if raw is None:
        return None
    d = "".join(ch for ch in str(raw) if ch.isdigit())
    return d or None


def _parse_int(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def _parse_datetime(raw: Any) -> datetime | None:
    """ISO com ou sem `Z`, com ou sem fracao. Naive -> assume UTC."""
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


def _is_end_open(raw: Any) -> bool:
    """RelationshipEndDate sentinel 9999 = vinculo em aberto (ativo)."""
    if not raw:
        return True
    s = str(raw).strip()
    return s.startswith("9999")


# ─────────────────────────── Vinculos (arestas) ────────────────────────────


@dataclass(frozen=True)
class VinculoFields:
    """Uma aresta do grafo societario/relacional."""

    documento_relacionado: str | None
    tipo_pessoa: str | None  # PF | PJ
    nome: str | None
    relationship_type: str | None
    relationship_name: str | None
    percentual: Decimal | None
    ativo: bool
    data_inicio: date | None
    data_fim: date | None
    # Frescor da fonte (LastUpdateDate da aresta) -> source_updated_at.
    source_updated_at: datetime | None


def _bool_or_none(raw: Any) -> bool | None:
    return None if raw is None else bool(raw)


@dataclass(frozen=True)
class VinculosResumo:
    """Resumo de topo do bloco relationships (atributos da empresa)."""

    qtd_socios: int | None
    qtd_empresas_possuidas: int | None
    empresa_familiar: bool | None
    operada_pela_familia: bool | None


@dataclass(frozen=True)
class RelationshipsMapResult:
    found: bool
    dataset_status_code: int | None
    query_id: str | None
    vinculos: list[VinculoFields]
    resumo: VinculosResumo | None = None


_TIPO_PESSOA = {"CPF": "PF", "CNPJ": "PJ"}

# Onde mora o objeto que contem a lista `Relationships` por dataset.
_REL_ROOT = {
    "relationships": "Relationships",
    "dynamic_qsa_data": "DynamicQSAData",
}


def _status_code(payload: dict[str, Any], dataset: str) -> int | None:
    block = payload.get("Status")
    if isinstance(block, dict):
        entries = block.get(dataset)
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            code = entries[0].get("Code")
            if isinstance(code, int):
                return code
    return None


def _edge_from_raw(item: dict[str, Any]) -> VinculoFields:
    end_raw = item.get("RelationshipEndDate")
    ativo = _is_end_open(end_raw)
    tipo_raw = _str_or_none(item.get("RelatedEntityTaxIdType"))
    return VinculoFields(
        documento_relacionado=_digits(item.get("RelatedEntityTaxIdNumber")),
        tipo_pessoa=_TIPO_PESSOA.get(tipo_raw or ""),
        nome=_str_or_none(item.get("RelatedEntityName")),
        relationship_type=_str_or_none(item.get("RelationshipType")),
        relationship_name=_str_or_none(item.get("RelationshipName")),
        # `relationships`/QSA nao trazem %; reservado p/ dataset de participacao.
        percentual=None,
        ativo=ativo,
        data_inicio=_parse_date(item.get("RelationshipStartDate")),
        data_fim=None if ativo else _parse_date(end_raw),
        source_updated_at=_parse_datetime(item.get("LastUpdateDate")),
    )


def map_relationships(
    payload: dict[str, Any], *, dataset: str = "relationships"
) -> RelationshipsMapResult:
    """Extrai as arestas do grafo de `relationships` ou `dynamic_qsa_data`.

    Usa a lista `Relationships` (uniao de current + historical) e deduplica
    por (documento, tipo, nome, inicio) — a fonte repete a mesma aresta entre
    as listas all/current/historical.
    """
    query_id = _str_or_none(payload.get("QueryId"))
    status_code = _status_code(payload, dataset)

    results = payload.get("Result")
    if not isinstance(results, list) or not results:
        return RelationshipsMapResult(False, status_code, query_id, [])

    root = results[0].get(_REL_ROOT.get(dataset, "Relationships"))
    if not isinstance(root, dict):
        return RelationshipsMapResult(False, status_code, query_id, [])

    # `relationships`: root JA e o holder (root["Relationships"] e lista).
    # `dynamic_qsa_data`: root["Relationships"] e um dict holder -> desce.
    holder = root
    inner = root.get("Relationships")
    if isinstance(inner, dict):
        holder = inner

    resumo = VinculosResumo(
        qtd_socios=_parse_int(holder.get("TotalOwners")),
        qtd_empresas_possuidas=_parse_int(holder.get("TotalOwned")),
        empresa_familiar=_bool_or_none(holder.get("IsFamilyCompany")),
        operada_pela_familia=_bool_or_none(holder.get("IsFamilyOperated")),
    )

    edges_raw = holder.get("Relationships")
    if not isinstance(edges_raw, list):
        return RelationshipsMapResult(True, status_code, query_id, [], resumo)

    seen: set[tuple] = set()
    vinculos: list[VinculoFields] = []
    for item in edges_raw:
        if not isinstance(item, dict):
            continue
        edge = _edge_from_raw(item)
        key = (
            edge.documento_relacionado,
            edge.relationship_type,
            edge.relationship_name,
            edge.data_inicio,
        )
        if key in seen:
            continue
        seen.add(key)
        vinculos.append(edge)

    return RelationshipsMapResult(True, status_code, query_id, vinculos, resumo)


# ───────────────────────── Indicadores do grupo ────────────────────────────


@dataclass(frozen=True)
class GrupoIndicadorFields:
    """Rollup do grupo economico de 1o nivel."""

    total_companies: int | None
    total_active: int | None
    total_inactive: int | None
    total_people: int | None
    total_owners: int | None
    total_sanctioned: int | None
    total_peps: int | None
    total_lawsuits: int | None
    total_bad_passages: int | None
    avg_activity_level: Decimal | None
    min_company_age: int | None
    max_company_age: int | None
    avg_company_age: int | None
    first_passage_date: datetime | None
    last_passage_date: datetime | None
    last_12m_passages: int | None
    faturamento_faixa: str | None = None
    faturamento_faixa_min: str | None = None
    faturamento_faixa_max: str | None = None
    faturamento_faixa_media: str | None = None
    funcionarios_faixa: str | None = None
    funcionarios_faixa_min: str | None = None
    funcionarios_faixa_max: str | None = None
    funcionarios_faixa_media: str | None = None
    cnaes: list | None = None


@dataclass(frozen=True)
class GrupoIndicadorMapResult:
    found: bool
    dataset_status_code: int | None
    query_id: str | None
    fields: GrupoIndicadorFields | None


def map_economic_group(
    payload: dict[str, Any], *, dataset: str = "economic_group_first_level"
) -> GrupoIndicadorMapResult:
    """Extrai os contadores do grupo economico de `economic_group_first_level`."""
    query_id = _str_or_none(payload.get("QueryId"))
    status_code = _status_code(payload, dataset)

    results = payload.get("Result")
    if not isinstance(results, list) or not results:
        return GrupoIndicadorMapResult(False, status_code, query_id, None)

    groups = results[0].get("NewEconomicGroups")
    if not isinstance(groups, list) or not groups or not isinstance(groups[0], dict):
        return GrupoIndicadorMapResult(False, status_code, query_id, None)

    g = groups[0]
    fields = GrupoIndicadorFields(
        total_companies=_parse_int(g.get("TotalCompanies")),
        total_active=_parse_int(g.get("TotalActiveCompanies")),
        total_inactive=_parse_int(g.get("TotalInactiveCompanies")),
        total_people=_parse_int(g.get("TotalPeople")),
        total_owners=_parse_int(g.get("TotalOwners")),
        total_sanctioned=_parse_int(g.get("TotalSanctioned")),
        total_peps=_parse_int(g.get("TotalPEPs")),
        total_lawsuits=_parse_int(g.get("TotalLawsuits")),
        total_bad_passages=_parse_int(g.get("TotalBadPassages")),
        avg_activity_level=_parse_decimal(g.get("AverageActivityLevel")),
        min_company_age=_parse_int(g.get("MinCompanyAge")),
        max_company_age=_parse_int(g.get("MaxCompanyAge")),
        avg_company_age=_parse_int(g.get("AverageCompanyAge")),
        first_passage_date=_parse_datetime(g.get("FirstPassageDate")),
        last_passage_date=_parse_datetime(g.get("LastPassageDate")),
        last_12m_passages=_parse_int(g.get("Last12MonthsPassages")),
        faturamento_faixa=_str_or_none(g.get("TotalIncomeRange")),
        faturamento_faixa_min=_str_or_none(g.get("MinIncomeRange")),
        faturamento_faixa_max=_str_or_none(g.get("MaxIncomeRange")),
        faturamento_faixa_media=_str_or_none(g.get("AverageIncomeRange")),
        funcionarios_faixa=_str_or_none(g.get("TotalEmployeesRange")),
        funcionarios_faixa_min=_str_or_none(g.get("MinEmployeesRange")),
        funcionarios_faixa_max=_str_or_none(g.get("MaxEmployeesRange")),
        funcionarios_faixa_media=_str_or_none(g.get("AverageEmployeesRange")),
        cnaes=(
            g.get("EconomicActivities")
            if isinstance(g.get("EconomicActivities"), list)
            else None
        ),
    )
    return GrupoIndicadorMapResult(True, status_code, query_id, fields)
