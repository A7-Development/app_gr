"""Mapper: /v2/fidc-custodia/report/aquisicao-consolidada/{cnpj}/{di}/{df}.

Wrapper: `{aquisicaoConsolidada: [...]}`. Schema validado contra sample
real de 583 cessoes (REALINVEST FIDC, periodo 2026-01-01..2026-01-08).

Inconsistencias da QiTech (vs liquidados-baixados-v2):
- `fundoCnpj` aqui e int (laa e str). `_normalize_cnpj_any` lida com ambos.
- `idRecebivel` aqui e int (laa e str). Convertido pra str sempre no DB.
- `valorCompra` e `valorVencimento` vem como inteiro em CENTAVOS
  (ex.: 7476156 = R$ 74.761,56). Em liquidados-baixados o mesmo conceito
  vem em REAIS (float ISO ou string BR). Inconsistencia confirmada em
  2026-05-18 cruzando wh_aquisicao_recebivel vs wh_estoque_recebivel —
  razao exata 100x. Aplicamos `_centavos_to_reais` em ambos os campos.

source_id = `{cnpj_fundo}|{idRecebivel}|aq` — UQ por cessao adquirida.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    parse_iso_or_none,
    to_decimal,
)

# Divisor pra conversao centavos -> reais. Constante explicita pra deixar
# claro o que esta acontecendo na callsite (vs literal "100").
_CENTAVOS_PER_REAL = Decimal("100")


def _centavos_to_reais(value: Any) -> Decimal:
    """Converte inteiro em centavos pra Decimal em reais.

    QiTech entrega `valorCompra` e `valorVencimento` no endpoint
    aquisicao-consolidada como int (centavos). Outros endpoints da mesma
    administradora usam float ISO ou string BR — divergencia confirmada
    em 2026-05-18 cruzando silver de aquisicao vs estoque.
    """
    return to_decimal(value) / _CENTAVOS_PER_REAL


def _normalize_cnpj_any(value: Any) -> str:
    """CNPJ pode vir int (42449234000160) ou str ("42.449.234/0001-60").
    Normaliza pra string com 14 digitos zero-paded."""
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value).zfill(14)
    digits = re.sub(r"\D", "", str(value))
    return digits.zfill(14) if digits else ""


def map_aquisicao_consolidada(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    cnpj_fundo: str,
) -> list[dict[str, Any]]:
    """Transforma payload em linhas pra `wh_aquisicao_recebivel`.

    Note: `cnpj_fundo` recebido como param e normalizado em ambos os lados
    do source_id pra defender contra drift de formato vindo do payload.
    """
    items = (
        payload.get("aquisicaoConsolidada")
        if isinstance(payload, dict)
        else None
    )
    if not isinstance(items, list) or not items:
        return []

    cnpj_fundo_norm = _normalize_cnpj_any(cnpj_fundo)
    ingested_at = datetime.now(UTC)
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        id_recebivel = str(item.get("idRecebivel", ""))
        source_id = f"{cnpj_fundo_norm}|{id_recebivel}|aq"

        dt_aquisicao = parse_iso_or_none(item.get("dataDaPosicao"))
        dt_vencimento = parse_iso_or_none(item.get("dataVencimento"))

        rows.append(
            {
                "tenant_id": tenant_id,
                "data_aquisicao": dt_aquisicao.date() if dt_aquisicao else None,
                "data_vencimento": dt_vencimento.date() if dt_vencimento else None,
                # Fundo
                "fundo_doc": _normalize_cnpj_any(item.get("fundoCnpj")) or cnpj_fundo_norm,
                "fundo_nome": str(item.get("fundoNome", "")),
                # Cedente
                "cedente_doc": _normalize_cnpj_any(item.get("cpfCnpjCedente")),
                "cedente_nome": str(item.get("cedente", "")),
                # Sacado
                "sacado_doc": _normalize_cnpj_any(item.get("cpfCnpjSacado")),
                "sacado_nome": str(item.get("nomeSacado", "")),
                # Recebivel
                "id_recebivel": id_recebivel,
                "seu_numero": str(item.get("seuNumero", "")),
                "numero_documento": str(item.get("numeroDocumento", "")),
                "tipo_recebivel": str(item.get("tipoRecebivel", "")),
                # Fatos. valor_compra e valor_vencimento vem em centavos
                # (int) do endpoint aquisicao-consolidada — converter pra
                # reais antes de gravar no silver. Ver docstring.
                "valor_compra": _centavos_to_reais(item.get("valorCompra")),
                "valor_vencimento": _centavos_to_reais(item.get("valorVencimento")),
                "prazo_recebivel": int(item.get("prazoRecebivel") or 0),
                "taxa_aquisicao": to_decimal(item.get("taxaAquisicao")),
                # Proveniencia
                **build_provenance(
                    source_id=source_id,
                    item=item,
                    ingested_at=ingested_at,
                    source_updated_at=dt_aquisicao,
                ),
            }
        )

    return rows
