"""Sync do party model: Bitfin -> wh_entidade + papeis + grupo economico.

Endpoint proprio (`bitfin.entidades`), independente do `bitfin.full_sync` do
ERP — cadencia e enable separados.

Pipeline (ordem importa — cada passo resolve FKs do anterior):

1. `GrupoEconomico`            -> wh_grupo_economico
2. `Entidade` (completa, ~20k) -> wh_entidade (1 linha por tenant+documento)
                               -> wh_entidade_fonte (crosswalk EntidadeId->uuid;
                                  documento invalido = quarentena entidade_id NULL)
3. `Cliente` / `Sacado`        -> wh_entidade_papel (cedente / sacado),
                                  resolvendo entidade via crosswalk em memoria
4. `GrupoEconomicoMembro`      -> wh_grupo_economico_membro (arestas)

Politica de identidade (app/shared/documento.py): 1 entidade canonica por
(tenant, documento normalizado). Multiplas linhas-fonte com o mesmo documento
convergem pra mesma entidade (ultima DataDeCadastro vence nos campos
cadastrais); o crosswalk preserva TODOS os ids de fonte. Nada some em
silencio: linhas sem documento normalizavel ficam em quarentena contada no
summary e visivel em wh_entidade_fonte.

Full refresh idempotente (volumes pequenos: ~20k entidades, ~500 clientes,
~16k sacados). `since` ignorado.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import EntidadePapel, SourceType, TipoPessoa
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import fetch_rows
from app.modules.integracoes.adapters.erp.bitfin.etl import _bulk_upsert, _provenance
from app.modules.integracoes.adapters.erp.bitfin.queries import bitfin
from app.modules.integracoes.adapters.erp.bitfin.version import ADAPTER_VERSION
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.shared.documento import DocumentoNormalizado, normalizar_documento
from app.warehouse.conta_bancaria import ContaBancariaEntidade
from app.warehouse.entidade import (
    WhEntidade,
    WhEntidadeFonte,
    WhEntidadePapel,
    WhGrupoEconomico,
    WhGrupoEconomicoMembro,
)
from app.warehouse.posicao_papel import (
    WhPagamentoPracaMensal,
    WhPosicaoCedente,
    WhPosicaoCedenteProduto,
    WhPosicaoSacado,
    WhPosicaoSacadoCedente,
)

_TIPO_HINT = {"PJ": TipoPessoa.PJ, "PF": TipoPessoa.PF}


def _map_entidade(row: dict, tenant_id: UUID, doc: DocumentoNormalizado) -> dict:
    return {
        "tenant_id": tenant_id,
        "documento": doc.documento,
        "tipo_pessoa": doc.tipo_pessoa,
        "documento_raiz": doc.raiz,
        "filial_numero": doc.filial_numero,
        "is_matriz": doc.is_matriz,
        "nome": (row.get("nome") or "").strip() or "(sem nome)",
        "cnae_chave": row.get("cnae_chave"),
        "cnae_denominacao": row.get("cnae_denominacao"),
        "porte": row.get("porte"),
        "data_constituicao": row.get("data_constituicao"),
        "em_recuperacao_judicial": row.get("em_recuperacao_judicial"),
        "data_recuperacao_judicial": row.get("data_recuperacao_judicial"),
        "logradouro": row.get("logradouro"),
        "endereco_numero": row.get("endereco_numero"),
        "complemento": row.get("complemento"),
        "bairro": row.get("bairro"),
        "localidade": row.get("localidade"),
        "estado": row.get("estado"),
        "cep": (row.get("cep") or "").strip() or None,
        "pais": row.get("pais"),
        "endereco_verificado": row.get("endereco_verificado"),
        "grupo_economico_source_id": row.get("grupo_economico_source_id"),
        "data_cadastro_fonte": row.get("data_cadastro_fonte"),
        **_provenance(row["entidade_id"], row, row.get("data_cadastro_fonte")),
    }


async def sync_entidades(
    tenant_id: UUID,
    config: BitfinConfig,
    *,
    triggered_by: str = "system:scheduler",
    endpoint_name: str | None = None,
) -> dict[str, Any]:
    """Full refresh do party model. Retorna summary auditavel."""
    started_at = datetime.now(UTC)
    t0 = time.monotonic()

    db_name = config.database_bitfin
    grupos_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_GRUPO_ECONOMICO
    )
    entidade_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_ENTIDADE_FULL
    )
    cliente_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_CLIENTE_PAPEL
    )
    sacado_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_SACADO_PAPEL
    )
    membro_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_GRUPO_ECONOMICO_MEMBRO
    )
    pos_cedente_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_POSICAO_CEDENTE
    )
    pos_cedente_prod_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_POSICAO_CEDENTE_PRODUTO
    )
    pos_sacado_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_POSICAO_SACADO
    )
    pos_sacado_cedente_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_POSICAO_SACADO_CEDENTE
    )
    praca_mensal_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_PAGAMENTO_PRACA_MENSAL
    )
    conta_bancaria_rows = await asyncio.to_thread(
        fetch_rows, config, db_name, bitfin.SELECT_CONTA_BANCARIA
    )

    now = datetime.now(UTC)
    quarentena: list[dict] = []
    entidades: list[dict] = []
    # entidade_source_id -> documento canonico (para crosswalk + papeis)
    doc_by_source_id: dict[int, str] = {}

    # Ultima DataDeCadastro vence nos campos cadastrais quando 2+ linhas-fonte
    # compartilham o documento (o _bulk_upsert mantem a ULTIMA do batch).
    entidade_rows.sort(key=lambda r: (r.get("data_cadastro_fonte") or datetime.min))

    for row in entidade_rows:
        source_id = int(row["entidade_id"])
        doc = normalizar_documento(
            row.get("documento"), _TIPO_HINT.get((row.get("tipo") or "").strip())
        )
        if doc is None or not doc.valido:
            motivo = "documento_ausente_ou_sem_formato" if doc is None else (
                "check_digit_invalido"
            )
            quarentena.append(
                {
                    "tenant_id": tenant_id,
                    "source_type": SourceType.ERP_BITFIN,
                    "source_entity_id": str(source_id),
                    "entidade_id": None,
                    "documento_bruto": row.get("documento"),
                    "motivo_quarentena": motivo,
                    "fetched_at": now,
                    "fetched_by_version": ADAPTER_VERSION,
                }
            )
            continue
        doc_by_source_id[source_id] = doc.documento
        entidades.append(_map_entidade(row, tenant_id, doc))

    async with AsyncSessionLocal() as db:
        n_entidades = await _bulk_upsert(
            db, WhEntidade, entidades, ["tenant_id", "documento"]
        )

        # documento -> uuid canonico (do proprio tenant)
        id_rows = await db.execute(
            select(WhEntidade.documento, WhEntidade.id).where(
                WhEntidade.tenant_id == tenant_id
            )
        )
        uuid_by_doc: dict[str, UUID] = dict(id_rows.all())

        crosswalk = quarentena + [
            {
                "tenant_id": tenant_id,
                "source_type": SourceType.ERP_BITFIN,
                "source_entity_id": str(source_id),
                "entidade_id": uuid_by_doc[documento],
                "documento_bruto": None,
                "motivo_quarentena": None,
                "fetched_at": now,
                "fetched_by_version": ADAPTER_VERSION,
            }
            for source_id, documento in doc_by_source_id.items()
        ]
        n_crosswalk = await _bulk_upsert(
            db,
            WhEntidadeFonte,
            crosswalk,
            ["tenant_id", "source_type", "source_entity_id"],
        )

        # --- Papeis (cedente/sacado) — resolve via crosswalk em memoria ---
        uuid_by_source_id: dict[int, UUID] = {
            sid: uuid_by_doc[doc] for sid, doc in doc_by_source_id.items()
        }

        def _papel_rows(
            rows: list[dict], papel: EntidadePapel
        ) -> tuple[list[dict], int]:
            mapped: list[dict] = []
            unresolved = 0
            for r in rows:
                ent_uuid = uuid_by_source_id.get(int(r["entidade_source_id"]))
                if ent_uuid is None:
                    unresolved += 1  # entidade em quarentena — contado, nao some
                    continue
                status = r.get("situacao") or (
                    str(r["status_int"]) if r.get("status_int") is not None else None
                )
                mapped.append(
                    {
                        "tenant_id": tenant_id,
                        "entidade_id": ent_uuid,
                        "papel": papel,
                        "status_fonte": status,
                        "data_cadastro_fonte": r.get("data_cadastro_fonte"),
                        **_provenance(
                            r["papel_source_id"], r, r.get("data_cadastro_fonte")
                        ),
                    }
                )
            return mapped, unresolved

        cedentes, ced_quarentena = _papel_rows(cliente_rows, EntidadePapel.CEDENTE)
        sacados, sac_quarentena = _papel_rows(sacado_rows, EntidadePapel.SACADO)
        n_papeis = await _bulk_upsert(
            db,
            WhEntidadePapel,
            cedentes + sacados,
            ["tenant_id", "source_type", "papel", "source_id"],
        )

        # --- Grupos economicos + membros ---
        grupos = [
            {
                "tenant_id": tenant_id,
                "nome": (g.get("nome") or "").strip() or "(sem nome)",
                "segmento": g.get("segmento"),
                "quantidade_membros": g.get("quantidade_membros"),
                "data_cadastro_fonte": g.get("data_cadastro_fonte"),
                **_provenance(g["grupo_source_id"], g, g.get("data_cadastro_fonte")),
            }
            for g in grupos_rows
        ]
        n_grupos = await _bulk_upsert(
            db, WhGrupoEconomico, grupos, ["tenant_id", "source_type", "source_id"]
        )

        grupo_rows = await db.execute(
            select(WhGrupoEconomico.source_id, WhGrupoEconomico.id).where(
                WhGrupoEconomico.tenant_id == tenant_id,
                WhGrupoEconomico.source_type == SourceType.ERP_BITFIN,
            )
        )
        grupo_uuid_by_source: dict[str, UUID] = dict(grupo_rows.all())

        membros: list[dict] = []
        membros_sem_grupo = 0
        for m in membro_rows:
            grupo_uuid = grupo_uuid_by_source.get(str(m["grupo_source_id"]))
            if grupo_uuid is None:
                membros_sem_grupo += 1
                continue
            edge_id = f"{m['grupo_source_id']}:{m['entidade_source_id']}"
            membros.append(
                {
                    "tenant_id": tenant_id,
                    "grupo_economico_id": grupo_uuid,
                    # NULL = membro em quarentena; aresta preservada p/ auditoria
                    "entidade_id": uuid_by_source_id.get(
                        int(m["entidade_source_id"])
                    ),
                    "vinculo": m.get("vinculo"),
                    "data_cadastro_fonte": m.get("data_cadastro_fonte"),
                    **_provenance(edge_id, m, m.get("data_cadastro_fonte")),
                }
            )
        n_membros = await _bulk_upsert(
            db,
            WhGrupoEconomicoMembro,
            membros,
            ["tenant_id", "source_type", "source_id"],
        )

        # --- Posicoes por papel (F1) — snapshot vendor-computed, full refresh.
        # entidade_id NULL quando a entidade do papel esta em quarentena
        # (posicao preservada; nada some).
        def _map_posicao(row: dict, source_id: str) -> dict:
            data = {
                k: v
                for k, v in row.items()
                if k not in ("posicao_id", "entidade_source_id")
            }
            data["papel_source_id"] = str(row["papel_source_id"])
            return {
                "tenant_id": tenant_id,
                "entidade_id": uuid_by_source_id.get(
                    int(row["entidade_source_id"])
                ),
                **data,
                **_provenance(source_id, row, row.get("liquidez_data_apuracao")),
            }

        n_pos_cedente = await _bulk_upsert(
            db,
            WhPosicaoCedente,
            [_map_posicao(r, str(r["posicao_id"])) for r in pos_cedente_rows],
            ["tenant_id", "source_type", "source_id"],
        )
        n_pos_cedente_prod = await _bulk_upsert(
            db,
            WhPosicaoCedenteProduto,
            [
                _map_posicao(r, f"{r['posicao_id']}:{r['produto_source_id']}")
                for r in pos_cedente_prod_rows
            ],
            ["tenant_id", "source_type", "source_id"],
        )
        n_pos_sacado = await _bulk_upsert(
            db,
            WhPosicaoSacado,
            [_map_posicao(r, str(r["posicao_id"])) for r in pos_sacado_rows],
            ["tenant_id", "source_type", "source_id"],
        )

        # Relacao sacado x cedente + serie mensal de praca (sinais de
        # autoliquidacao). Resolve o lado cedente via crosswalk tambem.
        def _map_sacado_cedente(row: dict) -> dict:
            data = {
                k: v
                for k, v in row.items()
                if k
                not in ("posicao_id", "entidade_source_id", "cedente_entidade_source_id")
            }
            data["papel_source_id"] = str(row["papel_source_id"])
            if row.get("cedente_papel_source_id") is not None:
                data["cedente_papel_source_id"] = str(row["cedente_papel_source_id"])
            ced_src = row.get("cedente_entidade_source_id")
            return {
                "tenant_id": tenant_id,
                "entidade_id": uuid_by_source_id.get(int(row["entidade_source_id"])),
                "cedente_entidade_id": uuid_by_source_id.get(int(ced_src))
                if ced_src is not None
                else None,
                **data,
                **_provenance(
                    f"{row['posicao_id']}:{row['conta_operacional_source_id']}", row
                ),
            }

        n_pos_sacado_cedente = await _bulk_upsert(
            db,
            WhPosicaoSacadoCedente,
            [_map_sacado_cedente(r) for r in pos_sacado_cedente_rows],
            ["tenant_id", "source_type", "source_id"],
        )

        def _map_praca_mensal(row: dict) -> dict:
            data = {k: v for k, v in row.items() if k != "cedente_entidade_source_id"}
            if row.get("cedente_papel_source_id") is not None:
                data["cedente_papel_source_id"] = str(row["cedente_papel_source_id"])
            ced_src = row.get("cedente_entidade_source_id")
            return {
                "tenant_id": tenant_id,
                "cedente_entidade_id": uuid_by_source_id.get(int(ced_src))
                if ced_src is not None
                else None,
                **data,
                **_provenance(
                    f"{row['conta_operacional_source_id']}:{row['ano']}-{row['mes']}",
                    row,
                ),
            }

        n_praca_mensal = await _bulk_upsert(
            db,
            WhPagamentoPracaMensal,
            [_map_praca_mensal(r) for r in praca_mensal_rows],
            ["tenant_id", "source_type", "source_id"],
        )

        # Contas bancarias cadastradas por entidade — consumidas pelo S1
        # ("praca do cedente") do modelo de deteccao de liquidacao.
        def _map_conta_bancaria(row: dict) -> dict:
            doc = normalizar_documento(
                row.get("documento"),
                _TIPO_HINT.get((row.get("tipo_entidade") or "").strip()),
            )
            return {
                "tenant_id": tenant_id,
                "entidade_source_id": int(row["entidade_source_id"]),
                "entidade_documento": doc.documento if doc and doc.valido else None,
                "banco_id": row.get("banco_id"),
                "banco_codigo": (str(row.get("banco_codigo") or "").strip() or None),
                "banco_nome": row.get("banco_nome"),
                "banco_digital": row.get("banco_digital"),
                "agencia_codigo": (
                    str(row.get("agencia_codigo") or "").strip() or None
                ),
                "agencia_digito": (
                    str(row.get("agencia_digito") or "").strip() or None
                ),
                "agencia_localidade": row.get("agencia_localidade"),
                "agencia_estado": (
                    str(row.get("agencia_estado") or "").strip() or None
                ),
                "numero_conta": row.get("numero_conta"),
                "tipo_conta": row.get("tipo_conta"),
                "ativa": row.get("ativa"),
                "escrow": row.get("escrow"),
                "suporte_para_depositos": row.get("suporte_para_depositos"),
                **_provenance(
                    str(row["conta_bancaria_id"]),
                    row,
                    row.get("data_cadastro_fonte"),
                ),
            }

        n_contas = await _bulk_upsert(
            db,
            ContaBancariaEntidade,
            [_map_conta_bancaria(r) for r in conta_bancaria_rows],
            ["tenant_id", "source_id"],
        )

    summary = {
        "adapter_version": ADAPTER_VERSION,
        "started_at": started_at.isoformat(),
        "elapsed_seconds": round(time.monotonic() - t0, 2),
        "tables": [
            {"table": "wh_entidade", "rows": n_entidades},
            {"table": "wh_entidade_fonte", "rows": n_crosswalk},
            {"table": "wh_entidade_papel", "rows": n_papeis},
            {"table": "wh_grupo_economico", "rows": n_grupos},
            {"table": "wh_grupo_economico_membro", "rows": n_membros},
            {"table": "wh_posicao_cedente", "rows": n_pos_cedente},
            {"table": "wh_posicao_cedente_produto", "rows": n_pos_cedente_prod},
            {"table": "wh_posicao_sacado", "rows": n_pos_sacado},
            {"table": "wh_posicao_sacado_cedente", "rows": n_pos_sacado_cedente},
            {"table": "wh_pagamento_praca_mensal", "rows": n_praca_mensal},
            {"table": "wh_conta_bancaria", "rows": n_contas},
        ],
        "quarentena_documentos": len(quarentena),
        "papeis_em_quarentena": {
            "cedente": ced_quarentena,
            "sacado": sac_quarentena,
        },
        "membros_sem_grupo": membros_sem_grupo,
        "errors": [],
    }

    async with AsyncSessionLocal() as db:
        db.add(
            DecisionLog(
                tenant_id=tenant_id,
                decision_type=DecisionType.SYNC,
                inputs_ref={"endpoint": endpoint_name},
                rule_or_model="bitfin_adapter",
                rule_or_model_version=ADAPTER_VERSION,
                endpoint_name=endpoint_name,
                output=summary,
                explanation=(
                    f"party model: {n_entidades} entidades, {n_papeis} papeis, "
                    f"{len(quarentena)} em quarentena"
                ),
                triggered_by=triggered_by,
            )
        )
        await db.commit()

    return summary
