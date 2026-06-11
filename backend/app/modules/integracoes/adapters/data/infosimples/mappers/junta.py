"""Mapper JUCESP — payload cru da Infosimples → campos canônicos.

Tolerante por construção (dict.get em tudo): OCR de portal muda de layout;
campo ausente vira None/[] e NUNCA derruba a consulta. Re-mapeamento sobre o
bronze é barato (§13.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


def _digits(raw: Any) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def _parse_date_br(raw: Any) -> date | None:
    """'30/01/2006' ou '2006-01-30' → date."""
    s = str(raw or "").strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _parse_brl(raw: Any) -> Decimal | None:
    """'R$ 500.000,00' / '500000.00' / 500000 → Decimal."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    s = str(raw)
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    # Formato BR: ponto = milhar, vírgula = decimal.
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


@dataclass(slots=True)
class JuntaFichaFields:
    """Ficha cadastral da Junta (vendor-neutro)."""

    nire: str | None = None
    nome: str | None = None
    cnpj: str | None = None  # dígitos
    tipo: str | None = None
    data_constituicao: date | None = None
    inicio_atividades: date | None = None
    inscricao_estadual: str | None = None
    capital_valor: Decimal | None = None
    capital_texto: str | None = None
    objeto_social: str | None = None
    endereco: dict[str, Any] | None = None
    # Quadro societário oficial da Junta: [{nome, documento?, qualificacao?,
    # texto?}] — shape tolerante (campos_extraidos do OCR variam).
    participantes: list[dict[str, Any]] = field(default_factory=list)
    procuradores: list[dict[str, Any]] = field(default_factory=list)
    # Histórico de arquivamentos (alterações contratuais): [{descricao?,
    # eventos?, numero/registro?, data?, sessao?, texto?}]
    arquivamentos: list[dict[str, Any]] = field(default_factory=list)
    autenticidade: str | None = None


def _as_list_of_dicts(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [i for i in raw if isinstance(i, dict)]
    if isinstance(raw, dict):
        # Alguns blocos vêm como {"campos_extraidos": [...], "texto": "..."}.
        extr = raw.get("campos_extraidos")
        if isinstance(extr, list):
            out = [i for i in extr if isinstance(i, dict)]
            if out:
                return out
        return [raw]
    return []


def map_ficha(item: dict[str, Any]) -> JuntaFichaFields:
    """Mapeia 1 resultado (data[0]) da ficha cadastral (completa ou simples)."""
    empresa = item.get("empresa") if isinstance(item.get("empresa"), dict) else {}
    capital = item.get("capital") if isinstance(item.get("capital"), dict) else {}
    endereco = item.get("endereco") if isinstance(item.get("endereco"), dict) else None

    return JuntaFichaFields(
        nire=str(item.get("nire") or empresa.get("nire") or "").strip() or None,
        nome=str(item.get("nome") or "").strip() or None,
        cnpj=_digits(empresa.get("cnpj") or item.get("cnpj")) or None,
        tipo=str(empresa.get("tipo") or "").strip() or None,
        data_constituicao=_parse_date_br(empresa.get("data_constituicao")),
        inicio_atividades=_parse_date_br(empresa.get("inicio_atividades")),
        inscricao_estadual=(
            str(empresa.get("inscricao_estadual") or "").strip() or None
        ),
        capital_valor=_parse_brl(
            capital.get("normalizado_valor") or capital.get("valor")
        ),
        capital_texto=str(capital.get("texto") or "").strip() or None,
        objeto_social=str(item.get("objeto_social") or "").strip() or None,
        endereco=endereco,
        participantes=_as_list_of_dicts(item.get("participantes")),
        procuradores=_as_list_of_dicts(item.get("procuradores")),
        arquivamentos=_as_list_of_dicts(item.get("arquivamentos")),
        autenticidade=str(item.get("autenticidade") or "").strip() or None,
    )


def fields_to_jsonable(f: JuntaFichaFields) -> dict[str, Any]:
    """Versão JSON-safe pra persistir em credit_dossier_company.junta_data."""
    return {
        "nire": f.nire,
        "nome": f.nome,
        "cnpj": f.cnpj,
        "tipo": f.tipo,
        "data_constituicao": (
            f.data_constituicao.isoformat() if f.data_constituicao else None
        ),
        "inicio_atividades": (
            f.inicio_atividades.isoformat() if f.inicio_atividades else None
        ),
        "inscricao_estadual": f.inscricao_estadual,
        "capital_valor": float(f.capital_valor) if f.capital_valor is not None else None,
        "capital_texto": f.capital_texto,
        "objeto_social": f.objeto_social,
        "endereco": f.endereco,
        "participantes": f.participantes,
        "procuradores": f.procuradores,
        "arquivamentos": f.arquivamentos,
        "autenticidade": f.autenticidade,
    }
