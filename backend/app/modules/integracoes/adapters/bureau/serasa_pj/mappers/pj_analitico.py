"""Mapper: payload RELATORIO_AVANCADO_PJ_ANALITICO -> dicts canonicos.

Estrutura do payload real da Serasa (validado contra prod 2026-05-01,
segmento `028` factoring/FIDC):

    {
      "reports": [
        {
          "reportName": "RELATORIO_AVANCADO_PJ_ANALITICO",
          "identificationReport": { companyName, documentNumber, ... },
          "negativeData": {
            "pefin":             { summary, pefinResponse[] },
            "notary":            { summary, notaryResponse[] },   # protestos
            "check":             { summary [, checkResponse[]] },
            "refin":             { summary [, refinResponse[]] },
            "collectionRecords": { summary [, collectionRecordsResponse[]] }
          },
          "facts": { bankrupts, judgementFilings, inquiryCompanyResponse },
          "checkFilingsHistorical": {...},
          "advancedCommercialPaymentHistory": {...}
        }
      ]
    }

Diferencas em relacao a doc oficial:
    - O contrato A7 (segmento `028`) NAO retorna `scoring`, `partners`,
      `businessParticipation`. Esses produtos podem precisar de outro
      `reportName` ou outro segmento. Mapper deixa as colunas/listas
      vazias quando ausentes — nao levanta.

Nomes em portugues no silver:
    notary  -> tipo "protesto"
    check   -> tipo "cheque"
    pefin   -> tipo "pefin"
    refin   -> tipo "refin"
    collectionRecords -> tipo "collection"

Source IDs deterministicos (idempotencia em remap):
    consulta:      "<raw_id>"
    socio:         "<raw_id>|socio|<documento>"   (vazio enquanto nao vem)
    restricao:     "<raw_id>|<tipo>|<cadus>"      (cadus = ID unico Serasa)
    participacao:  "<raw_id>|participacao|<documento_empresa>"
    endereco:      "<raw_id>|endereco|0"          (1 endereco — nao e array)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.modules.integracoes.adapters.bureau.serasa_pj.liminar import (
    extract_negative_summary_message,
    is_suspeita_liminar,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.mappers._common import (
    as_list,
    build_provenance,
    get_block,
    normalize_str_or_none,
    parse_date_or_none,
    strip_non_digits,
    to_decimal_or_none,
)


@dataclass
class SerasaPjMappedRows:
    """Linhas canonicas derivadas de uma consulta PJ analitico."""

    consulta: dict[str, Any]
    socios: list[dict[str, Any]] = field(default_factory=list)
    restricoes: list[dict[str, Any]] = field(default_factory=list)
    restricao_summaries: list[dict[str, Any]] = field(default_factory=list)
    participacoes: list[dict[str, Any]] = field(default_factory=list)
    enderecos: list[dict[str, Any]] = field(default_factory=list)
    pagamento_buckets: list[dict[str, Any]] = field(default_factory=list)
    inquiries_anteriores: list[dict[str, Any]] = field(default_factory=list)
    predecessores: list[dict[str, Any]] = field(default_factory=list)
    inquiries_mensais: list[dict[str, Any]] = field(default_factory=list)
    business_references: list[dict[str, Any]] = field(default_factory=list)
    pagamento_evolucao_mensal: list[dict[str, Any]] = field(
        default_factory=list
    )
    atraso_medio_mensal: list[dict[str, Any]] = field(default_factory=list)
    payment_comparatives: list[dict[str, Any]] = field(default_factory=list)


# Tipos canonicos de restricao (coluna `tipo` em wh_serasa_pj_restricao).
# Mapeamento payload-Serasa -> tipo canonico (em portugues):
_RESTRICAO_PEFIN = "pefin"
_RESTRICAO_REFIN = "refin"
_RESTRICAO_PROTESTO = "protesto"   # vem de `notary` no payload
_RESTRICAO_CHEQUE = "cheque"       # vem de `check`
_RESTRICAO_COLLECTION = "collection"  # vem de `collectionRecords`


# Quando categoria existe no payload mas nao houve ocorrencia, a Serasa
# retorna apenas `summary` sem array de items. Esses contadores ainda
# precisam ir para o header (count_*=0, has_*=False).
_NEGATIVE_CATEGORIES = (
    # (chave_payload, tipo_canonico, chave_response)
    ("pefin", _RESTRICAO_PEFIN, "pefinResponse"),
    ("refin", _RESTRICAO_REFIN, "refinResponse"),
    ("notary", _RESTRICAO_PROTESTO, "notaryResponse"),
    ("check", _RESTRICAO_CHEQUE, "checkResponse"),
    ("collectionRecords", _RESTRICAO_COLLECTION, "collectionRecordsResponse"),
)


def map_pj_analitico(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    raw_id: UUID,
    cnpj: str,
    consulted_at: datetime,
    requested_report: str,
    actual_report_returned: str,
) -> SerasaPjMappedRows:
    """Transforma payload Serasa PJ em linhas canonicas (silver).

    Args:
        payload: body JSON da resposta Serasa (igual ao que foi gravado
            em `wh_serasa_pj_raw_relatorio.payload`).
        tenant_id: dono da consulta.
        raw_id: PK da linha bronze que originou esta consulta.
        cnpj: 14 digitos (ja normalizado pelo client).
        consulted_at: quando a consulta foi feita (= raw.fetched_at).
        requested_report: o que pedimos (`reportName` enviado).
        actual_report_returned: o que veio (`reportName` no payload).

    Returns:
        `SerasaPjMappedRows` com `consulta` (sempre 1) + N filhas.
    """
    consulta_id = uuid4()
    ingested_at = datetime.now(UTC)
    cnpj = strip_non_digits(cnpj)
    raw_str = str(raw_id)

    # ─── Descer pra reports[0] ─────────────────────────────────────────────
    # O payload da Serasa envelopa tudo em `{"reports": [{...}]}`. Caller
    # passa o body inteiro; mapper resolve o envelope.
    report = _extract_report(payload)

    identification = report.get("identificationReport") or {}
    negative = report.get("negativeData") or {}

    # ─── Supressao judicial (regra serasa_liminar_v1) ──────────────────────
    # "NADA CONSTA" explicito em negativeSummary = padrao de liminar
    # escondendo apontamentos (limpo genuino vem SEM message).
    negative_summary_message = extract_negative_summary_message(report)
    suspeita_liminar = is_suspeita_liminar(negative_summary_message)

    # ─── Restricoes (silver + contadores agregados) ────────────────────────
    restricoes_rows: list[dict[str, Any]] = []
    restricao_summary_rows: list[dict[str, Any]] = []
    counters_per_tipo: dict[str, dict[str, Any]] = {}

    for category_key, tipo_canonico, response_key in _NEGATIVE_CATEGORIES:
        category = negative.get(category_key) or {}
        summary = category.get("summary") or {}
        items = as_list(category.get(response_key))

        first_occurrence = parse_date_or_none(summary.get("firstOccurrence"))
        last_occurrence = parse_date_or_none(summary.get("lastOccurrence"))

        # Counters pro header.
        counters_per_tipo[tipo_canonico] = {
            "count": int(summary.get("count") or 0),
            "balance": to_decimal_or_none(summary.get("balance")),
            "first_occurrence": first_occurrence,
            "last_occurrence": last_occurrence,
        }

        # Linha em wh_serasa_pj_restricao_summary (1 por categoria, sempre
        # quando ha summary mesmo que count=0 — agregado historico vale).
        if summary:
            restricao_summary_rows.append(
                {
                    "tenant_id": tenant_id,
                    "consulta_id": consulta_id,
                    "tipo": tipo_canonico,
                    "count": int(summary.get("count") or 0),
                    "balance": to_decimal_or_none(summary.get("balance")),
                    "first_occurrence": first_occurrence,
                    "last_occurrence": last_occurrence,
                    **build_provenance(
                        source_id=(
                            f"{raw_str}|summary|{tipo_canonico}"
                        ),
                        item=summary,
                        ingested_at=ingested_at,
                    ),
                }
            )

        # Items individuais (linhas em wh_serasa_pj_restricao).
        for item in items:
            if not isinstance(item, dict):
                continue
            row = _map_restricao_item(
                item=item,
                tipo=tipo_canonico,
                category_key=category_key,
                tenant_id=tenant_id,
                consulta_id=consulta_id,
                raw_str=raw_str,
                ingested_at=ingested_at,
            )
            if row is not None:
                restricoes_rows.append(row)

    # ─── Header: cadastrais + contadores ───────────────────────────────────
    counters = _aggregate_counters(counters_per_tipo)

    # ─── Sumario de facts.bankrupts e facts.judgementFilings ───────────────
    facts_block = report.get("facts") or {}
    bankrupts_summary = (facts_block.get("bankrupts") or {}).get("summary") or {}
    judgement_summary = (
        (facts_block.get("judgementFilings") or {}).get("summary") or {}
    )

    bankrupts_count = int(bankrupts_summary.get("count") or 0)
    bankrupts_balance = to_decimal_or_none(bankrupts_summary.get("balance"))
    judgement_count = int(judgement_summary.get("count") or 0)
    judgement_balance = to_decimal_or_none(judgement_summary.get("balance"))

    # ─── Telefone (separado em area_code + number) ─────────────────────────
    phone_block = identification.get("phone") or {}

    consulta_row: dict[str, Any] = {
        "id": consulta_id,
        "tenant_id": tenant_id,
        "raw_id": raw_id,
        "cnpj": cnpj,
        "consulted_at": consulted_at,
        "requested_report": requested_report,
        "actual_report_returned": actual_report_returned,
        "reciprocity_downgrade": (
            requested_report != actual_report_returned
        ),
        # Cadastrais (de identificationReport)
        "razao_social": normalize_str_or_none(
            identification.get("companyName")
        ),
        # Nome fantasia nao vem no payload do segmento 028.
        "nome_fantasia": None,
        "situacao_cadastral": normalize_str_or_none(
            identification.get("statusCodeDescription")
        ),
        "data_constituicao": parse_date_or_none(
            identification.get("companyFoundation")
        ),
        # Capital social e faturamento presumido nao vem nesse segmento.
        "capital_social": None,
        "faturamento_presumido": None,
        "atividade_principal_cnae": normalize_str_or_none(
            identification.get("cnae")
        ),
        "atividade_principal_descricao": normalize_str_or_none(
            identification.get("economicActivity")
        ),
        # Cadastrais expandidos (F.1)
        "legal_nature_code": normalize_str_or_none(
            identification.get("legalNatureCode")
        ),
        "partnership_description": normalize_str_or_none(
            identification.get("partnership")
        ),
        "number_employees": _to_int_or_none(
            identification.get("numberEmployees")
        ),
        "export_sales": to_decimal_or_none(
            identification.get("exportSales")
        ),
        "import_purchases": to_decimal_or_none(
            identification.get("importPurchases")
        ),
        "nire_number": normalize_str_or_none(
            identification.get("nireNumber")
        ),
        "state_registration": normalize_str_or_none(
            identification.get("stateRegistration")
        ),
        "company_register": normalize_str_or_none(
            identification.get("companyRegister")
        ),
        "company_register_date": parse_date_or_none(
            identification.get("companyRegisterDate")
        ),
        "serasa_active_code": normalize_str_or_none(
            identification.get("serasaActiveCode")
        ),
        # Status detalhado
        "status_code": normalize_str_or_none(
            identification.get("statusCode")
        ),
        "status_registration_text": normalize_str_or_none(
            identification.get("statusRegistration")
        ),
        "company_url": normalize_str_or_none(
            identification.get("companyUrl")
        ),
        # Telefone
        "phone_area_code": normalize_str_or_none(
            phone_block.get("areaCode")
        ),
        "phone_number": normalize_str_or_none(
            phone_block.get("phoneNumber")
        ),
        # Regime tributario + filiais (F.3.1)
        "tax_option": normalize_str_or_none(
            identification.get("taxOption")
        ),
        "branch_offices": normalize_str_or_none(
            identification.get("branchOffices")
        ),
        # Score nao vem no segmento 028 (factoring/FIDC). Deixa nulo —
        # se um dia o contrato adicionar produto de score, mapper
        # pega de `report["scoring"]` (ou onde estiver).
        "score_h4pj": to_decimal_or_none(
            get_block(report.get("scoring") or {}, "score", "value")
        ),
        "score_classe": normalize_str_or_none(
            get_block(report.get("scoring") or {}, "class", "classe")
        ),
        "score_descricao": normalize_str_or_none(
            get_block(report.get("scoring") or {}, "description")
        ),
        # Contadores agregados (negativeData)
        **counters,
        # Supressao judicial (regra serasa_liminar_v1)
        "negative_summary_message": negative_summary_message,
        "suspeita_liminar": suspeita_liminar,
        # Sumario de facts.bankrupts (F.1)
        "has_falencias": bankrupts_count > 0,
        "count_falencias": bankrupts_count,
        "valor_falencias": bankrupts_balance,
        # Sumario de facts.judgementFilings (F.1)
        "has_acoes_judiciais": judgement_count > 0,
        "count_acoes_judiciais": judgement_count,
        "valor_acoes_judiciais": judgement_balance,
        # Proveniencia
        **build_provenance(
            source_id=raw_str,
            item=payload,
            ingested_at=ingested_at,
            source_updated_at=_date_to_utc_datetime(
                parse_date_or_none(identification.get("updateDate"))
            ),
        ),
    }

    # ─── Enderecos (silver) ────────────────────────────────────────────────
    # Serasa retorna 1 endereco em `identificationReport.address` (dict,
    # nao array). Tratamos como lista de 1.
    enderecos_rows = _map_enderecos(
        address=identification.get("address"),
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )

    # ─── Socios e Participacoes (vazios neste contrato) ────────────────────
    # Mapper le caminhos genericos pra estar pronto quando o contrato
    # adicionar esses produtos. Hoje o segmento 028 nao retorna nada.
    socios_rows = _map_socios(
        items=as_list(
            get_block(report, "partners", "Partners", "relationships")
        ),
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )
    participacoes_rows = _map_participacoes(
        items=as_list(
            get_block(
                report,
                "businessParticipation",
                "BusinessParticipation",
                "participations",
            )
        ),
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )

    # ─── Pagamento buckets (advancedCommercialPaymentHistory) ──────────────
    pagamento_rows = _map_pagamento_buckets(
        block=report.get("advancedCommercialPaymentHistory") or {},
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )

    # ─── Inquiries anteriores (facts.inquiryCompanyResponse.results) ───────
    inquiry_block = (
        (report.get("facts") or {}).get("inquiryCompanyResponse") or {}
    )
    inquiries_rows = _map_inquiries_anteriores(
        block=inquiry_block,
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )

    # ─── Inquiries mensais (facts.inquiryCompanyResponse.quantity.historical)
    inquiries_mensais_rows = _map_inquiries_mensais(
        block=inquiry_block,
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )

    # ─── Predecessores (identificationReport.predecessorList) ──────────────
    predecessores_rows = _map_predecessores(
        items=as_list(identification.get("predecessorList")),
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )

    # ─── F.3.2: Bloco advancedCommercialPaymentHistory expandido ───────────
    acph = report.get("advancedCommercialPaymentHistory") or {}
    business_refs_rows = _map_business_references(
        block=acph,
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )
    evolucao_mensal_rows = _map_pagamento_evolucao_mensal(
        block=acph,
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )
    atraso_medio_rows = _map_atraso_medio_mensal(
        block=acph,
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )
    payment_comparative_rows = _map_payment_comparative(
        block=acph,
        tenant_id=tenant_id,
        consulta_id=consulta_id,
        raw_str=raw_str,
        ingested_at=ingested_at,
    )

    return SerasaPjMappedRows(
        consulta=consulta_row,
        socios=socios_rows,
        restricoes=restricoes_rows,
        restricao_summaries=restricao_summary_rows,
        participacoes=participacoes_rows,
        enderecos=enderecos_rows,
        pagamento_buckets=pagamento_rows,
        inquiries_anteriores=inquiries_rows,
        predecessores=predecessores_rows,
        inquiries_mensais=inquiries_mensais_rows,
        business_references=business_refs_rows,
        pagamento_evolucao_mensal=evolucao_mensal_rows,
        atraso_medio_mensal=atraso_medio_rows,
        payment_comparatives=payment_comparative_rows,
    )


# ─── Helpers de extracao ───────────────────────────────────────────────────


def _extract_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve o envelope `{"reports": [{...}]}` -> dict do report.

    Tolera payloads que ja venham flat (sem `reports`) em re-mapeamento
    futuro de raw com shape diferente.
    """
    reports = payload.get("reports")
    if isinstance(reports, list) and reports:
        first = reports[0]
        if isinstance(first, dict):
            return first
    # Fallback: payload ja flat ou shape inesperado — retorna o que tem.
    return payload if isinstance(payload, dict) else {}


