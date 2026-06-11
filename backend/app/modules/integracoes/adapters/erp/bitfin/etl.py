"""ETL orquestrador: MSSQL (UNLTD_<cliente>) -> gr_db warehouse.

Desenho:
- Cada tabela-alvo tem uma funcao `sync_<tabela>(tenant_id, since)`.
- Extract roda em thread pool (pyodbc e sync); Load em async (SQLAlchemy).
- Upsert idempotente via `ON CONFLICT DO UPDATE` (Postgres).
- Cada sync grava uma entrada em `decision_log` (sistema auditavel).
- Proveniencia completa em cada linha (source_type, source_id, hash_origem, ...).

Adapter v2.0.0 (2026-05-12): o caminho critico do DRE deixou de depender
do banco ANALYTICS (A7-especifico). Bronze passou a cobrir as 3 fontes do
DRE direto em UNLTD_<X>; silver `wh_dre_mensal` agora monta DRE a partir
do bronze + classifier `wh_dre_classification_rule`. Resta apenas
`sync_titulo_snapshot` (elig_snapshot_titulo em ANALYTICS) -- followup
separado pra eliminar.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from itertools import islice
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType, TrustLevel
from app.modules.controladoria.services.dre import (
    DreClassifier,
    load_dre_classifier,
)
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import fetch_rows
from app.modules.integracoes.adapters.erp.bitfin.hashing import sha256_of_row
from app.modules.integracoes.adapters.erp.bitfin.queries import analytics, bitfin
from app.modules.integracoes.adapters.erp.bitfin.receitas import (
    sync_receita_grafica,
    sync_receita_mora_liquidacao,
    sync_receita_operacao,
    sync_receita_recompra,
)
from app.modules.integracoes.adapters.erp.bitfin.version import ADAPTER_VERSION
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.shared.audit_log.sync_health import last_sync_at
from app.warehouse.bitfin_entidade import WhBitfinEntidade
from app.warehouse.bitfin_raw_debenture import (
    TIPO_ORIGEM_VALOR_ATUALIZADO_DIA,
    BitfinRawDebenture,
)
from app.warehouse.bitfin_raw_dre import (
    TIPO_ORIGEM_COMISSAO,
    TIPO_ORIGEM_DEMONSTRATIVO,
    TIPO_ORIGEM_PAGAMENTO,
    BitfinRawDre,
)
from app.warehouse.bitfin_tarifa_catalogo import WhBitfinTarifaCatalogo
from app.warehouse.caixa_snapshot import CaixaSnapshot
from app.warehouse.dim import DimProduto, DimUnidadeAdministrativa
from app.warehouse.dre import DreMensal
from app.warehouse.operacao import Operacao, OperacaoItem
from app.warehouse.posicao_debenture import ORIGEM_SNAPSHOT, PosicaoDebentureDia
from app.warehouse.titulo import Titulo
from app.warehouse.titulo_snapshot import TituloSnapshot

# Discriminator -> Fonte da regra de classificacao. Mapeamento explicito
# entre o `tipo_origem` do bronze (decisao tecnica) e o `fonte` da regra
# (decisao de dominio).
_TIPO_TO_FONTE: dict[str, str] = {
    TIPO_ORIGEM_DEMONSTRATIVO: "DRE_OPERACIONAL",
    TIPO_ORIGEM_PAGAMENTO: "CONTAS_A_PAGAR",
    TIPO_ORIGEM_COMISSAO: "COMISSAO",
}

CHUNK_SIZE = 1000
MAX_PG_PARAMS = 30000  # margem abaixo do limite asyncpg/Postgres de 32767
EPOCH = date(1900, 1, 1)


def _chunked(iterable: list, size: int):
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


def _provenance(source_id: Any, row: dict, source_updated_at: Any = None) -> dict:
    """Campos de proveniencia adicionados a cada linha antes do insert."""
    return {
        "source_type": SourceType.ERP_BITFIN,
        "source_id": str(source_id),
        "source_updated_at": source_updated_at,
        "ingested_at": datetime.now(UTC),
        "hash_origem": sha256_of_row(row),
        "ingested_by_version": ADAPTER_VERSION,
        "trust_level": TrustLevel.HIGH,
        "collected_by": None,
    }


# ---- Mappers ----


def _map_titulo_snapshot(row: dict, tenant_id: UUID) -> dict:
    return {
        "tenant_id": tenant_id,
        **row,
        **_provenance(row["snapshot_id"], row, row["data_ref"]),
    }


def _map_operacao(row: dict, tenant_id: UUID) -> dict:
    # OperacaoResultado nao-preenchido = operacao nao efetivada ainda; usa defaults
    metric_defaults = {
        "prazo_medio_real": 0,
        "prazo_medio_cobrado": 0,
        "total_bruto": 0,
        "total_liquido": 0,
        "total_de_juros": 0,
        "total_de_ad_valorem": 0,
        "total_de_iof": 0,
        "total_de_imposto": 0,
        "total_de_rebate": 0,
        "valor_medio_dos_titulos": 0,
        "quantidade_de_sacados": 0,
        "taxa_de_juros": 0,
        "taxa_de_ad_valorem": 0,
        "taxa_de_iof": 0,
        "taxa_de_imposto": 0,
        "taxa_de_rebate": 0,
        "spread": 0,
        "fator_de_desconto_cobrado": 0,
        "fator_de_desconto_real": 0,
        "floating_para_prazo": 0,
        "total_das_consultas_financeiras": 0,
        "total_dos_registros_bancarios": 0,
        "total_das_consultas_fiscais": 0,
        "total_dos_comunicados_de_cessao": 0,
        "total_dos_documentos_digitais": 0,
        "total_dos_descontos_ou_abatimentos": 0,
    }
    merged = {**metric_defaults, **{k: v for k, v in row.items() if v is not None}}
    return {
        "tenant_id": tenant_id,
        **merged,
        **_provenance(
            row["operacao_id"], row, row.get("data_de_efetivacao") or row["data_de_cadastro"]
        ),
    }


def _map_operacao_item(row: dict, tenant_id: UUID) -> dict:
    defaults = {
        "valor_base": 0,
        "valor_liquido": 0,
        "valor_presente": 0,
        "valor_de_juros": 0,
        "valor_do_ad_valorem": 0,
        "valor_do_iof": 0,
        "valor_do_rebate": 0,
        "saldo_devedor": 0,
        "prazo_real": 0,
        "prazo_cobrado": 0,
        "sugerido_para_exclusao": False,
    }
    merged = {**defaults, **{k: v for k, v in row.items() if v is not None}}
    return {
        "tenant_id": tenant_id,
        **merged,
        **_provenance(row["item_da_operacao_id"], row, row.get("data_de_vencimento_original")),
    }


def _map_titulo(row: dict, tenant_id: UUID) -> dict:
    defaults = {
        "valor_do_pagamento": 0,
        "valor_liquido": 0,
        "saldo_devedor": 0,
        "sustado_judicialmente": False,
    }
    merged = {**defaults, **{k: v for k, v in row.items() if v is not None}}
    return {
        "tenant_id": tenant_id,
        **merged,
        **_provenance(row["titulo_id"], row, row["data_da_situacao"]),
    }


def _map_dim_ua(row: dict, tenant_id: UUID) -> dict:
    """Mapeia Bitfin.UnidadeAdministrativa -> wh_dim_unidade_administrativa.

    Campos especiais:
    - `Ativa` vem do MSSQL como bool (True/False) — preserva tipo.
    - `Alias` vira `nome` (nao ha campo "Nome" no Bitfin).
    - `Classe` opcional (pode ser None).
    """
    return {
        "tenant_id": tenant_id,
        **row,
        **_provenance(row["ua_id"], row, None),
    }


def _map_dim_produto(row: dict, tenant_id: UUID) -> dict:
    """Mapeia Bitfin.Produto -> wh_dim_produto.

    - `Sigla` e `Descricao` ja vem nomeados pelo SELECT (`sigla`, `nome`).
    - `produto_de_risco` vem como bool do MSSQL.
    - `tipo_de_contrato` pode ser None.
    """
    return {
        "tenant_id": tenant_id,
        **row,
        **_provenance(row["produto_id"], row, None),
    }


def _map_caixa_snapshot(row: dict, tenant_id: UUID, data_snapshot: date) -> dict:
    """Mapeia ContaBancaria + ContaCorrente + UA + flags -> wh_caixa_snapshot.

    Granularidade silver: 1 linha por (tenant, conta_bancaria, data_snapshot).
    Ao re-rodar a sync no mesmo dia, UPSERT substitui a row de hoje (saldo
    atualizado). Historico cresce 1 row por (conta, dia).

    Flags `eh_caucao` / `eh_travada` chegam como int 0/1 do CASE WHEN no
    MSSQL — convertidos para bool aqui.
    """
    return {
        "tenant_id": tenant_id,
        "data_snapshot": data_snapshot,
        **row,
        "eh_caucao": bool(row.get("eh_caucao")),
        "eh_travada": bool(row.get("eh_travada")),
        **_provenance(row["conta_bancaria_id"], row, None),
    }


# ---- Upsert helpers ----


async def _bulk_upsert(
    db: AsyncSession, model, rows: list[dict], conflict_columns: list[str]
) -> int:
    """Upsert idempotente em chunks. Retorna total de rows afetadas.

    Resolve 3 problemas:
    1. **Chunk dinamico**: n_rows * n_cols deve ficar abaixo do limite asyncpg
       (32767 params). Calculado a partir do numero de colunas da tabela.
    2. **Row normalization**: bulk `VALUES` exige que todas as rows tenham as
       mesmas chaves. Rows vindas dos mappers podem ter keys faltando quando
       um campo e None/nullable — preenchemos com None explicito.
    3. **Deduplicacao**: `ON CONFLICT DO UPDATE` falha se o mesmo batch tem
       duas linhas com o mesmo unique key. Deduplicamos mantendo a ultima.
    """
    if not rows:
        return 0

    # 1. Lista de colunas do model (exceto `id` autogerado)
    all_columns = [c.name for c in model.__table__.columns if c.name != "id"]

    # 2. Normalizar: toda row tem TODAS as chaves (None para ausentes)
    normalized = [{col: row.get(col) for col in all_columns} for row in rows]

    # 3. Deduplicar por conflict_columns (mantem ultima ocorrencia)
    seen: dict[tuple, dict] = {}
    for row in normalized:
        key = tuple(row[c] for c in conflict_columns)
        seen[key] = row
    deduped = list(seen.values())

    # 4. Chunk dinamico baseado no numero de colunas
    chunk_size = max(1, min(CHUNK_SIZE, MAX_PG_PARAMS // len(all_columns)))

    update_cols_names = [
        c.name
        for c in model.__table__.columns
        if c.name not in {"id", *conflict_columns, "ingested_at"}
    ]

    total = 0
    for chunk in _chunked(deduped, chunk_size):
        stmt = pg_insert(model.__table__).values(chunk)
        update_set = {name: stmt.excluded[name] for name in update_cols_names}
        stmt = stmt.on_conflict_do_update(index_elements=conflict_columns, set_=update_set)
        await db.execute(stmt)
        total += len(chunk)
    await db.commit()
    return total


# ---- Sync functions (uma por tabela alvo) ----


async def sync_titulo_snapshot(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    # ANALYTICS opcional (v2.0.0+). Tenant sem ANALYTICS configurado pula
    # esse sync sem erro -- e o ultimo consumer de ANALYTICS pendente de
    # eliminacao (followup separado).
    if not config.database_analytics:
        return {
            "table": "wh_titulo_snapshot",
            "rows": 0,
            "skipped_reason": "database_analytics_not_configured",
        }
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_analytics, analytics.SELECT_SNAPSHOT_TITULO, (cutoff,)
    )
    mapped = [_map_titulo_snapshot(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(
            db, TituloSnapshot, mapped, ["tenant_id", "data_ref", "source_id"]
        )
    return {"table": "wh_titulo_snapshot", "rows": count}


async def sync_operacao(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_OPERACAO, (cutoff,)
    )
    mapped = [_map_operacao(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, Operacao, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_operacao", "rows": count}


async def sync_operacao_item(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_OPERACAO_ITEM
    )
    mapped = [_map_operacao_item(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, OperacaoItem, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_operacao_item", "rows": count}


async def sync_titulo(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_TITULO, (cutoff,)
    )
    mapped = [_map_titulo(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, Titulo, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_titulo", "rows": count}


# ---- Silver builder: bronze -> wh_dre_mensal -------------------------------
#
# v2.0.0+: o silver `wh_dre_mensal` deixou de fetchar `ANALYTICS.dbo.vw_DRE`
# e passou a montar DRE a partir das 3 fontes bronze (UNLTD_<X>), aplicando
# o classifier global de `wh_dre_classification_rule`. Replay barato e
# multi-tenant viabilizado.
#
# Paridade com vw_DRE legacy: bloco 1 mapeia 1:1 com d.TotalApurado/Custo;
# bloco 2 espelha o `Custo=Valor, Resultado=-Valor`; bloco 3 idem para
# Comissao. Caveat preservado: bloco 2 ignora coluna `Direcao` (D/C) -- ja
# era o comportamento da vw_DRE.


def _silver_source_id(
    *,
    competencia: date | str,
    grupo_dre: str,
    subgrupo: str,
    descricao: str,
    entidade_id: int | None,
    produto_id: int | None,
    unidade_administrativa_id: int | None,
    fonte: str,
) -> str:
    """source_id sintetico para wh_dre_mensal (vide uq_wh_dre_mensal_source).
    Estavel entre runs com mesma classificacao -> idempotencia do upsert.

    `unidade_administrativa_id` E PARTE DA CHAVE: o mesmo cedente+produto+
    descricao pode operar em >1 fundo (A7 + RealInvest) na mesma competencia;
    sem o ua_id na chave, as linhas colidem e o upsert descarta a do fundo
    'perdedor' (bug que subcontava o A7). Ver project_dre_bitfin."""
    return (
        f"{competencia}|{grupo_dre}|{subgrupo}|{descricao}|"
        f"{entidade_id}|{produto_id}|{unidade_administrativa_id}|{fonte}"
    )


_ZERO = Decimal("0")


def _to_date(value: Any) -> date:
    """Coerce bronze JSONB date value em `date`.

    pyodbc serializa SQL Server DATE/DATETIME como `date`/`datetime` em
    Python; ao gravar no payload JSONB do bronze, viram strings ISO
    ("YYYY-MM-DD" ou "YYYY-MM-DDTHH:MM:SS..."). asyncpg recusa string em
    coluna DATE (`'str' object has no attribute 'toordinal'`).

    Fail-hard quando o tipo nao bate — `competencia` e estrutural (chave
    de proveniencia + indice na silver), nao pode virar default silencioso.
    """
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        # Aceita "YYYY-MM-DD" ou ISO datetime com sufixo de hora/timezone.
        return date.fromisoformat(value[:10])
    raise TypeError(
        f"competencia bronze tem tipo inesperado: {type(value).__name__}={value!r}"
    )


def _to_decimal(value: Any) -> Decimal:
    """Coerce bronze JSONB value (string ou number) em Decimal de forma defensiva.

    pyodbc serializa colunas SQL Server NUMERIC/DECIMAL como `Decimal` em
    Python; quando o payload bronze e gravado como JSONB, esses Decimals
    viram **strings** ("1500.00000"). Quaisquer operacoes aritmeticas
    posteriores sobre o valor cru (ex.: `-valor`) lancam
    `TypeError: bad operand type for unary -: 'str'`. Este helper normaliza:

    - None / "" / lista / dict -> Decimal("0")
    - string numerica          -> Decimal(value)
    - int / float / Decimal    -> Decimal(str(value))

    Em casos de string mal-formada, retorna 0 (fail-soft) — preferimos um
    silver-row com valor zero a derrubar o sync inteiro de uma competencia.
    """
    if value is None or value == "":
        return _ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return _ZERO


def _bronze_row_to_silver(
    *,
    tipo_origem: str,
    bronze_row: dict[str, Any],
    classifier: DreClassifier,
    tenant_id: UUID,
) -> dict | None:
    """Converte 1 row do payload bronze em 1 row do silver wh_dre_mensal.
    Retorna None se a row deve ser descartada (sem classificacao, ativo=False,
    ou filtro de bloco -- ex.: comissao<=0)."""
    fonte = _TIPO_TO_FONTE[tipo_origem]

    if tipo_origem == TIPO_ORIGEM_DEMONSTRATIVO:
        # Bloco 1 -- DemonstrativoDeResultado
        categoria = bronze_row.get("categoria")
        if not categoria:
            return None
        cls = classifier.classify(fonte, categoria)
        if cls is None or not cls.ativo:
            return None
        descricao = bronze_row.get("descricao") or ""
        entidade_id = bronze_row.get("entidade_id")
        produto_id = bronze_row.get("produto_id")
        ua_id = bronze_row.get("unidade_administrativa_id")
        return {
            "ano": bronze_row["ano"],
            "mes": bronze_row["mes"],
            "competencia": _to_date(bronze_row["competencia"]),
            "ordem_grupo": cls.ordem_grupo,
            "grupo_dre": cls.grupo_dre,
            "subgrupo": cls.subgrupo,
            "descricao": descricao,
            "fornecedor": None,
            "fornecedor_documento": None,
            "entidade_id": entidade_id,
            "produto_id": produto_id,
            "unidade_administrativa_id": ua_id,
            "fonte": fonte,
            "fonte_integracao": "bitfin",
            "receita": _to_decimal(bronze_row.get("total_apurado")),
            "custo": _to_decimal(bronze_row.get("total_do_custo")),
            "resultado": _to_decimal(bronze_row.get("resultado")),
            "quantidade": int(bronze_row.get("quantidade") or 0),
            "_source_id": _silver_source_id(
                competencia=_to_date(bronze_row["competencia"]),
                grupo_dre=cls.grupo_dre,
                subgrupo=cls.subgrupo,
                descricao=descricao,
                entidade_id=entidade_id,
                produto_id=produto_id,
                unidade_administrativa_id=ua_id,
                fonte=fonte,
            ),
        }

    if tipo_origem == TIPO_ORIGEM_PAGAMENTO:
        # Bloco 2 -- PagamentoOpcaoDePagamento. Espelha vw_DRE block 2:
        # categoria vira "Descricao", Valor vira Custo, -Valor vira Resultado.
        # IMPORTANTE: a vw_DRE original ignora `Direcao` (D/C) -- preservamos
        # o mesmo comportamento para paridade. Se virar bug em audit, fix
        # separado no mapper (e nao retroceder ao vw_DRE).
        categoria = bronze_row.get("categoria")
        if not categoria:
            return None
        cls = classifier.classify(fonte, categoria)
        if cls is None or not cls.ativo:
            return None
        valor = _to_decimal(bronze_row.get("valor"))
        ua_id = bronze_row.get("unidade_administrativa_id")
        return {
            "ano": bronze_row["ano"],
            "mes": bronze_row["mes"],
            "competencia": _to_date(bronze_row["competencia"]),
            "ordem_grupo": cls.ordem_grupo,
            "grupo_dre": cls.grupo_dre,
            "subgrupo": cls.subgrupo,
            "descricao": categoria,
            "fornecedor": bronze_row.get("fornecedor_nome"),
            "fornecedor_documento": bronze_row.get("fornecedor_documento"),
            "entidade_id": None,
            "produto_id": None,
            "unidade_administrativa_id": ua_id,
            "fonte": fonte,
            "fonte_integracao": "bitfin",
            "receita": _ZERO,
            "custo": valor,
            "resultado": -valor,
            "quantidade": 1,
            "_source_id": _silver_source_id(
                competencia=_to_date(bronze_row["competencia"]),
                grupo_dre=cls.grupo_dre,
                subgrupo=cls.subgrupo,
                descricao=categoria,
                entidade_id=None,
                produto_id=None,
                unidade_administrativa_id=ua_id,
                fonte=fonte,
            ),
        }

    if tipo_origem == TIPO_ORIGEM_COMISSAO:
        # Bloco 3 -- ComissaoComercialFechamento. vw_DRE block 3 filtra
        # `Comissao > 0` -- preservamos. Categoria e SEMPRE "Comissao de
        # Consultor" (hardcoded na vw_DRE block 3).
        comissao = _to_decimal(bronze_row.get("comissao"))
        if comissao <= _ZERO:
            return None
        categoria = "Comissao de Consultor"
        cls = classifier.classify(fonte, categoria)
        if cls is None or not cls.ativo:
            return None
        ua_id = bronze_row.get("unidade_administrativa_id")
        return {
            "ano": bronze_row["ano"],
            "mes": bronze_row["mes"],
            "competencia": _to_date(bronze_row["competencia"]),
            "ordem_grupo": cls.ordem_grupo,
            "grupo_dre": cls.grupo_dre,
            "subgrupo": cls.subgrupo,
            "descricao": categoria,
            "fornecedor": None,
            "fornecedor_documento": None,
            "entidade_id": None,
            "produto_id": None,
            "unidade_administrativa_id": ua_id,
            "fonte": fonte,
            "fonte_integracao": "bitfin",
            "receita": _ZERO,
            "custo": comissao,
            "resultado": -comissao,
            "quantidade": 1,
            "_source_id": _silver_source_id(
                competencia=_to_date(bronze_row["competencia"]),
                grupo_dre=cls.grupo_dre,
                subgrupo=cls.subgrupo,
                descricao=categoria,
                entidade_id=None,
                produto_id=None,
                unidade_administrativa_id=ua_id,
                fonte=fonte,
            ),
        }

    return None


async def _load_latest_bronze_snapshots(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    tipo_origem: str,
    competencia_cutoff: date | None,
) -> list[BitfinRawDre]:
    """Retorna o snapshot mais recente do bronze por competencia >= cutoff.
    Idempotencia: cada (tenant, tipo_origem, competencia) -> 1 snapshot;
    o ordering por `fetched_at DESC` + DISTINCT garante "ultimo fetch"."""
    stmt = (
        select(BitfinRawDre)
        .where(
            BitfinRawDre.tenant_id == tenant_id,
            BitfinRawDre.tipo_origem == tipo_origem,
        )
        .order_by(
            BitfinRawDre.competencia,
            BitfinRawDre.fetched_at.desc(),
        )
        .distinct(BitfinRawDre.competencia)
    )
    if competencia_cutoff is not None:
        stmt = stmt.where(BitfinRawDre.competencia >= competencia_cutoff)
    return list((await db.execute(stmt)).scalars().all())


async def sync_dre_mensal(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Reconstroi `wh_dre_mensal` a partir do bronze (3 fontes) + classifier.

    Sem fetch a MSSQL -- a unica IO externa eh a leitura do bronze e do
    classifier no proprio gr_db. `since` filtra competencias do bronze
    (>= since); None = full rebuild.
    """
    competencia_cutoff = since if since != EPOCH else None
    silver_rows: list[dict] = []

    async with AsyncSessionLocal() as db:
        classifier = await load_dre_classifier(db, tenant_id)

        for tipo_origem in (
            TIPO_ORIGEM_DEMONSTRATIVO,
            TIPO_ORIGEM_PAGAMENTO,
            TIPO_ORIGEM_COMISSAO,
        ):
            snapshots = await _load_latest_bronze_snapshots(
                db,
                tenant_id=tenant_id,
                tipo_origem=tipo_origem,
                competencia_cutoff=competencia_cutoff,
            )
            for snap in snapshots:
                for bronze_row in snap.payload:
                    silver_row = _bronze_row_to_silver(
                        tipo_origem=tipo_origem,
                        bronze_row=bronze_row,
                        classifier=classifier,
                        tenant_id=tenant_id,
                    )
                    if silver_row is None:
                        continue
                    source_id = silver_row.pop("_source_id")
                    silver_rows.append(
                        {
                            "tenant_id": tenant_id,
                            **silver_row,
                            **_provenance(
                                source_id, silver_row, silver_row["competencia"]
                            ),
                        }
                    )

        count = await _bulk_upsert(
            db, DreMensal, silver_rows, ["tenant_id", "source_id"]
        )

    return {
        "table": "wh_dre_mensal",
        "rows": count,
        "classifier_rules": classifier.rule_count,
    }


