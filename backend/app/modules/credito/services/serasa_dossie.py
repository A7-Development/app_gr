"""Visão PARA O AGENTE da consulta Serasa PJ (silver-first, ABRANGENTE).

Builder da read-tool `get_serasa_pj`. Serasa e dataset CARO — esta view extrai
o MAXIMO do silver ja materializado (`wh_serasa_pj_consulta` + ~13 filhas):
score, cadastrais expandidos, restricoes (detalhe + resumo), falencias/acoes,
suspeita de liminar, comportamento de pagamento (atraso medio, evolucao de
compromissos, comparativo de mercado, buckets), demanda por credito
(inquiries), socios, participacoes, predecessores e faturamento potencial.

Resolve dossier->cnpj (TARGET, igual cadastral/societario) e le a ULTIMA
consulta do CNPJ. Provider-blind (§13.2.1). Frescor: `consultado_em`
(quando consultamos) + `atualizado_na_fonte` (updateDate do Serasa).

Hoje hand-shaped; migrar para projecao dirigida por contrato e follow-up.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CompanyRole
from app.modules.credito.models.company import CreditDossierCompany


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime | date):
        return v.isoformat()
    return v


# Cada filha: (chave_na_view, tabela, [colunas de negocio], order_by SQL).
_CHILDREN: list[tuple[str, str, list[str], str]] = [
    ("socios", "wh_serasa_pj_socio",
     ["documento", "documento_tipo", "nome", "qualificacao", "percentual",
      "data_entrada"], "percentual DESC NULLS LAST"),
    ("restricoes_detalhe", "wh_serasa_pj_restricao",
     ["tipo", "valor", "credor", "data_ocorrencia", "data_baixa", "detalhe"],
     "valor DESC NULLS LAST"),
    ("restricoes_por_tipo", "wh_serasa_pj_restricao_summary",
     ["tipo", "count", "balance", "first_occurrence", "last_occurrence"],
     "balance DESC NULLS LAST"),
    ("participacoes", "wh_serasa_pj_participacao",
     ["documento_empresa", "razao_social", "percentual", "qualificacao"],
     "percentual DESC NULLS LAST"),
    ("predecessores", "wh_serasa_pj_predecessor",
     ["predecessor_name", "predecessor_date"], "predecessor_date DESC NULLS LAST"),
    ("pagamento_atraso_medio_mensal", "wh_serasa_pj_atraso_medio_mensal",
     ["segment_kind", "month_label", "average_delay_days_from",
      "average_delay_days_to"], "month_label"),
    ("pagamento_evolucao_mensal", "wh_serasa_pj_pagamento_evolucao_mensal",
     ["segment_kind", "year_commitment", "month_commitment", "month_description",
      "total_month_range_description", "value_commitments_due_from",
      "value_commitments_due_to", "value_overdue_commitments_from",
      "value_overdue_commitments_to", "expired_track_description"],
     "year_commitment, month_commitment"),
    ("pagamento_comparativo_mercado", "wh_serasa_pj_payment_comparative",
     ["segment_kind", "month_label", "market_spot_payment_description",
      "market_installment_payment_description", "segment_spot_payment_description",
      "segment_installment_payment_description"], "month_label"),
    ("pagamento_buckets", "wh_serasa_pj_pagamento_bucket",
     ["segment_kind", "name", "range_label", "percentage_label",
      "range_value_from", "range_value_to"], "name"),
    ("demanda_inquiries_mensal", "wh_serasa_pj_inquiry_mensal",
     ["inquiry_year_month", "occurrences"], "inquiry_year_month DESC"),
    ("demanda_inquiries_anteriores", "wh_serasa_pj_inquiry_anterior",
     ["company_name", "company_alias", "occurrence_date", "days_quantity"],
     "occurrence_date DESC NULLS LAST"),
    ("faturamento_potencial", "wh_serasa_pj_business_reference",
     ["business_description", "reference_year", "reference_month",
      "potential_value_range_description", "potential_value_from",
      "potential_value_to"], "reference_year DESC NULLS LAST"),
    ("enderecos", "wh_serasa_pj_endereco",
     ["tipo", "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
      "cep"], "tipo"),
]


async def _target_cnpj(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> str | None:
    from sqlalchemy import select

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
    return digits if len(digits) == 14 else None


async def _rows(
    db: AsyncSession, *, table: str, cols: list[str], consulta_id: UUID,
    tenant_id: UUID, order_by: str,
) -> list[dict]:
    sql = text(
        f"SELECT {', '.join(cols)} FROM {table} "
        "WHERE tenant_id = :t AND consulta_id = :c "
        f"ORDER BY {order_by}"
    )
    res = await db.execute(sql, {"t": tenant_id, "c": consulta_id})
    return [
        {k: _jsonable(v) for k, v in zip(cols, row, strict=True)}
        for row in res.fetchall()
    ]


async def build_serasa_pj_agent_view(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> dict | None:
    """Visão Serasa COMPLETA para o agente. None se não há empresa-alvo."""
    cnpj = await _target_cnpj(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if cnpj is None:
        return None

    header = (
        await db.execute(
            text(
                "SELECT * FROM wh_serasa_pj_consulta "
                "WHERE tenant_id = :t AND cnpj = :c "
                "ORDER BY consulted_at DESC LIMIT 1"
            ),
            {"t": tenant_id, "c": cnpj},
        )
    ).mappings().first()

    if header is None:
        return {
            "encontrado": False,
            "cnpj": cnpj,
            "mensagem": (
                "Sem consulta Serasa para esta empresa. Rode a consulta antes."
            ),
        }

    h = dict(header)
    consulta_id = h["id"]

    def g(k: str) -> Any:
        return _jsonable(h.get(k))

    view: dict[str, Any] = {
        "encontrado": True,
        "cnpj": cnpj,
        "consultado_em": g("consulted_at"),
        "atualizado_na_fonte": g("source_updated_at"),
        "relatorio": h.get("actual_report_returned"),
        "reciprocity_downgrade": h.get("reciprocity_downgrade"),
        "cadastrais": {
            "razao_social": h.get("razao_social"),
            "nome_fantasia": h.get("nome_fantasia"),
            "situacao_cadastral": h.get("situacao_cadastral"),
            "data_constituicao": g("data_constituicao"),
            "capital_social": g("capital_social"),
            "faturamento_presumido": g("faturamento_presumido"),
            "natureza_juridica": h.get("legal_nature_code"),
            "atividade_principal_cnae": h.get("atividade_principal_cnae"),
            "atividade_principal": h.get("atividade_principal_descricao"),
            "numero_funcionarios": h.get("number_employees"),
            "regime_tributario": h.get("tax_option"),
            "filiais": h.get("branch_offices"),
            "export_sales": g("export_sales"),
            "import_purchases": g("import_purchases"),
        },
        "score": {
            "h4pj": g("score_h4pj"),
            "classe": h.get("score_classe"),
            "descricao": h.get("score_descricao"),
        },
        "restricoes_resumo": {
            "tem_restricao": bool(
                h.get("has_refin") or h.get("has_pefin")
                or h.get("has_protesto") or h.get("has_cheque")
            ),
            "qtd_refin": h.get("count_refin"),
            "qtd_pefin": h.get("count_pefin"),
            "qtd_protesto": h.get("count_protesto"),
            "qtd_cheque": h.get("count_cheque"),
            "valor_total": g("valor_total_restricoes"),
        },
        "falencias": {
            "tem": h.get("has_falencias"),
            "qtd": h.get("count_falencias"),
            "valor": g("valor_falencias"),
        },
        "acoes_judiciais": {
            "tem": h.get("has_acoes_judiciais"),
            "qtd": h.get("count_acoes_judiciais"),
            "valor": g("valor_acoes_judiciais"),
        },
        # Conclusao DERIVADA Strata (regra serasa_liminar_v1): "NADA CONSTA"
        # explicito = padrao de supressao judicial. Zeros NAO = ficha limpa.
        "suspeita_liminar": bool(h.get("suspeita_liminar")),
        "negative_summary_message": h.get("negative_summary_message"),
        "nota": (
            "Serasa = bureau caro; esta view traz tudo que o silver guarda. "
            "Comportamento de pagamento e inquiries sao sinais fortes: muitos "
            "compromissos vencidos / pico de consultas recentes = distress. "
            "suspeita_liminar=true: trate os zeros de restricao como suspeitos."
        ),
    }

    for key, table, cols, order_by in _CHILDREN:
        view[key] = await _rows(
            db, table=table, cols=cols, consulta_id=consulta_id,
            tenant_id=tenant_id, order_by=order_by,
        )

    return view
