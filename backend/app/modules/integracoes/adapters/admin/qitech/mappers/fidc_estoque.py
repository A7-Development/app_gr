"""Mapper: CSV de FIDC Estoque QiTech -> linhas wh_estoque_recebivel.

QiTech entrega esse relatorio como CSV (separador `;`, locale BR) baixado
de uma URL S3 presigned. Diferente dos endpoints /netreport/ (sincronos
em JSON), este e assincrono: POST cria job, callback traz fileLink, nos
baixamos o CSV e parseamos.

Schema do CSV (30 colunas, validado em 2026-04-25 com sample real do
REALINVEST FIDC do dia 2026-01-08):

    nomeFundo;docFundo;dataFundo;
    nomeGestor;docGestor;
    nomeOriginador;docOriginador;
    nomeCedente;docCedente;
    nomeSacado;docSacado;
    seuNumero;numeroDocumento;tipoRecebivel;
    valorNominal;valorPresente;valorAquisicao;valorPdd;faixaPdd;
    dataReferencia;dataVencimentoOriginal;dataVencimentoAjustada;
    dataEmissao;dataAquisicao;
    prazo;prazoAnual;
    situacaoRecebivel;
    taxaCessao;taxaRecebivel;coobrigacao

Locale BR:
- Decimal: "3600,00" (virgula)
- Data: "08/01/2026" (dd/mm/yyyy)
- Boolean: "SIM" / "NAO"
- CNPJ formatado: "42.449.234/0001-60" — normalizamos pra digits-only

source_id (UQ): `{docFundo}|{docCedente}|{seuNumero}|{numeroDocumento}|{data_ref_iso}`.

A `data_referencia` e a do PARAM (data alvo do relatorio), nao a do
CSV — pra sustentar idempotencia mesmo se o conteudo do `dataReferencia`
da linha vier diferente por TZ ou ajuste.
"""

from __future__ import annotations

import csv
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO
from typing import Any
from uuid import UUID

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.admin.qitech.hashing import sha256_of_row
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION

# Header canonico esperado. Se a QiTech reordenar colunas no futuro,
# detectamos via DictReader (que matcha por nome). Mas se renomear,
# nosso mapper deixa a coluna nova sair vazia — investigar log do ETL.
_EXPECTED_HEADER = ["nomeFundo", "docFundo", "dataFundo", "nomeGestor", "docGestor", "nomeOriginador", "docOriginador", "nomeCedente", "docCedente", "nomeSacado", "docSacado", "seuNumero", "numeroDocumento", "tipoRecebivel", "valorNominal", "valorPresente", "valorAquisicao", "valorPdd", "faixaPdd", "dataReferencia", "dataVencimentoOriginal", "dataVencimentoAjustada", "dataEmissao", "dataAquisicao", "prazo", "prazoAnual", "situacaoRecebivel", "taxaCessao", "taxaRecebivel", "coobrigacao"]


def _normalize_cnpj(value: str | None) -> str:
    """Remove pontuacao de CNPJ, deixa so digitos."""
    if not value:
        return ""
    return re.sub(r"\D", "", value)


def _parse_decimal_br(value: str | None) -> Decimal:
    """Decimal com virgula brasileira: '3600,00' -> Decimal('3600.00').

    Trata vazio/None como Decimal('0'). NAO trata como erro -- CSV pode
    vir com colunas vazias em alguns recebiveis.
    """
    if value is None:
        return Decimal("0")
    s = value.strip()
    if not s:
        return Decimal("0")
    # Converte locale BR pra ISO: remove separador de milhar (.) e troca virgula por ponto.
    # Cuidado: o CSV nao usa separador de milhar (so virgula decimal),
    # mas se um dia vier "1.234,56" o replace cobre.
    iso = s.replace(".", "").replace(",", ".")
    return Decimal(iso)


def _parse_date_br(value: str | None) -> date | None:
    """Data BR 'dd/mm/yyyy' -> date. Retorna None se vazio/invalido."""
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return None


def _parse_bool_br(value: str | None) -> bool:
    """Boolean BR: 'SIM' -> True, 'NAO'/vazio -> False (case-insensitive)."""
    if not value:
        return False
    return value.strip().upper() == "SIM"


def _parse_int_or_zero(value: str | None) -> int:
    """Int tolerante. Vazio/invalido -> 0."""
    if not value:
        return 0
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return 0


