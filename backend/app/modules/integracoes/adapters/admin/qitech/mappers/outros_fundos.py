"""Mapper: payload /netreport/report/market/outros-fundos/{data} -> dict canonico.

Contrato:

    map_outros_fundos(
        payload=<dict cru da QiTech>,
        tenant_id=<UUID>,
        data_posicao=<date>,
    ) -> list[dict]

Cada dict no retorno tem TODAS as colunas de `wh_posicao_cota_fundo`
(incluindo proveniencia via `Auditable`) — pronto para:

    stmt = pg_insert(PosicaoCotaFundo).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "source_id"], ...
    )

Payload de entrada (forma observada em 2026-01-13):

    {
      "relatorios": {
        "outros-fundos": [
          {
            "dataDaPosicao": "2026-01-13T00:00:00.000Z",
            "codigo": "REALIAVE",
            "fundo": "REALINVEST A VENCER",
            ... 14 outras chaves ...
          },
          ...
        ]
      },
      "_links": {"lastAvailableReport": "..."}
    }

Se a QiTech devolver envelope vazio (`{"relatorios": {}, "message": "Nao ha
resultados..."}`) a funcao devolve `[]` — comportamento intencional para
distinguir "dia sem dados" de "falha de integracao" no ETL.

source_id (chave de idempotencia): `{clienteId}|{codigo}|{YYYY-MM-DD}`.
Re-ingerir o mesmo dia substitui a linha via upsert (unique constraint
`uq_wh_posicao_cota_fundo`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    normalize_str_or_none,
    parse_iso_or_none,
    to_decimal,
)


def map_outros_fundos(
    *,
    payload: dict[str, Any],
    tenant_id: UUID,
    data_posicao: date,
) -> list[dict[str, Any]]:
    """Transforma payload QiTech em linhas prontas pra `wh_posicao_cota_fundo`.

    Args:
        payload: body JSON bruto retornado pelo endpoint de outros-fundos.
        tenant_id: dono da ingestao (escopo multi-tenant).
        data_posicao: data alvo do relatorio (vai em `data_posicao` e no
            `source_id` composto). Usa-se o param da chamada (nao confia
            no `dataDaPosicao` dentro do item — pode haver drift de TZ na
            api).

    Returns:
        Lista de dicts. Vazia se a QiTech reportou "sem resultados".
    """
    relatorios = payload.get("relatórios") if isinstance(payload, dict) else None
    if not isinstance(relatorios, dict):
        return []

    items = relatorios.get("outros-fundos")
    if not isinstance(items, list) or not items:
        return []

    ingested_at = datetime.now(UTC)
    data_iso = data_posicao.isoformat()
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            # Defensivo: a QiTech nunca misturou tipos na amostra, mas se
            # algum dia misturar, ignoramos itens sem shape de dict em vez
            # de propagar erro — sync deve ser resiliente.
            continue

        cliente_id = str(item.get("clienteId", ""))
        codigo = str(item.get("código", ""))
        # source_id determinista — idempotencia do upsert.
        source_id = f"{cliente_id}|{codigo}|{data_iso}"

        rows.append(
            {
                "tenant_id": tenant_id,
                # Quando
                "data_posicao": data_posicao,
                # Carteira
                "carteira_cliente_id": cliente_id,
                "carteira_cliente_nome": str(item.get("clienteNome", "")),
                "carteira_cliente_doc": str(item.get("cpfDoCliente", "")),
                "carteira_cliente_sac": normalize_str_or_none(
                    item.get("códigoDoClienteNoSAC")
                ),
                # Ativo
                "ativo_codigo": codigo,
                "ativo_nome": str(item.get("fundo", "")),
                "ativo_instituicao": str(item.get("nomeDaInstituição", "")),
                # Fatos
                "quantidade": to_decimal(item.get("quantidade")),
                "quantidade_bloqueada": to_decimal(item.get("quantidadeBloqueada")),
                "valor_cota": to_decimal(item.get("valorDaCota")),
                "valor_aplicacao_resgate": to_decimal(
                    item.get("valorAplicação/resgate")
                ),
                "valor_atual": to_decimal(item.get("valorAtual")),
                "valor_impostos": to_decimal(item.get("valorDeImpostos")),
                "valor_liquido": to_decimal(item.get("valorLíquido")),
                "percentual_sobre_fundos": to_decimal(
                    item.get("percentualSobreFundos")
                ),
                "percentual_sobre_total": to_decimal(
                    item.get("percentualSobreTotal")
                ),
                # Proveniencia (mixin Auditable)
                **build_provenance(
                    source_id=source_id,
                    item=item,
                    ingested_at=ingested_at,
                    source_updated_at=parse_iso_or_none(
                        item.get("dataDaPosição")
                    ),
                ),
            }
        )

    return rows
