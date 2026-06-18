"""Mapper (BDC processes) -> silver de processos judiciais (4 tabelas).

    upsert_pj_processos()        -> wh_pj_processo (UPSERT por numero, sem apagar)
                                  + wh_pj_processo_parte (replace por processo)
                                  + wh_pj_processo_andamento (INCREMENTA, dedupe)
    upsert_pj_processo_resumo()  -> wh_pj_processo_resumo (UPSERT por cnpj)

Reconciliacao (decisao Ricardo): re-consulta INCREMENTA, nao subscreve —
processo via upsert (atualiza o que muda, marca last_seen_at, nunca apaga);
andamentos acumulam (ON CONFLICT DO NOTHING) pra nao perder historico de bens.
Nao commita — o caller controla a transacao.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.processos import (
    ProcessoFields,
    ProcessoResumoFields,
)
from app.warehouse.pj_processo import (
    PjProcesso,
    PjProcessoAndamento,
    PjProcessoParte,
    PjProcessoResumo,
)


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


# Campos mutaveis do processo atualizados na re-consulta (upsert).
_PROC_UPDATE = (
    "raw_id", "unidade_administrativa_id", "tipo", "assunto", "assunto_cnj",
    "assunto_cnj_amplo", "tribunal", "instancia", "area", "comarca",
    "orgao_julgador", "uf", "status", "encerrado", "valor", "polaridade_alvo",
    "is_execucao", "num_partes", "num_atualizacoes", "idade_dias",
    "data_redistribuicao", "data_notice", "data_last_movement", "data_last_update",
    "source_id", "source_updated_at", "ingested_by_version", "hash_origem",
    "trust_level", "last_seen_at",
)


async def upsert_pj_processos(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj: str,
    processos: list[ProcessoFields],
    raw_id: UUID | None,
    hash_origem: str | None,
    ingested_by_version: str,
    unidade_administrativa_id: UUID | None = None,
    source_type: SourceType = SourceType.BUREAU_BDC,
) -> tuple[int, int, int]:
    """Upsert processos + replace partes + incrementa andamentos.

    Retorna (n_processos, n_partes, n_andamentos_novos).
    """
    cnpj_digits = _digits(cnpj)
    n_proc = n_partes = 0
    andamento_rows: list[dict[str, Any]] = []
    parte_rows: list[dict[str, Any]] = []
    numeros = [p.numero for p in processos]

    # Partes: replace por processo -> apaga as desta fonte/cnpj e reinsere.
    if numeros:
        await db.execute(
            delete(PjProcessoParte).where(
                PjProcessoParte.tenant_id == tenant_id,
                PjProcessoParte.cnpj == cnpj_digits,
                PjProcessoParte.source_type == source_type,
                PjProcessoParte.numero.in_(numeros),
            )
        )

    for p in processos:
        n_proc += 1
        values: dict[str, Any] = {
            "tenant_id": tenant_id,
            "unidade_administrativa_id": unidade_administrativa_id,
            "raw_id": raw_id,
            "cnpj": cnpj_digits,
            "numero": p.numero,
            "tipo": p.tipo,
            "assunto": p.assunto,
            "assunto_cnj": p.assunto_cnj,
            "assunto_cnj_amplo": p.assunto_cnj_amplo,
            "tribunal": p.tribunal,
            "instancia": p.instancia,
            "area": p.area,
            "comarca": p.comarca,
            "orgao_julgador": p.orgao_julgador,
            "uf": p.uf,
            "status": p.status,
            "encerrado": p.encerrado,
            "valor": p.valor,
            "polaridade_alvo": p.polaridade_alvo,
            "is_execucao": p.is_execucao,
            "num_partes": p.num_partes,
            "num_atualizacoes": p.num_atualizacoes,
            "idade_dias": p.idade_dias,
            "data_redistribuicao": p.data_redistribuicao,
            "data_notice": p.data_notice,
            "data_last_movement": p.data_last_movement,
            "data_last_update": p.data_last_update,
            "source_type": source_type,
            "source_id": f"{cnpj_digits}:{p.numero}"[:255],
            "source_updated_at": p.source_updated_at,
            "ingested_by_version": ingested_by_version,
            "hash_origem": hash_origem,
            "trust_level": TrustLevel.HIGH,
            "last_seen_at": func.now(),
        }
        stmt = pg_insert(PjProcesso).values(**values)
        update_set = {c: stmt.excluded[c] for c in _PROC_UPDATE}
        update_set["ingested_at"] = func.now()
        stmt = stmt.on_conflict_do_update(
            constraint="uq_wh_pj_processo", set_=update_set
        )
        await db.execute(stmt)

        for pt in p.partes:
            n_partes += 1
            parte_rows.append(
                {
                    "tenant_id": tenant_id,
                    "unidade_administrativa_id": unidade_administrativa_id,
                    "raw_id": raw_id,
                    "cnpj": cnpj_digits,
                    "numero": p.numero,
                    "polaridade": pt.polaridade,
                    "tipo_parte": pt.tipo_parte,
                    "ativa": pt.ativa,
                    "nome": pt.nome,
                    "doc": pt.doc,
                    "source_type": source_type,
                    "source_id": f"{cnpj_digits}:{p.numero}:{pt.doc or pt.nome or '?'}"[:255],
                    "source_updated_at": None,
                    "ingested_by_version": ingested_by_version,
                    "hash_origem": hash_origem,
                    "trust_level": TrustLevel.HIGH,
                }
            )

        for a in p.andamentos:
            andamento_rows.append(
                {
                    "tenant_id": tenant_id,
                    "unidade_administrativa_id": unidade_administrativa_id,
                    "raw_id": raw_id,
                    "cnpj": cnpj_digits,
                    "numero": p.numero,
                    "data": a.data,
                    "conteudo": a.conteudo,
                    "conteudo_hash": a.conteudo_hash,
                    "evento_patrimonial": a.evento_patrimonial,
                    "source_type": source_type,
                    "source_id": f"{cnpj_digits}:{p.numero}:{a.conteudo_hash[:16]}"[:255],
                    "source_updated_at": a.data,
                    "ingested_by_version": ingested_by_version,
                    "hash_origem": hash_origem,
                    "trust_level": TrustLevel.HIGH,
                }
            )

    # Chunk: asyncpg limita 32767 params/statement (~16 cols -> teto ~2000 rows).
    _chunk = 1000
    for i in range(0, len(parte_rows), _chunk):
        await db.execute(pg_insert(PjProcessoParte).values(parte_rows[i : i + _chunk]))

    n_novos = 0
    for i in range(0, len(andamento_rows), _chunk):
        stmt = (
            pg_insert(PjProcessoAndamento)
            .values(andamento_rows[i : i + _chunk])
            .on_conflict_do_nothing(constraint="uq_wh_pj_processo_andamento")
            .returning(PjProcessoAndamento.id)
        )
        n_novos += len((await db.execute(stmt)).all())

    return n_proc, n_partes, n_novos


async def upsert_pj_processo_resumo(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj: str,
    resumo: ProcessoResumoFields,
    raw_id: UUID | None,
    hash_origem: str | None,
    ingested_by_version: str,
    unidade_administrativa_id: UUID | None = None,
    source_type: SourceType = SourceType.BUREAU_BDC,
) -> None:
    """Upsert do rollup de processos (por tenant+cnpj+source_type)."""
    cnpj_digits = _digits(cnpj)
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "unidade_administrativa_id": unidade_administrativa_id,
        "raw_id": raw_id,
        "cnpj": cnpj_digits,
        "qtd_total": resumo.qtd_total,
        "qtd_ativos": resumo.qtd_ativos,
        "qtd_encerrados": resumo.qtd_encerrados,
        "por_area": resumo.por_area,
        "qtd_como_reu": resumo.qtd_como_reu,
        "qtd_como_autor": resumo.qtd_como_autor,
        "qtd_execucoes_contra": resumo.qtd_execucoes_contra,
        "credores_executando": resumo.credores_executando,
        "qtd_recuperacao_falencia": resumo.qtd_recuperacao_falencia,
        "valor_total_informado": resumo.valor_total_informado,
        "last_30d": resumo.last_30d,
        "last_90d": resumo.last_90d,
        "last_365d": resumo.last_365d,
        "primeira_data": resumo.primeira_data,
        "ultima_data": resumo.ultima_data,
        "source_type": source_type,
        "source_id": cnpj_digits,
        "source_updated_at": None,  # derivado -> idade = consulta
        "ingested_by_version": ingested_by_version,
        "hash_origem": hash_origem,
        "trust_level": TrustLevel.HIGH,
    }
    _cols = tuple(k for k in values if k not in ("tenant_id", "cnpj", "source_type"))
    stmt = pg_insert(PjProcessoResumo).values(**values)
    update_set = {c: stmt.excluded[c] for c in _cols}
    update_set["ingested_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        constraint="uq_wh_pj_processo_resumo", set_=update_set
    )
    await db.execute(stmt)