def _aggregate_counters(
    per_tipo: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Calcula has_*/count_* + soma total.

    `per_tipo` e dict mapeando tipo canonico -> {count, balance, ...}.
    """
    pefin = per_tipo.get(_RESTRICAO_PEFIN, {})
    refin = per_tipo.get(_RESTRICAO_REFIN, {})
    protesto = per_tipo.get(_RESTRICAO_PROTESTO, {})
    cheque = per_tipo.get(_RESTRICAO_CHEQUE, {})

    # Soma os balance disponiveis (incluindo collection se houver).
    total = Decimal("0")
    has_any_balance = False
    for v in per_tipo.values():
        bal = v.get("balance")
        if bal is not None:
            total += bal
            has_any_balance = True

    return {
        "has_refin": int(refin.get("count") or 0) > 0,
        "has_pefin": int(pefin.get("count") or 0) > 0,
        "has_protesto": int(protesto.get("count") or 0) > 0,
        "has_cheque": int(cheque.get("count") or 0) > 0,
        "count_refin": int(refin.get("count") or 0),
        "count_pefin": int(pefin.get("count") or 0),
        "count_protesto": int(protesto.get("count") or 0),
        "count_cheque": int(cheque.get("count") or 0),
        "valor_total_restricoes": total if has_any_balance else None,
    }


def _map_restricao_item(
    *,
    item: dict[str, Any],
    tipo: str,
    category_key: str,
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> dict[str, Any] | None:
    """Mapeia 1 item de pefinResponse/notaryResponse/etc -> linha canonica.

    Source ID usa `cadus` (ID unico Serasa) quando disponivel — mais robusto
    que index. Se nao tiver cadus, gera `<raw>|<tipo>|<contractId>` ou
    fallback `<raw>|<tipo>|<index_no_dump>` (caller deve cuidar do index).
    """
    cadus = normalize_str_or_none(item.get("cadus"))
    contract_id = normalize_str_or_none(item.get("contractId"))
    natural_id = cadus or contract_id
    if not natural_id:
        # Sem chave natural, descarta (nao tem como deduplicar em remap).
        return None

    return {
        "tenant_id": tenant_id,
        "consulta_id": consulta_id,
        "tipo": tipo,
        "valor": to_decimal_or_none(item.get("amount")),
        # Notary nao tem creditor; pefin/refin/check sim.
        "credor": normalize_str_or_none(item.get("creditorName")),
        "data_ocorrencia": parse_date_or_none(
            item.get("occurrenceDate")
        ),
        # Serasa nao retorna data de baixa neste payload (so quando ha
        # baixa registrada). Deixa None.
        "data_baixa": parse_date_or_none(item.get("settlementDate")),
        # Detalhe livre — preserva todos os campos especificos do tipo.
        # `category_key` e o nome original do bloco no payload, util pra
        # remap se a Serasa renomear.
        "detalhe": {**item, "_payload_block": category_key},
        **build_provenance(
            source_id=f"{raw_str}|{tipo}|{natural_id}",
            item=item,
            ingested_at=ingested_at,
        ),
    }


def _map_socios(
    *,
    items: list[Any],
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        documento = strip_non_digits(
            get_block(
                item,
                "documentId",
                "DocumentId",
                "document",
                "documento",
                "cpf",
                "cnpj",
            )
        )
        if not documento:
            continue
        rows.append(
            {
                "tenant_id": tenant_id,
                "consulta_id": consulta_id,
                "documento": documento,
                "documento_tipo": _classify_documento(documento),
                "nome": normalize_str_or_none(
                    get_block(item, "name", "Name", "nome")
                ),
                "qualificacao": normalize_str_or_none(
                    get_block(
                        item,
                        "role",
                        "qualification",
                        "qualificacao",
                        "type",
                    )
                ),
                "percentual": to_decimal_or_none(
                    get_block(
                        item,
                        "participationPercentage",
                        "percentage",
                        "percentual",
                    )
                ),
                "data_entrada": parse_date_or_none(
                    get_block(
                        item,
                        "entryDate",
                        "dataEntrada",
                        "joinDate",
                    )
                ),
                **build_provenance(
                    source_id=f"{raw_str}|socio|{documento}",
                    item=item,
                    ingested_at=ingested_at,
                ),
            }
        )
    return rows


def _map_participacoes(
    *,
    items: list[Any],
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        documento_empresa = strip_non_digits(
            get_block(
                item,
                "documentId",
                "DocumentId",
                "cnpj",
                "documento",
            )
        )
        if len(documento_empresa) != 14:
            continue
        rows.append(
            {
                "tenant_id": tenant_id,
                "consulta_id": consulta_id,
                "documento_empresa": documento_empresa,
                "razao_social": normalize_str_or_none(
                    get_block(
                        item,
                        "businessName",
                        "BusinessName",
                        "razaoSocial",
                        "name",
                    )
                ),
                "percentual": to_decimal_or_none(
                    get_block(
                        item,
                        "participationPercentage",
                        "percentage",
                        "percentual",
                    )
                ),
                "qualificacao": normalize_str_or_none(
                    get_block(item, "role", "qualification", "qualificacao")
                ),
                **build_provenance(
                    source_id=(
                        f"{raw_str}|participacao|{documento_empresa}"
                    ),
                    item=item,
                    ingested_at=ingested_at,
                ),
            }
        )
    return rows


def _map_enderecos(
    *,
    address: Any,
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    """Serasa retorna 1 endereco em `identificationReport.address` (dict).

    Caso futuro de produto que retorne array de enderecos, este helper
    aceita lista tambem.
    """
    if not address:
        return []

    items = address if isinstance(address, list) else [address]
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "tenant_id": tenant_id,
                "consulta_id": consulta_id,
                "tipo": normalize_str_or_none(
                    get_block(item, "type", "Type", "tipo")
                ),
                "logradouro": normalize_str_or_none(
                    get_block(
                        item,
                        "addressLine",
                        "street",
                        "logradouro",
                        "address",
                    )
                ),
                # Numero costuma vir embutido no addressLine no PJ analitico
                # do segmento 028. Mantemos o campo separado disponivel
                # caso outro produto retorne.
                "numero": normalize_str_or_none(
                    get_block(item, "number", "numero")
                ),
                "complemento": normalize_str_or_none(
                    get_block(item, "complement", "complemento")
                ),
                "bairro": normalize_str_or_none(
                    get_block(
                        item, "district", "neighborhood", "bairro"
                    )
                ),
                "cidade": normalize_str_or_none(
                    get_block(item, "city", "cidade")
                ),
                "uf": _normalize_uf(
                    get_block(item, "state", "federalUnit", "uf")
                ),
                "cep": _normalize_cep(
                    get_block(item, "zipCode", "postalCode", "cep")
                ),
                **build_provenance(
                    source_id=f"{raw_str}|endereco|{idx}",
                    item=item,
                    ingested_at=ingested_at,
                ),
            }
        )
    return rows


# ─── Normalizacao auxiliar ────────────────────────────────────────────────


def _classify_documento(documento: str) -> str:
    if len(documento) == 11:
        return "cpf"
    if len(documento) == 14:
        return "cnpj"
    return "unknown"


def _normalize_uf(value: Any) -> str | None:
    s = normalize_str_or_none(value)
    if s is None:
        return None
    s = s.strip().upper()
    return s if len(s) == 2 else None


def _normalize_cep(value: Any) -> str | None:
    digits = strip_non_digits(value)
    return digits if len(digits) == 8 else None


def _date_to_utc_datetime(d: Any) -> datetime | None:
    """Converte date -> datetime UTC meia-noite. None preserva None."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d
    return datetime.combine(d, datetime.min.time(), UTC)


# ─── Pagamento buckets ────────────────────────────────────────────────────


# segmentData carrega buckets aninhados por tipo de segmento. Cada um
# pode estar populado ou vazio (`{}`) — so processa quando tem chave.
_SEGMENT_KINDS = ("drawee", "assignor", "individual")


def _map_pagamento_buckets(
    *,
    block: dict[str, Any],
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    """Extrai buckets de pontualidade do `advancedCommercialPaymentHistory`.

    Estrutura observada:
        {
            "segmentData": {
                "drawee":     {<buckets ou vazio>},
                "assignor":   {<buckets ou vazio>},
                "individual": {<buckets ou vazio>},
                "segmentDescription": "FACTORINGS"
            },
            "paymentHistory": {
                "titlesQuantity": [<bucket>, ...]
            }
        }

    Quando algum dos sub-segmentos vier populado, le buckets dele.
    Quando segmentData/segmentos estao vazios, le do `paymentHistory`
    direto e marca `segment_kind` como "default" (caso visto em
    factoring/segmento 028).
    """
    if not isinstance(block, dict) or not block:
        return []

    rows: list[dict[str, Any]] = []
    segment_data = block.get("segmentData") or {}

    # Tenta segmentos especificos primeiro.
    found_in_segments = False
    for kind in _SEGMENT_KINDS:
        sub = segment_data.get(kind)
        if isinstance(sub, dict) and sub:
            buckets = as_list(
                (sub.get("titlesQuantity") or sub.get("buckets")) or []
            )
            for idx, bucket in enumerate(buckets):
                row = _bucket_row(
                    bucket=bucket,
                    segment_kind=kind,
                    tenant_id=tenant_id,
                    consulta_id=consulta_id,
                    raw_str=raw_str,
                    ingested_at=ingested_at,
                    idx=idx,
                )
                if row is not None:
                    rows.append(row)
                    found_in_segments = True

    # Se nenhum segmento especifico trouxe buckets, le do payment_history
    # default (caso comum em factoring 028).
    if not found_in_segments:
        payment_history = block.get("paymentHistory") or {}
        buckets = as_list(payment_history.get("titlesQuantity"))
        for idx, bucket in enumerate(buckets):
            row = _bucket_row(
                bucket=bucket,
                segment_kind="default",
                tenant_id=tenant_id,
                consulta_id=consulta_id,
                raw_str=raw_str,
                ingested_at=ingested_at,
                idx=idx,
            )
            if row is not None:
                rows.append(row)

    return rows


def _bucket_row(
    *,
    bucket: Any,
    segment_kind: str,
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
    idx: int,
) -> dict[str, Any] | None:
    if not isinstance(bucket, dict):
        return None
    name = normalize_str_or_none(bucket.get("name"))
    if not name:
        return None

    range_code = normalize_str_or_none(bucket.get("rangeCode"))
    natural_id = range_code or name
    return {
        "tenant_id": tenant_id,
        "consulta_id": consulta_id,
        "segment_kind": segment_kind,
        "name": name,
        "range_label": normalize_str_or_none(bucket.get("range")),
        "range_code": range_code,
        "range_value_from": to_decimal_or_none(
            bucket.get("rangeValueFrom")
        ),
        "range_value_to": to_decimal_or_none(bucket.get("rangeValueTo")),
        "percentage_from": to_decimal_or_none(
            bucket.get("percentageFrom")
        ),
        "percentage_to": to_decimal_or_none(bucket.get("percentageTo")),
        "percentage_label": normalize_str_or_none(bucket.get("percentage")),
        **build_provenance(
            source_id=(
                f"{raw_str}|payment|{segment_kind}|{natural_id}|{idx}"
            ),
            item=bucket,
            ingested_at=ingested_at,
        ),
    }


# ─── Inquiries anteriores ─────────────────────────────────────────────────


def _map_inquiries_anteriores(
    *,
    block: dict[str, Any],
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    """Extrai `results[]` de `facts.inquiryCompanyResponse`."""
    if not isinstance(block, dict):
        return []
    items = as_list(block.get("results"))
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        company_doc = strip_non_digits(item.get("companyDocumentId"))
        # Source ID: <raw>|inquiry|<doc>|<date>|<idx> — mesmo CNPJ pode
        # consultar varias vezes em datas diferentes.
        date_part = (
            normalize_str_or_none(item.get("occurrenceDate")) or "no-date"
        )
        natural_id = (
            f"{company_doc or 'no-doc'}|{date_part}|{idx}"
        )
        rows.append(
            {
                "tenant_id": tenant_id,
                "consulta_id": consulta_id,
                "company_document_id": company_doc or None,
                "company_name": normalize_str_or_none(
                    item.get("companyName")
                ),
                "company_alias": normalize_str_or_none(
                    item.get("companyAlias")
                ),
                "occurrence_date": parse_date_or_none(
                    item.get("occurrenceDate")
                ),
                "days_quantity": _to_int_or_none(
                    item.get("daysQuantity")
                ),
                "detalhe": item,
                **build_provenance(
                    source_id=f"{raw_str}|inquiry|{natural_id}",
                    item=item,
                    ingested_at=ingested_at,
                ),
            }
        )
    return rows


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ─── Predecessores (sucessoes empresariais) ───────────────────────────────


def _map_predecessores(
    *,
    items: list[Any],
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    """Extrai `identificationReport.predecessorList[]`.

    Cada predecessor representa uma empresa anterior (razao social + CNPJ
    historicos) que foi sucedida pela target em data registrada. Sinal
    forte pra credito: empresa que mudou de razao social recente pode
    estar tentando "lavar" historico negativo.
    """
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        nome = normalize_str_or_none(item.get("predecessorName"))
        if not nome:
            # Sem nome nao da pra deduplicar; descarta.
            continue
        data = parse_date_or_none(item.get("predecessorDate"))
        # Source ID: usa nome+data; se data for None, usa idx.
        date_part = data.isoformat() if data else f"idx{idx}"
        rows.append(
            {
                "tenant_id": tenant_id,
                "consulta_id": consulta_id,
                "predecessor_name": nome,
                "predecessor_date": data,
                **build_provenance(
                    source_id=(
                        f"{raw_str}|predecessor|{nome}|{date_part}"
                    ),
                    item=item,
                    ingested_at=ingested_at,
                ),
            }
        )
    return rows


# ─── Inquiries mensais ────────────────────────────────────────────────────


# ─── F.3.2 helpers — advancedCommercialPaymentHistory expandido ───────────


def _iter_segment_kinds_for_block(
    acph: dict[str, Any], inner_key: str
) -> list[tuple[str, dict[str, Any]]]:
    """Coleta paths (segment_kind, sub-block) onde `inner_key` existe.

    Procura em segmentData.{drawee, assignor, individual} e tambem na
    raiz. Retorna lista de tuplas (kind, block) para iterar uniformemente.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    if not isinstance(acph, dict):
        return found

    # Raiz.
    raiz_block = acph.get(inner_key)
    if isinstance(raiz_block, dict) and raiz_block:
        found.append(("default", raiz_block))

    # Sub-segmentos.
    seg_data = acph.get("segmentData") or {}
    for kind in ("drawee", "assignor", "individual"):
        sub = seg_data.get(kind) or {}
        sub_block = sub.get(inner_key)
        if isinstance(sub_block, dict) and sub_block:
            found.append((kind, sub_block))

    return found


def _map_business_references(
    *,
    block: dict[str, Any],
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    """Extrai businessReferencesList[] da raiz e segmentos."""
    rows: list[dict[str, Any]] = []
    for segment_kind, br_block in _iter_segment_kinds_for_block(
        block, "businessReferences"
    ):
        items = as_list(br_block.get("businessReferencesList"))
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            description = normalize_str_or_none(
                item.get("businessDescription")
            )
            year = normalize_str_or_none(item.get("yearPotentialDate"))
            month = normalize_str_or_none(item.get("monthPotentialDate"))
            # Source ID estavel: <raw>|business_ref|<segment>|<desc>|<ym>|<idx>
            ym = f"{year or '----'}-{month or '--'}"
            natural = f"{description or 'no-desc'}|{ym}|{idx}"
            rows.append(
                {
                    "tenant_id": tenant_id,
                    "consulta_id": consulta_id,
                    "segment_kind": segment_kind,
                    "business_description": description,
                    "reference_year": year,
                    "reference_month": month,
                    "potential_value_range_code": normalize_str_or_none(
                        item.get("potentialValueRangeCode")
                    ),
                    "potential_value_range_description": normalize_str_or_none(
                        item.get("potentialValueRangeDescription")
                    ),
                    "potential_value_from": to_decimal_or_none(
                        item.get("potentialValueFrom")
                    ),
                    "potential_value_to": to_decimal_or_none(
                        item.get("potentialValueTo")
                    ),
                    "potential_midrange_code": normalize_str_or_none(
                        item.get("potentialMidrangeCode")
                    ),
                    "potential_midrange_description": normalize_str_or_none(
                        item.get("potentialMidrangeDescription")
                    ),
                    "potential_midrange_value_from": to_decimal_or_none(
                        item.get("potentialMidrangeValueFrom")
                    ),
                    "potential_midrange_value_to": to_decimal_or_none(
                        item.get("potentialMidrangeValueTo")
                    ),
                    **build_provenance(
                        source_id=(
                            f"{raw_str}|business_ref|{segment_kind}|{natural}"
                        ),
                        item=item,
                        ingested_at=ingested_at,
                    ),
                }
            )
    return rows


def _map_pagamento_evolucao_mensal(
    *,
    block: dict[str, Any],
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    """Extrai evolutionCommitmentsSuppliersList[] da raiz e segmentos."""
    rows: list[dict[str, Any]] = []
    for segment_kind, ev_block in _iter_segment_kinds_for_block(
        block, "evolutionCommitmentsSuppliers"
    ):
        items = as_list(ev_block.get("evolutionCommitmentsSuppliersList"))
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            year = normalize_str_or_none(item.get("yearCommitment"))
            month = normalize_str_or_none(item.get("monthCommitment"))
            ym = f"{year or '--'}-{month or '--'}"
            rows.append(
                {
                    "tenant_id": tenant_id,
                    "consulta_id": consulta_id,
                    "segment_kind": segment_kind,
                    "year_commitment": year,
                    "month_commitment": month,
                    "month_description": normalize_str_or_none(
                        item.get("descriptionMonthCommitment")
                    ),
                    "segment_information": normalize_str_or_none(
                        item.get("segmentInformation")
                    ),
                    "total_month_range_code": normalize_str_or_none(
                        item.get("totalMonthRangeCode")
                    ),
                    "total_month_range_description": normalize_str_or_none(
                        item.get("totalMonthRangeDescription")
                    ),
                    "total_monthly_range_value_from": to_decimal_or_none(
                        item.get("totalMonthlyRangeValueFrom")
                    ),
                    "total_monthly_range_value_to": to_decimal_or_none(
                        item.get("totalMonthlyRangeValueTo")
                    ),
                    "value_commitments_due_from": to_decimal_or_none(
                        item.get("valueCommitmentsDueFrom")
                    ),
                    "value_commitments_due_to": to_decimal_or_none(
                        item.get("valueCommitmentsDueTo")
                    ),
                    "track_code_to_expire": normalize_str_or_none(
                        item.get("trackCodeToExpire")
                    ),
                    "track_description_to_expire": normalize_str_or_none(
                        item.get("trackDescriptionToExpire")
                    ),
                    "value_overdue_commitments_from": to_decimal_or_none(
                        item.get("valueOverdueCommitmentsFrom")
                    ),
                    "value_overdue_commitments_to": to_decimal_or_none(
                        item.get("valueOverdueCommitmentsTo")
                    ),
                    "expired_track_code": normalize_str_or_none(
                        item.get("expiredTrackCode")
                    ),
                    "expired_track_description": normalize_str_or_none(
                        item.get("expiredTrackDescription")
                    ),
                    **build_provenance(
                        source_id=(
                            f"{raw_str}|evolucao|{segment_kind}|{ym}|{idx}"
                        ),
                        item=item,
                        ingested_at=ingested_at,
                    ),
                }
            )
    return rows


def _map_atraso_medio_mensal(
    *,
    block: dict[str, Any],
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    """Extrai averageDelayPeriod.periodList[] dos segmentos drawee/assignor.

    Estrutura: segmentData.{kind}.paymentHistory.averageDelayPeriod.
    periodList[] (cada item = {period: "ABR/25", averageDelayDaysFrom,
    averageDelayDaysTo}).
    """
    rows: list[dict[str, Any]] = []
    if not isinstance(block, dict):
        return rows
    seg_data = block.get("segmentData") or {}
    for kind in ("drawee", "assignor", "individual"):
        sub = seg_data.get(kind) or {}
        adp = (sub.get("paymentHistory") or {}).get("averageDelayPeriod") or {}
        items = as_list(adp.get("periodList"))
        for item in items:
            if not isinstance(item, dict):
                continue
            month_label = normalize_str_or_none(item.get("period"))
            if not month_label:
                continue
            rows.append(
                {
                    "tenant_id": tenant_id,
                    "consulta_id": consulta_id,
                    "segment_kind": kind,
                    "month_label": month_label,
                    "average_delay_days_from": _to_int_or_none(
                        item.get("averageDelayDaysFrom")
                    ),
                    "average_delay_days_to": _to_int_or_none(
                        item.get("averageDelayDaysTo")
                    ),
                    **build_provenance(
                        source_id=(
                            f"{raw_str}|atraso_medio|{kind}|{month_label}"
                        ),
                        item=item,
                        ingested_at=ingested_at,
                    ),
                }
            )
    return rows


def _map_payment_comparative(
    *,
    block: dict[str, Any],
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    """Extrai paymentHistoryComparativeAnalysisList[] (so vem em drawee).

    Cada item tem month + 2 sub-blocks (market e segment) com codigo+
    descricao de pagamento spot e parcelado. Achata para colunas planas.
    """
    rows: list[dict[str, Any]] = []
    if not isinstance(block, dict):
        return rows
    seg_data = block.get("segmentData") or {}
    for kind in ("drawee", "assignor", "individual"):
        sub = seg_data.get(kind) or {}
        pha = sub.get("paymentHistoryComparativeAnalysis") or {}
        items = as_list(pha.get("paymentHistoryComparativeAnalysisList"))
        for item in items:
            if not isinstance(item, dict):
                continue
            month_label = normalize_str_or_none(item.get("month"))
            if not month_label:
                continue
            market = item.get("market") or {}
            segment = item.get("segment") or {}
            rows.append(
                {
                    "tenant_id": tenant_id,
                    "consulta_id": consulta_id,
                    "segment_kind": kind,
                    "month_label": month_label,
                    "market_origin_code": normalize_str_or_none(
                        market.get("originCode")
                    ),
                    "market_spot_payment_code": normalize_str_or_none(
                        market.get("spotPaymentCode")
                    ),
                    "market_spot_payment_description": normalize_str_or_none(
                        market.get("spotPaymentCodeDescription")
                    ),
                    "market_installment_payment_code": normalize_str_or_none(
                        market.get("installmentPaymentCode")
                    ),
                    "market_installment_payment_description": (
                        normalize_str_or_none(
                            market.get("installmentPaymentCodeDescription")
                        )
                    ),
                    "segment_origin_code": normalize_str_or_none(
                        segment.get("originCode")
                    ),
                    "segment_spot_payment_code": normalize_str_or_none(
                        segment.get("spotPaymentCode")
                    ),
                    "segment_spot_payment_description": normalize_str_or_none(
                        segment.get("spotPaymentCodeDescription")
                    ),
                    "segment_installment_payment_code": normalize_str_or_none(
                        segment.get("installmentPaymentCode")
                    ),
                    "segment_installment_payment_description": (
                        normalize_str_or_none(
                            segment.get("installmentPaymentCodeDescription")
                        )
                    ),
                    **build_provenance(
                        source_id=(
                            f"{raw_str}|payment_comp|{kind}|{month_label}"
                        ),
                        item=item,
                        ingested_at=ingested_at,
                    ),
                }
            )
    return rows


def _map_inquiries_mensais(
    *,
    block: dict[str, Any],
    tenant_id: UUID,
    consulta_id: UUID,
    raw_str: str,
    ingested_at: datetime,
) -> list[dict[str, Any]]:
    """Extrai `quantity.historical[]` (agregado mensal de consultas).

    Estrutura observada:
        quantity.historical[] = [
            {"inquiryDate": "2026-04", "occurrences": 1},
            {"inquiryDate": "2026-03", "occurrences": 0},
            ...
        ]

    Tipicamente 13 entradas (mes corrente + 12 anteriores). Source ID
    usa o `inquiry_year_month` como chave natural — re-mapeamento da
    mesma consulta substitui linhas antigas via UPSERT.
    """
    if not isinstance(block, dict):
        return []
    historical = as_list((block.get("quantity") or {}).get("historical"))
    rows: list[dict[str, Any]] = []
    for item in historical:
        if not isinstance(item, dict):
            continue
        ym = normalize_str_or_none(item.get("inquiryDate"))
        if not ym:
            continue
        rows.append(
            {
                "tenant_id": tenant_id,
                "consulta_id": consulta_id,
                "inquiry_year_month": ym,
                "occurrences": _to_int_or_none(item.get("occurrences"))
                or 0,
                **build_provenance(
                    source_id=f"{raw_str}|inquiry_mensal|{ym}",
                    item=item,
                    ingested_at=ingested_at,
                ),
            }
        )
    return rows