# ---- Bronze (raw) sync handlers --------------------------------------------
#
# Camada raw do DRE Bitfin (CLAUDE.md §13.2). Cada handler agrupa as linhas
# do fetch por competencia e grava 1 row de bronze por competencia
# (payload = JSONB array de linhas). UQ (tenant, tipo_origem, competencia,
# payload_sha256) dedupe fetch identico via ON CONFLICT DO NOTHING — fetch
# com qualquer alteracao no conteudo gera nova row preservando o historico
# de snapshots.


def _group_rows_by_competencia(
    rows: list[dict], competencia_key: str = "competencia"
) -> dict[date, list[dict]]:
    """Agrupa rows do fetch por competencia (descartando colunas exclusivamente
    de snapshot, como `snapshot_at` do DemonstrativoDeResultado, que mudam
    a cada rebuild da fonte e invalidariam o dedup via sha)."""
    by_comp: dict[date, list[dict]] = {}
    for row in rows:
        comp = row[competencia_key]
        # Conteudo "negocio" — sem snapshot_at (timestamp do rebuild do Bitfin).
        content = {k: v for k, v in row.items() if k != "snapshot_at"}
        by_comp.setdefault(comp, []).append(content)
    return by_comp


async def _upsert_bronze_dre(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    tipo_origem: str,
    competencia: date,
    payload: list[dict],
) -> bool:
    """Grava 1 row de bronze. Retorna True se inseriu, False se ja existia
    (mesmo conteudo -> mesmo sha -> ON CONFLICT DO NOTHING)."""
    sha = sha256_of_row({"items": payload})
    row = {
        "tenant_id": tenant_id,
        "tipo_origem": tipo_origem,
        "competencia": competencia,
        "payload": payload,
        "row_count": len(payload),
        "payload_sha256": sha,
        "fetched_at": datetime.now(UTC),
        "fetched_by_version": ADAPTER_VERSION,
    }
    stmt = pg_insert(BitfinRawDre.__table__).values(row).on_conflict_do_nothing(
        constraint="uq_wh_bitfin_raw_dre"
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


async def sync_bitfin_raw_dre_demonstrativo(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Bronze: snapshot granular de `UNLTD_A7CREDIT.dbo.DemonstrativoDeResultado`.

    Fetch full por competencia (>= since). Bitfin rebuilda o snapshot
    inteiro de cada competencia periodicamente; o dedup via sha garante
    que rebuild sem mudanca de conteudo seja no-op.
    """
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows,
        config,
        config.database_bitfin,
        bitfin.SELECT_DRE_DEMONSTRATIVO_RAW,
        (cutoff,),
    )
    by_comp = _group_rows_by_competencia(rows)
    inserted = 0
    async with AsyncSessionLocal() as db:
        for comp, payload in by_comp.items():
            if await _upsert_bronze_dre(
                db,
                tenant_id=tenant_id,
                tipo_origem=TIPO_ORIGEM_DEMONSTRATIVO,
                competencia=comp,
                payload=payload,
            ):
                inserted += 1
        await db.commit()
    return {
        "table": "wh_bitfin_raw_dre",
        "tipo_origem": TIPO_ORIGEM_DEMONSTRATIVO,
        "competencias_processed": len(by_comp),
        "rows": inserted,
    }


async def sync_bitfin_raw_dre_pagamento(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Bronze: PagamentoOpcaoDePagamento (despesas administrativas, bloco 2
    do DRE). Joins LEFT em PagamentoOperacao (UA) + Fornecedor + Entidade
    (nome/documento). Sem filtro de classificacao — silver decide via
    `wh_dre_classification_rule`.

    Volume tipico: 45-156 linhas/competencia. Fetch full por competencia
    (>= since); dedup via sha do payload garante no-op em re-fetch sem
    mudanca.
    """
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows,
        config,
        config.database_bitfin,
        bitfin.SELECT_DRE_PAGAMENTO_RAW,
        (cutoff,),
    )
    by_comp = _group_rows_by_competencia(rows)
    inserted = 0
    async with AsyncSessionLocal() as db:
        for comp, payload in by_comp.items():
            if await _upsert_bronze_dre(
                db,
                tenant_id=tenant_id,
                tipo_origem=TIPO_ORIGEM_PAGAMENTO,
                competencia=comp,
                payload=payload,
            ):
                inserted += 1
        await db.commit()
    return {
        "table": "wh_bitfin_raw_dre",
        "tipo_origem": TIPO_ORIGEM_PAGAMENTO,
        "competencias_processed": len(by_comp),
        "rows": inserted,
    }


async def sync_bitfin_raw_dre_comissao(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Bronze: ComissaoComercialFechamento (comissoes comerciais, bloco 3
    do DRE). 1 row por (MembroInterno, Ano, Mes). LEFT JOIN MembroInterno
    para UA.

    Vw_DRE original filtra `Comissao > 0`; aqui preservamos todas as rows
    (filtro aplicado no silver mapper).

    Volume: ~3 linhas/competencia.
    """
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows,
        config,
        config.database_bitfin,
        bitfin.SELECT_DRE_COMISSAO_RAW,
        (cutoff,),
    )
    by_comp = _group_rows_by_competencia(rows)
    inserted = 0
    async with AsyncSessionLocal() as db:
        for comp, payload in by_comp.items():
            if await _upsert_bronze_dre(
                db,
                tenant_id=tenant_id,
                tipo_origem=TIPO_ORIGEM_COMISSAO,
                competencia=comp,
                payload=payload,
            ):
                inserted += 1
        await db.commit()
    return {
        "table": "wh_bitfin_raw_dre",
        "tipo_origem": TIPO_ORIGEM_COMISSAO,
        "competencias_processed": len(by_comp),
        "rows": inserted,
    }


async def sync_dim_ua(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Full refresh da dim UA — Bitfin tem poucas linhas (ordem de 3-10)
    e raramente mudam; custo desprezivel."""
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_UNIDADE_ADMINISTRATIVA
    )
    mapped = [_map_dim_ua(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(
            db, DimUnidadeAdministrativa, mapped, ["tenant_id", "source_id"]
        )
    return {"table": "wh_dim_unidade_administrativa", "rows": count}


async def sync_dim_produto(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Full refresh da dim Produto — Bitfin tem ~20 linhas, full table
    sempre. Custo desprezivel."""
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_PRODUTO
    )
    mapped = [_map_dim_produto(r, tenant_id) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(db, DimProduto, mapped, ["tenant_id", "source_id"])
    return {"table": "wh_dim_produto", "rows": count}


async def sync_bitfin_tarifa_catalogo(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Full refresh do catalogo de tarifas (OrganizacaoTarifa) -> dim.

    Vocabulario controlado de tarifas/encargos (Tipo nativo 1=fixa,
    2=variavel) — base do futuro catalogo de receitas operacionais e
    detector de item novo. ~60 linhas; full refresh, custo desprezivel.
    `since` ignorado (catalogo nao e temporal)."""
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_ORGANIZACAO_TARIFA
    )
    now = datetime.now(UTC)
    mapped = [
        {
            "tenant_id": tenant_id,
            "categoria": r["categoria"],
            "descricao": r["descricao"],
            "tipo": int(r["tipo"]),
            "comissionada": bool(r["comissionada"]),
            "fetched_at": now,
            "fetched_by_version": ADAPTER_VERSION,
        }
        for r in rows
    ]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(
            db,
            WhBitfinTarifaCatalogo,
            mapped,
            ["tenant_id", "categoria", "descricao"],
        )
    return {"table": "wh_bitfin_tarifa_catalogo", "rows": count}


async def sync_bitfin_entidade(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Full refresh da dim de entidades (cedentes) referenciadas no DRE.

    Resolve entidade_id -> nome/documento (receita por cedente). Ingere so
    o subconjunto de Entidade que aparece no DemonstrativoDeResultado
    (~90 de ~20k). `since` ignorado."""
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_ENTIDADE_DRE
    )
    now = datetime.now(UTC)
    mapped = [
        {
            "tenant_id": tenant_id,
            "entidade_id": int(r["entidade_id"]),
            "nome": r["nome"],
            "documento": r["documento"],
            "fetched_at": now,
            "fetched_by_version": ADAPTER_VERSION,
        }
        for r in rows
    ]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(
            db, WhBitfinEntidade, mapped, ["tenant_id", "entidade_id"]
        )
    return {"table": "wh_bitfin_entidade", "rows": count}


async def sync_caixa_snapshot(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Snapshot diario do saldo das ContaBancaria-de-UA do tenant.

    `since` ignorado — sempre captura o saldo ATUAL (ContaCorrente.Saldo
    no momento da execucao) e marca `data_snapshot = today`. Multiple
    execucoes de sync no mesmo dia upsertam a mesma row.

    Volume: poucas dezenas de linhas por execucao (uma por conta de UA).
    """
    today = datetime.now(UTC).date()
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, bitfin.SELECT_CAIXA_SNAPSHOT
    )
    mapped = [_map_caixa_snapshot(r, tenant_id, today) for r in rows]
    async with AsyncSessionLocal() as db:
        count = await _bulk_upsert(
            db, CaixaSnapshot, mapped, ["tenant_id", "data_snapshot", "source_id"]
        )
    return {"table": "wh_caixa_snapshot", "rows": count}


# ---- Debentures (snapshot diario da posicao) ----


async def _upsert_bronze_debenture(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    data_referencia: date,
    payload: list[dict],
) -> bool:
    """Grava 1 row de bronze (snapshot diario). Dedup via sha (ON CONFLICT
    DO NOTHING) -- re-run no mesmo dia com mesmo conteudo e no-op."""
    sha = sha256_of_row({"items": payload})
    row = {
        "tenant_id": tenant_id,
        "tipo_origem": TIPO_ORIGEM_VALOR_ATUALIZADO_DIA,
        "data_referencia": data_referencia,
        "payload": payload,
        "row_count": len(payload),
        "payload_sha256": sha,
        "fetched_at": datetime.now(UTC),
        "fetched_by_version": ADAPTER_VERSION,
    }
    stmt = pg_insert(BitfinRawDebenture.__table__).values(row).on_conflict_do_nothing(
        constraint="uq_wh_bitfin_raw_debenture"
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


async def sync_debenture_posicao(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Snapshot diario da posicao de debentures (going-forward).

    `DebentureSubscricao.TotalBruto/Liquido/Valor` sao mantidos pela Bitfin com
    correcao diaria (CDI+spread, por subscricao). Fotografamos o estado atual:
      - bronze `wh_bitfin_raw_debenture` (tipo_origem=valor_atualizado_dia): 1
        row/dia com o payload de todas as subscricoes Integralizadas (auditavel);
      - silver `wh_posicao_debenture_dia`: 1 row por UA para o DIA de hoje
        (origem=snapshot), pl_bruto = SUM(TotalBruto), etc.

    Idempotente: re-run no mesmo dia faz dedup do bronze (sha) e upsert do
    silver (business key tenant/ua/dia). `since` ignorado -- e sempre o estado
    corrente. A Bitfin faz a conta do CDI; nos so capturamos (zero CDI nosso).
    """
    rows = await asyncio.to_thread(
        fetch_rows,
        config,
        config.database_bitfin,
        bitfin.SELECT_DEBENTURE_POSICAO_LIVE,
    )
    today = datetime.now(UTC).date()
    if not rows:
        return {"table": "wh_posicao_debenture_dia", "rows": 0, "uas": 0}

    # Agrega por UA para o silver.
    by_ua: dict[int, dict[str, Any]] = {}
    for r in rows:
        ua = int(r["ua_id"])
        acc = by_ua.setdefault(
            ua,
            {"bruto": _ZERO, "valor": _ZERO, "liquido": _ZERO, "qtd": _ZERO, "n": 0},
        )
        acc["bruto"] += _to_decimal(r["total_bruto"])
        acc["valor"] += _to_decimal(r["valor"])
        acc["liquido"] += _to_decimal(r["total_liquido"])
        acc["qtd"] += _to_decimal(r["quantidade"])
        acc["n"] += 1

    cent = Decimal("0.01")
    async with AsyncSessionLocal() as db:
        await _upsert_bronze_debenture(
            db, tenant_id=tenant_id, data_referencia=today, payload=rows
        )
        n_silver = 0
        for ua, acc in by_ua.items():
            silver_row = {
                "tenant_id": tenant_id,
                "unidade_administrativa_id": ua,
                "data_posicao": today,
                "pl_bruto": acc["bruto"].quantize(cent),
                "pl_valor": acc["valor"].quantize(cent),
                "pl_liquido": acc["liquido"].quantize(cent),
                "quantidade_debentures": acc["qtd"],
                "n_subscricoes": acc["n"],
                "origem": ORIGEM_SNAPSHOT,
                "source_type": SourceType.ERP_BITFIN,
                "source_id": f"{ua}|{today.isoformat()}",
                "ingested_by_version": ADAPTER_VERSION,
                "trust_level": TrustLevel.HIGH,
            }
            stmt = pg_insert(PosicaoDebentureDia.__table__).values(silver_row)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_wh_posicao_debenture_dia",
                set_={
                    "pl_bruto": stmt.excluded.pl_bruto,
                    "pl_valor": stmt.excluded.pl_valor,
                    "pl_liquido": stmt.excluded.pl_liquido,
                    "quantidade_debentures": stmt.excluded.quantidade_debentures,
                    "n_subscricoes": stmt.excluded.n_subscricoes,
                    "origem": stmt.excluded.origem,
                    "ingested_at": func.now(),
                },
            )
            await db.execute(stmt)
            n_silver += 1
        await db.commit()

    return {
        "table": "wh_posicao_debenture_dia",
        "rows": n_silver,
        "uas": len(by_ua),
        "data": today.isoformat(),
    }


# ---- Reconcile (anti-join hard-delete de orfaos) ---------------------------
#
# O ETL e upsert-only (ON CONFLICT DO UPDATE) e NUNCA enxerga delecoes. Quando
# o Bitfin re-edita uma operacao, os titulos antigos sao APAGADOS FISICAMENTE
# na fonte — sem flag/tombstone (verificado 2026-06-05: TituloId some da
# `dbo.Titulo`, sem coluna de status sinalizando). No nosso espelho esses
# titulos ficariam orfaos para sempre, poluindo a "carteira atual" (ex.:
# conciliacao de boletos marcando "So BITFIN" falso para titulos que nem
# existem mais).
#
# O reconcile faz ANTI-JOIN: busca o conjunto VIVO de ids no Bitfin (1 query
# id-only, sem watermark), compara com `source_id` do gr_db e DELETA do gr_db
# (e SO do gr_db) o que nao existe mais na fonte. Filosofia do reconciler
# QiTech (loop estilo Kubernetes): espelho reflete a fonte; quando a fonte
# remove, o espelho remove. O historico auditavel vive fora do espelho
# (decision_log + bronze imutavel), nunca em linha-fantasma (CLAUDE.md §14).

# Tabelas espelho reconciliaveis, em ordem child->parent (defensivo contra
# eventual FK): (model, query id-only, label).
_RECONCILE_TARGETS = [
    (OperacaoItem, bitfin.SELECT_OPERACAO_ITEM_IDS, "wh_operacao_item"),
    (Titulo, bitfin.SELECT_TITULO_IDS, "wh_titulo"),
    (Operacao, bitfin.SELECT_OPERACAO_IDS, "wh_operacao"),
]

# Guarda: se a poda proposta exceder esta fracao do espelho, ABORTA a tabela.
# Delecao legitima do Bitfin e marginal (ordem de 0.5%); uma poda de >25%
# sinaliza fetch parcial/corrompido do conjunto vivo (conexao caindo no meio,
# DB errado), nao delecao real — melhor nao deletar e investigar.
RECONCILE_MAX_DELETE_FRACTION = 0.25

# Intervalo minimo entre reconciles automaticos (gate diario). Anti-join e
# varredura full (~100k ids) — caro demais para rodar a cada micro-sync.
RECONCILE_MIN_INTERVAL_HOURS = 20


async def reconcile_bitfin_mirror(
    tenant_id: UUID, config: BitfinConfig
) -> dict[str, Any]:
    """Hard-delete de orfaos: linhas no espelho que nao existem mais no Bitfin.

    Anti-join por tabela: busca o conjunto VIVO de ids no Bitfin (id-only, sem
    watermark), compara com `source_id` do gr_db e DELETA so a diferenca
    (orfaos). Escopo SEMPRE por `tenant_id` — cada Bitfin (UNLTD_<cliente>)
    mapeia 1 tenant; sem o filtro, o anti-join apagaria titulos de outro tenant
    (que vivem noutro Bitfin, ausentes deste conjunto vivo).

    GUARDAS DURAS (nunca apagar o espelho por engano):
    - conjunto vivo VAZIO (falha de conexao / DB errado) -> aborta a tabela
      (um set vazio tornaria TODO o espelho orfao);
    - poda > RECONCILE_MAX_DELETE_FRACTION do espelho -> aborta a tabela
      (sinaliza fetch parcial, nao delecao legitima).

    NUNCA toca o Bitfin: la e SELECT id-only; o DELETE acontece so no gr_db.
    """
    results: list[dict[str, Any]] = []
    async with AsyncSessionLocal() as db:
        for model, query, label in _RECONCILE_TARGETS:
            live_rows = await asyncio.to_thread(
                fetch_rows, config, config.database_bitfin, query
            )
            # source_id no espelho e TEXT (str(id) no _provenance) — comparamos
            # como string para casar o conjunto vivo (ints do Bitfin).
            live_ids = {str(r["source_id"]) for r in live_rows}
            if not live_ids:
                results.append(
                    {"table": label, "deleted": 0, "skipped_reason": "live_set_empty"}
                )
                continue

            wh_ids = set(
                (
                    await db.execute(
                        select(model.source_id).where(model.tenant_id == tenant_id)
                    )
                )
                .scalars()
                .all()
            )
            phantoms = wh_ids - live_ids
            wh_count = len(wh_ids)
            if wh_count and len(phantoms) / wh_count > RECONCILE_MAX_DELETE_FRACTION:
                results.append(
                    {
                        "table": label,
                        "deleted": 0,
                        "skipped_reason": "exceeds_safety_cap",
                        "live_bitfin": len(live_ids),
                        "wh_before": wh_count,
                        "phantoms": len(phantoms),
                    }
                )
                continue

            deleted = 0
            for chunk in _chunked(list(phantoms), CHUNK_SIZE):
                res = await db.execute(
                    delete(model).where(
                        model.tenant_id == tenant_id,
                        model.source_id.in_(chunk),
                    )
                )
                deleted += res.rowcount or 0
            await db.commit()
            results.append(
                {
                    "table": label,
                    "live_bitfin": len(live_ids),
                    "wh_before": wh_count,
                    "phantoms": len(phantoms),
                    "deleted": deleted,
                }
            )
    return {
        "reconcile": results,
        "total_deleted": sum(r.get("deleted", 0) for r in results),
    }


async def sync_reconcile_mirror(
    tenant_id: UUID,
    config: BitfinConfig,
    since: date | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Passo de pipeline: reconcile com gate diario + entrada propria no
    decision_log (auditoria §14.6 da poda).

    `force=True` ignora o gate — usado pelo oneshot de limpeza inicial. `since`
    ignorado (reconcile e sempre full-set; nao ha como detectar delecao
    incrementalmente).
    """
    if not force:
        async with AsyncSessionLocal() as db:
            last = await last_sync_at(
                db,
                tenant_id,
                rule_or_model="bitfin_reconcile",
                endpoint_name="bitfin.reconcile",
            )
        if last is not None and (datetime.now(UTC) - last) < timedelta(
            hours=RECONCILE_MIN_INTERVAL_HOURS
        ):
            return {
                "table": "reconcile",
                "skipped_reason": "not_due",
                "last_reconcile": last.isoformat(),
            }

    result = await reconcile_bitfin_mirror(tenant_id, config)

    async with AsyncSessionLocal() as db:
        db.add(
            DecisionLog(
                tenant_id=tenant_id,
                decision_type=DecisionType.SYNC,
                inputs_ref={"force": force},
                rule_or_model="bitfin_reconcile",
                rule_or_model_version=ADAPTER_VERSION,
                endpoint_name="bitfin.reconcile",
                output=result,
                explanation="OK",
                triggered_by="script:reconcile_oneshot" if force else "system:scheduler",
            )
        )
        await db.commit()

    return {"table": "reconcile", **result}


# ---- Master orchestrator ----

SYNC_PIPELINE = [
    sync_dim_ua,
    sync_dim_produto,
    sync_bitfin_tarifa_catalogo,
    sync_bitfin_entidade,
    # `sync_titulo_snapshot` ainda depende de ANALYTICS.dbo.elig_snapshot_titulo
    # -- followup separado pra eliminar (CLAUDE.md secao 13: multi-tenant
    # absoluto). Mantemos no pipeline para A7 Credit hoje; quando o tenant
    # nao tiver ANALYTICS configurado, o sync vai falhar com 'database not
    # configured' e seguir (sync_all captura por try/except).
    sync_titulo_snapshot,
    sync_operacao,
    sync_operacao_item,
    sync_titulo,
    # DRE: bronze das 3 fontes em UNLTD_<X> -> silver via classifier do gr_db.
    # Zero dependencia de ANALYTICS aqui (v2.0.0).
    sync_bitfin_raw_dre_demonstrativo,
    sync_bitfin_raw_dre_pagamento,
    sync_bitfin_raw_dre_comissao,
    sync_dre_mensal,
    sync_caixa_snapshot,
    # Snapshot diario da posicao de debentures (going-forward; Bitfin faz o
    # CDI, nos capturamos). Alimenta o denominador do ROA bruto da DRE.
    sync_debenture_posicao,
    # Catalogo de receitas operacionais caixa-fiel (wh_receita_operacional,
    # dirigido por wh_bitfin_receita_stream). Roda apos sync_titulo (mesma
    # fonte) — leitura direta do MSSQL, sem dependencia das tabelas acima.
    sync_receita_mora_liquidacao,
    sync_receita_grafica,
    sync_receita_recompra,
    sync_receita_operacao,
    # Reconcile (anti-join hard-delete de orfaos). Ultimo passo: roda DEPOIS
    # dos upserts (espelho ja com os dados frescos) e tem gate diario interno
    # — a varredura full so dispara 1x/dia, demais ticks viram no-op barato.
    sync_reconcile_mirror,
]


async def sync_all(
    tenant_id: UUID,
    config: BitfinConfig,
    since: date | None = None,
    *,
    triggered_by: str = "system:scheduler",
    endpoint_name: str | None = None,
) -> dict[str, Any]:
    """Executa todas as syncs em sequencia + registra no decision_log.

    `triggered_by` identifica quem disparou o ciclo (scheduler automatico,
    bootstrap CLI, ou usuario via API: "user:<uuid>").

    `endpoint_name`: opcional. Quando o caller e o `adapter_sync_endpoint`
    novo (per-endpoint), passa "bitfin.full_sync" para que a entry de
    decision_log carimbe a dimensao endpoint. Caller legacy nao passa,
    e a entry fica com `endpoint_name=None` (compativel com modo legacy).
    """
    started_at = datetime.now(UTC)
    t0 = time.monotonic()
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for sync_fn in SYNC_PIPELINE:
        try:
            result = await sync_fn(tenant_id, config, since=since)
            results.append(result)
        except Exception as e:
            errors.append(f"{sync_fn.__name__}: {type(e).__name__}: {e}")

    elapsed = time.monotonic() - t0
    summary = {
        "adapter_version": ADAPTER_VERSION,
        "started_at": started_at.isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "tables": results,
        "errors": errors,
        "since": since.isoformat() if since else None,
    }

    # Log no decision_log (append-only)
    async with AsyncSessionLocal() as db:
        db.add(
            DecisionLog(
                tenant_id=tenant_id,
                decision_type=DecisionType.SYNC,
                inputs_ref={"since": summary["since"]},
                rule_or_model="bitfin_adapter",
                rule_or_model_version=ADAPTER_VERSION,
                endpoint_name=endpoint_name,
                output=summary,
                explanation=("OK" if not errors else f"{len(errors)} erro(s): {errors}"),
                triggered_by=triggered_by,
            )
        )
        await db.commit()

    return summary
