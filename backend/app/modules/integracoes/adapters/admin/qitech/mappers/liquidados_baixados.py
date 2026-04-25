"""Mapper: /v2/fidc-custodia/report/liquidados-baixados/v2/{cnpj}/{di}/{df}.

Wrapper: `{liquidadosBaixados: [...]}`. 799 baixas no sample real.

Inconsistencias QiTech (versionar pra debugar):
- `valorVencimento`: as vezes float (12699.03), as vezes string com virgula
  ("12699,03"). `_parse_loose_decimal` aceita ambos.
- `ajuste`: idem ("0,00" string).
- `idRecebivel`: aqui str.
- `fundoCnpj`: aqui str (em aquisicao-consolidada e int).

source_id = `{cnpj_fundo}|{idRecebivel}|liq`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    parse_iso_or_none,
    to_decimal,
)
from app.modules.integracoes.adapters.admin.qitech.mappers.aquisicao_consolidada import (
    _normalize_cnpj_any,
)


def _parse_loose_decimal(value: Any) -> Decimal:
    """Decimal que aceita number (12699.03), string locale BR ("12699,03")
    OU string ISO ("12699.03"). Heuristica: presenca de virgula = formato BR
    (ponto e separador de milhar e deve ser removido). Sem virgula = ISO
    (ponto e decimal — nao mexer).

    Usado em campos onde a QiTech vacila no tipo entre versoes/endpoints.
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, int | float | Decimal):
        return to_decimal(value)
    s = str(value).strip()
    if not s:
        return Decimal("0")
    if "," in s:
        # Locale BR: '.' e separador de milhar, ',' e decimal.
        s = s.replace(".", "").replace(",", ".")
    # Senao: ja esta em ISO. Nao mexer no ponto.
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")


def map_liquidados_baixados(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    cnpj_fundo: str,
) -> list[dict[str, Any]]:
    """Transforma payload em linhas pra `wh_liquidacao_recebivel`."""
    items = (
        payload.get("liquidadosBaixados")
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
        source_id = f"{cnpj_fundo_norm}|{id_recebivel}|liq"

        dt_posicao = parse_iso_or_none(item.get("dataDaPosicao"))
        dt_aquisicao = parse_iso_or_none(item.get("dataAquisicao"))
        dt_vencimento = parse_iso_or_none(item.get("dataVencimento"))

        rows.append(
            {
                "tenant_id": tenant_id,
                "data_posicao": dt_posicao.date() if dt_posicao else None,
                "data_aquisicao": dt_aquisicao.date() if dt_aquisicao else None,
                "data_vencimento": dt_vencimento.date() if dt_vencimento else None,
                # Fundo
                "fundo_doc": _normalize_cnpj_any(item.get("fundoCnpj")) or cnpj_fundo_norm,
                "fundo_nome": str(item.get("fundoNome", "")),
                # Cedente / Sacado (chaves diferentes do endpoint 1: nomes
                # `cedente`/`sacado` em vez de `nomeCedente`/`nomeSacado`,
                # docs em `identificacaoCedente`/`identificacaoSacado` em
                # vez de `cpfCnpjCedente`).
                "cedente_doc": _normalize_cnpj_any(
                    item.get("identificacaoCedente")
                ),
                "cedente_nome": str(item.get("cedente", "")),
                "sacado_doc": _normalize_cnpj_any(
                    item.get("identificacaoSacado")
                ),
                "sacado_nome": str(item.get("sacado", "")),
                # Recebivel
                "id_recebivel": id_recebivel,
                "seu_numero": str(item.get("seuNumero", "")),
                "documento": str(item.get("documento", "")),
                "numero_correspondente": str(
                    item.get("numeroCorrespondente") or ""
                )
                or None,
                "tipo_recebivel": str(item.get("tipoRecebivel", "")),
                # Fatos
                "valor_aquisicao": _parse_loose_decimal(
                    item.get("valorAquisicao")
                ),
                "valor_vencimento": _parse_loose_decimal(
                    item.get("valorVencimento")
                ),
                "valor_pago": _parse_loose_decimal(item.get("valorPago")),
                "ajuste": _parse_loose_decimal(item.get("ajuste")),
                "taxa_aquisicao": _parse_loose_decimal(item.get("txAquisicao")),
                # Estado
                "st_recebivel": str(item.get("stRecebivel", "")),
                "tipo_movimento": str(item.get("tipoMovimento", "")),
                # Proveniencia
                **build_provenance(
                    source_id=source_id,
                    item=item,
                    ingested_at=ingested_at,
                    source_updated_at=dt_posicao,
                ),
            }
        )

    return rows
