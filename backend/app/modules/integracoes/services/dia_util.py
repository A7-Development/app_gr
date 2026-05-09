"""Service de leitura da tabela `wh_dia_util_qitech`.

Resposta a pergunta: "para esta UA, em quais datas a QiTech publicou
snapshot que permite analise diaria?". Resultado consumido pelo Calendar
da pagina cota-sub (e por outras rotas que precisam filtrar datas
analisaveis).

Decisao 2026-05-07: na Fase A so trabalhamos com `status='completo'`. Se
no futuro evoluir para 'parcial' (ETL captura parcial), o callsite passa
`status_in=("completo", "parcial")` explicitamente.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse.dia_util_qitech import DiaUtilQitech


async def listar_datas_disponiveis(
    db:        AsyncSession,
    tenant_id: UUID,
    ua_id:     UUID,
    *,
    status_in: tuple[str, ...] = ("completo",),
    limit:     int | None = None,
) -> list[date]:
    """Lista as datas em que a QiTech publicou snapshot da UA, ordenadas desc.

    Args:
        db: sessao async (escopo: request).
        tenant_id: tenant da UA (escopo enforced via WHERE — multi-tenant
            §10).
        ua_id: unidade administrativa (fundo).
        status_in: tupla de status aceitos. Default ('completo',). Passar
            ('completo', 'parcial') para incluir dias com captura parcial
            quando essa diferenciacao virar relevante (Fase B).
        limit: opcional, limita ao N datas mais recentes. Util para
            payloads pequenos quando o historico for grande.

    Returns:
        Lista de date ordenada desc (mais recente primeiro). Vazia se a UA
        nao tem snapshot publicado em nenhuma data.
    """
    stmt = (
        select(DiaUtilQitech.data_posicao)
        .where(
            DiaUtilQitech.tenant_id == tenant_id,
            DiaUtilQitech.unidade_administrativa_id == ua_id,
            DiaUtilQitech.status.in_(status_in),
        )
        .order_by(DiaUtilQitech.data_posicao.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def dia_util_anterior_qitech(
    db:        AsyncSession,
    tenant_id: UUID,
    ua_id:     UUID,
    data_d0:   date,
    *,
    status_in: tuple[str, ...] = ("completo",),
) -> date:
    """Retorna a maior data < data_d0 em `wh_dia_util_qitech` para esta UA.

    Substitui a logica simplista `data_d0 - 1 dia + recua sabado/domingo`
    que vivia em `controladoria/services/balanco.py::_dia_util_anterior`.
    Aquela funcao nao tratava feriados nem falhas de ETL — D-1 podia cair
    em uma data sem snapshot publicado, distorcendo a comparacao.

    Esta funcao usa a mesma fonte de verdade que o Calendar do frontend
    (`wh_dia_util_qitech`), garantindo simetria: se uma data esta liberada
    no Calendar, o D-1 calculado para o dia seguinte vai ser exatamente ela.

    Args:
        db: sessao async.
        tenant_id: tenant da UA (multi-tenant §10).
        ua_id: unidade administrativa (fundo).
        data_d0: data alvo. A funcao retorna o maior dia anterior a esta.
        status_in: status aceitos. Default ('completo',). Manter sinc com
            `listar_datas_disponiveis` para evitar divergencia
            Calendar/backend.

    Returns:
        Data do dia util anterior efetivo (com snapshot QiTech publicado).

    Raises:
        ValueError: se nao houver nenhuma data < data_d0 com snapshot
            publicado para esta UA. Caller deve traduzir para HTTP 404.
    """
    stmt = (
        select(func.max(DiaUtilQitech.data_posicao))
        .where(
            DiaUtilQitech.tenant_id == tenant_id,
            DiaUtilQitech.unidade_administrativa_id == ua_id,
            DiaUtilQitech.data_posicao < data_d0,
            DiaUtilQitech.status.in_(status_in),
        )
    )
    result = await db.execute(stmt)
    d_d1 = result.scalar()
    if d_d1 is None:
        raise ValueError(
            f"Nao ha dia util anterior com snapshot QiTech para UA {ua_id} "
            f"antes de {data_d0.isoformat()}."
        )
    return d_d1
