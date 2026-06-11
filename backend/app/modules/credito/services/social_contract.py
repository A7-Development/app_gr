"""Montagem do payload do contrato social homologado (+ estrutura + cruzamentos).

Fonte ÚNICA consumida tanto pela read-tool `get_contrato_social_estrutura`
(agente `social_contract_analyst`) quanto pelo endpoint
`GET /dossies/{id}/societario` (tela do checkpoint). O que o agente JULGA e o
que a tela MOSTRA ficam ancorados no mesmo fato determinístico (§14).

Lê o homologado direto do `ai_extraction.extracted_fields` do documento
`social_contract` (JSONB) e CRUZA com o cadastro oficial já materializado em
`credit_dossier_company` (TARGET, populado pelo enriquecimento BDC):
capital social, data de constituição, CNPJ e razão social — divergência aqui
é a família de cruzamento "consistência cross-fonte" (o coração da esteira).

LGPD (§19.9): CPF de sócio NUNCA sai inteiro deste payload — só os 4 últimos
dígitos (o payload sobe ao LLM e vai pra UI).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CompanyRole, DocumentType

_CAPITAL_TOLERANCE_PCT = 1.0  # divergência de capital acima disso = não confere


def _to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _digits(raw: Any) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def _norm_name(raw: Any) -> str:
    """Normaliza razão social p/ comparação (caixa, acentos, pontuação, sufixos)."""
    s = unicodedata.normalize("NFKD", str(raw or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    # Sufixos societários não diferenciam a empresa.
    s = re.sub(r"\b(LTDA|LIMITADA|S\s*A|SA|EIRELI|ME|EPP|SS|SLU)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_date(raw: Any) -> date | None:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(raw or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _redact_socio(item: Any) -> dict[str, Any] | None:
    """Sócio com CPF reduzido aos 4 últimos dígitos (LGPD §19.9)."""
    if not isinstance(item, dict):
        return None
    nome = item.get("nome")
    if not isinstance(nome, str) or not nome.strip():
        return None
    cpf_digits = _digits(item.get("cpf"))
    return {
        "nome": nome.strip(),
        "cpf_ultimos4": cpf_digits[-4:] if len(cpf_digits) >= 4 else None,
        "participacao_pct": _to_float(item.get("participacao_pct")),
    }


def _estrutura(socios: list[dict[str, Any]], data_constituicao: date | None) -> dict[str, Any]:
    """Estrutura societária determinística — números prontos pro agente julgar."""
    pcts = [s["participacao_pct"] for s in socios if s["participacao_pct"] is not None]
    soma = round(sum(pcts), 2) if pcts else None
    sem_pct = sum(1 for s in socios if s["participacao_pct"] is None)
    maior = max(
        (s for s in socios if s["participacao_pct"] is not None),
        key=lambda s: s["participacao_pct"],
        default=None,
    )
    idade_anos: float | None = None
    if data_constituicao is not None:
        idade_anos = round((date.today() - data_constituicao).days / 365.25, 1)
    return {
        "n_socios": len(socios),
        "soma_participacoes_pct": soma,
        "soma_confere": (abs(soma - 100.0) <= 0.5) if soma is not None else None,
        "socios_sem_participacao": sem_pct,
        "controlador": (
            {
                "nome": maior["nome"],
                "participacao_pct": maior["participacao_pct"],
                "controle_majoritario": maior["participacao_pct"] > 50.0,
            }
            if maior is not None
            else None
        ),
        "idade_empresa_anos": idade_anos,
    }


def _cruzamento(
    campo: str,
    contrato: Any,
    oficial: Any,
    confere: bool | None,
    detalhe: str,
) -> dict[str, Any]:
    return {
        "campo": campo,
        "contrato": contrato,
        "oficial": oficial,
        "confere": confere,
        "detalhe": detalhe,
    }


def _cruzamentos(
    fields: dict[str, Any],
    company: Any,
    target_cnpj: str | None,
) -> list[dict[str, Any]]:
    """Contrato social x cadastro oficial (BDC) — consistência cross-fonte."""
    out: list[dict[str, Any]] = []

    # CNPJ do contrato x empresa-alvo do dossiê.
    c_cnpj = _digits(fields.get("cnpj"))
    alvo = _digits(target_cnpj) or (_digits(company.cnpj) if company is not None else "")
    if c_cnpj and alvo:
        ok = c_cnpj == alvo
        out.append(
            _cruzamento(
                "cnpj",
                fields.get("cnpj"),
                alvo,
                ok,
                "CNPJ do contrato confere com a empresa-alvo."
                if ok
                else "CNPJ do contrato NÃO é o da empresa-alvo — documento de outra empresa?",
            )
        )
    elif c_cnpj or alvo:
        out.append(
            _cruzamento(
                "cnpj", fields.get("cnpj"), alvo or None, None, "Sem base para comparar."
            )
        )

    if company is None:
        return out

    # Razão social.
    c_name = _norm_name(fields.get("razao_social"))
    o_name = _norm_name(company.name)
    if c_name and o_name:
        ok = c_name == o_name or c_name in o_name or o_name in c_name
        out.append(
            _cruzamento(
                "razao_social",
                fields.get("razao_social"),
                company.name,
                ok,
                "Razão social confere com o registro oficial."
                if ok
                else "Razão social do contrato diverge do registro oficial.",
            )
        )

    # Capital social.
    c_cap = _to_float(fields.get("capital_social"))
    o_cap = _to_float(company.capital_social)
    if c_cap is not None and o_cap is not None and o_cap > 0:
        diff_pct = abs(c_cap - o_cap) / o_cap * 100
        ok = diff_pct <= _CAPITAL_TOLERANCE_PCT
        out.append(
            _cruzamento(
                "capital_social",
                c_cap,
                o_cap,
                ok,
                "Capital do contrato confere com o oficial."
                if ok
                else (
                    f"Capital diverge {diff_pct:.1f}% do oficial — alteração "
                    "contratual não registrada, ou contrato desatualizado?"
                ),
            )
        )
    elif c_cap is not None or o_cap is not None:
        out.append(
            _cruzamento(
                "capital_social", c_cap, o_cap, None, "Sem base para comparar."
            )
        )

    # Data de constituição.
    c_dt = _parse_date(fields.get("data_constituicao"))
    o_dt = company.founding_date
    if c_dt is not None and o_dt is not None:
        ok = c_dt == o_dt
        out.append(
            _cruzamento(
                "data_constituicao",
                c_dt.isoformat(),
                o_dt.isoformat(),
                ok,
                "Data de constituição confere com o registro oficial."
                if ok
                else "Data de constituição diverge do registro oficial.",
            )
        )

    return out


async def build_societario_payload(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> dict[str, Any]:
    """Ficha do contrato social homologado + estrutura QSA + cruzamentos BDC.

    Returns:
        `{encontrado: False, mensagem}` quando não há contrato extraído;
        senão `{encontrado, homologado, fonte, contrato, estrutura,
        cruzamentos}`. Shape estável — contrato lido pelo agente e pela UI.
    """
    from app.modules.credito.models.company import CreditDossierCompany
    from app.modules.credito.models.document import CreditDossierDocument
    from app.modules.credito.services.dossier import get_dossier

    row = (
        await db.execute(
            select(CreditDossierDocument)
            .where(
                CreditDossierDocument.tenant_id == tenant_id,
                CreditDossierDocument.dossier_id == dossier_id,
                CreditDossierDocument.doc_type == DocumentType.SOCIAL_CONTRACT,
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
                "Nenhum contrato social extraído no dossiê. "
                "Não há base para análise societária."
            ),
        }

    extraction = row.ai_extraction or {}
    fields = extraction.get("extracted_fields")
    if not isinstance(fields, dict):
        fields = {}

    raw_socios = fields.get("socios")
    socios = (
        [s for s in (_redact_socio(i) for i in raw_socios) if s is not None]
        if isinstance(raw_socios, list)
        else []
    )

    company = (
        await db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()

    dossier = await get_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)
    target_cnpj = dossier.target_cnpj if dossier else None

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
        "contrato": {
            "cnpj": fields.get("cnpj"),
            "razao_social": fields.get("razao_social"),
            "capital_social": _to_float(fields.get("capital_social")),
            "data_constituicao": fields.get("data_constituicao"),
            "objeto_social": fields.get("objeto_social"),
            "endereco": fields.get("endereco"),
            "socios": socios,
        },
        "estrutura": _estrutura(socios, _parse_date(fields.get("data_constituicao"))),
        "cruzamentos": _cruzamentos(fields, company, target_cnpj),
    }