def map_fidc_estoque(
    *,
    csv_text: str,
    tenant_id: UUID,
    data_referencia: date,
) -> list[dict[str, Any]]:
    """Transforma CSV cru de FIDC Estoque em linhas pra `wh_estoque_recebivel`.

    Args:
        csv_text: conteudo do CSV em texto (UTF-8 ou cp1252).
        tenant_id: dono da ingestao (escopo multi-tenant).
        data_referencia: data alvo do relatorio (vai em `data_referencia`
            e no source_id).

    Returns:
        Lista de dicts. Vazia se CSV so tem header (sem dados pra esse dia).
    """
    if not csv_text or not csv_text.strip():
        return []

    reader = csv.DictReader(StringIO(csv_text), delimiter=";")
    if not reader.fieldnames:
        return []

    ingested_at = datetime.now(UTC)
    data_iso = data_referencia.isoformat()
    rows: list[dict[str, Any]] = []

    for raw_row in reader:
        # Defensivo: linhas vazias ou malformadas (DictReader devolve dict
        # com chave None pra colunas extras quando a linha tem mais campos
        # que o header — ignoramos).
        if not raw_row or not raw_row.get("seuNumero"):
            continue

        fundo_doc = _normalize_cnpj(raw_row.get("docFundo"))
        cedente_doc = _normalize_cnpj(raw_row.get("docCedente"))
        seu_numero = (raw_row.get("seuNumero") or "").strip()
        numero_documento = (raw_row.get("numeroDocumento") or "").strip()

        # source_id determinista — UQ no upsert. Inclui cedente_doc
        # porque um mesmo seuNumero pode existir em diferentes cedentes
        # (titulos com numeracao por cedente).
        source_id = (
            f"{fundo_doc}|{cedente_doc}|{seu_numero}|{numero_documento}|{data_iso}"
        )

        rows.append(
            {
                "tenant_id": tenant_id,
                "data_referencia": data_referencia,
                # Fundo
                "fundo_doc": fundo_doc,
                "fundo_nome": (raw_row.get("nomeFundo") or "").strip(),
                "data_fundo": _parse_date_br(raw_row.get("dataFundo")),
                # Gestor
                "gestor_doc": _normalize_cnpj(raw_row.get("docGestor")),
                "gestor_nome": (raw_row.get("nomeGestor") or "").strip(),
                # Originador
                "originador_doc": _normalize_cnpj(raw_row.get("docOriginador")),
                "originador_nome": (raw_row.get("nomeOriginador") or "").strip(),
                # Cedente
                "cedente_doc": cedente_doc,
                "cedente_nome": (raw_row.get("nomeCedente") or "").strip(),
                # Sacado
                "sacado_doc": _normalize_cnpj(raw_row.get("docSacado")),
                "sacado_nome": (raw_row.get("nomeSacado") or "").strip(),
                # Recebivel
                "seu_numero": seu_numero,
                "numero_documento": numero_documento,
                "tipo_recebivel": (raw_row.get("tipoRecebivel") or "").strip(),
                # Valores
                "valor_nominal": _parse_decimal_br(raw_row.get("valorNominal")),
                "valor_presente": _parse_decimal_br(raw_row.get("valorPresente")),
                "valor_aquisicao": _parse_decimal_br(raw_row.get("valorAquisicao")),
                "valor_pdd": _parse_decimal_br(raw_row.get("valorPdd")),
                "faixa_pdd": (raw_row.get("faixaPdd") or "").strip(),
                # Datas
                "data_vencimento_original": _parse_date_br(
                    raw_row.get("dataVencimentoOriginal")
                ),
                "data_vencimento_ajustada": _parse_date_br(
                    raw_row.get("dataVencimentoAjustada")
                ),
                "data_emissao": _parse_date_br(raw_row.get("dataEmissao")),
                "data_aquisicao": _parse_date_br(raw_row.get("dataAquisicao")),
                "prazo": _parse_int_or_zero(raw_row.get("prazo")),
                "prazo_anual": _parse_decimal_br(raw_row.get("prazoAnual")),
                # Estado / risco
                "situacao_recebivel": (
                    raw_row.get("situacaoRecebivel") or ""
                ).strip(),
                "taxa_cessao": _parse_decimal_br(raw_row.get("taxaCessao")),
                "taxa_recebivel": _parse_decimal_br(raw_row.get("taxaRecebivel")),
                "coobrigacao": _parse_bool_br(raw_row.get("coobrigacao")),
                # Proveniencia (mixin Auditable)
                "source_type": SourceType.ADMIN_QITECH,
                "source_id": source_id,
                "source_updated_at": ingested_at,  # CSV nao traz timestamp
                "ingested_at": ingested_at,
                "hash_origem": sha256_of_row(raw_row),
                "ingested_by_version": ADAPTER_VERSION,
                "trust_level": TrustLevel.HIGH,
                "collected_by": None,
            }
        )

    return rows
