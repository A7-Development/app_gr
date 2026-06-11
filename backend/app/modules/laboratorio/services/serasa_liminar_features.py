"""Extractor de features da tese de liminar (lab_serasa_pj_liminar_feature).

Le APENAS do silver (CLAUDE.md 13.2.1) + classificacao publica da regra
serasa_liminar (via `integracoes/public.py`). Reconstruivel do zero —
re-rodar substitui as linhas (UPSERT por tenant_id+raw_id) e atualiza
`extractor_version`.

Labels (`label_liminar`) NAO sao calculados aqui — sao ground truth
externo (flag Liminar do Bitfin / curadoria), preenchidos por fora via
`bitfin_consulta_id` da raw. Manter label separado da inferencia
(`suspeita_liminar`) e o que permite medir a regra contra a realidade.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.public import (
    classify_serasa_negative_summary_message,
)
from app.warehouse.serasa_pj_consulta import SerasaPjConsulta
from app.warehouse.serasa_pj_inquiry_anterior import SerasaPjInquiryAnterior
from app.warehouse.serasa_pj_inquiry_mensal import SerasaPjInquiryMensal
from app.warehouse.serasa_pj_liminar_feature import SerasaPjLiminarFeature
from app.warehouse.serasa_pj_pagamento_bucket import SerasaPjPagamentoBucket
from app.warehouse.serasa_pj_raw_relatorio import SerasaPjRawRelatorio

EXTRACTOR_VERSION = "liminar_features_v1"

_NEG_FIELDS = (
    "count_pefin",
    "count_refin",
    "count_protesto",
    "count_cheque",
    "count_falencias",
    "count_acoes_judiciais",
)


def compute_longitudinal(
    atual: dict[str, int],
    anterior: dict[str, int] | None,
) -> dict[str, Any]:
    """Deltas vs consulta anterior do mesmo CNPJ (nucleo puro).

    `zerou_em_bloco` = >= 2 categorias que estavam > 0 cairam a 0
    simultaneamente — assinatura de liminar (pagamento real e gradual e
    por categoria; supressao judicial derruba tudo de uma vez).
    """
    if anterior is None:
        return {
            "delta_negativos": None,
            "categorias_zeradas": None,
            "zerou_em_bloco": False,
        }
    delta = sum(atual[f] for f in _NEG_FIELDS) - sum(
        anterior[f] for f in _NEG_FIELDS
    )
    zeradas = sum(
        1 for f in _NEG_FIELDS if anterior[f] > 0 and atual[f] == 0
    )
    return {
        "delta_negativos": delta,
        "categorias_zeradas": zeradas,
        "zerou_em_bloco": zeradas >= 2,
    }


def idade_empresa_anos(
    data_constituicao: Any, consulted_at: datetime
) -> float | None:
    if data_constituicao is None:
        return None
    delta_dias = (consulted_at.date() - data_constituicao).days
    return round(delta_dias / 365.25, 1)


async def build_features(db: AsyncSession, *, tenant_id: UUID) -> int:
    """(Re)constroi as features de todas as consultas do tenant.

    Returns: numero de linhas upsertadas.
    """
    consultas = (
        (
            await db.execute(
                select(SerasaPjConsulta)
                .where(SerasaPjConsulta.tenant_id == tenant_id)
                .order_by(
                    SerasaPjConsulta.cnpj, SerasaPjConsulta.consulted_at
                )
            )
        )
        .scalars()
        .all()
    )
    if not consultas:
        return 0

    origem_por_raw = dict(
        (
            await db.execute(
                select(
                    SerasaPjRawRelatorio.id,
                    SerasaPjRawRelatorio.bitfin_consulta_id,
                ).where(SerasaPjRawRelatorio.tenant_id == tenant_id)
            )
        ).all()
    )

    # Agregados das filhas, 1 query por tabela (group by consulta_id).
    inquiries_12m = dict(
        (
            await db.execute(
                select(
                    SerasaPjInquiryMensal.consulta_id,
                    func.sum(SerasaPjInquiryMensal.occurrences),
                )
                .where(SerasaPjInquiryMensal.tenant_id == tenant_id)
                .group_by(SerasaPjInquiryMensal.consulta_id)
            )
        ).all()
    )
    inquiry_rows = (
        await db.execute(
            select(
                SerasaPjInquiryAnterior.consulta_id,
                SerasaPjInquiryAnterior.company_document_id,
                SerasaPjInquiryAnterior.occurrence_date,
            ).where(SerasaPjInquiryAnterior.tenant_id == tenant_id)
        )
    ).all()
    tem_buckets = {
        cid
        for (cid,) in (
            await db.execute(
                select(SerasaPjPagamentoBucket.consulta_id)
                .where(SerasaPjPagamentoBucket.tenant_id == tenant_id)
                .distinct()
            )
        ).all()
    }

    inquiries_por_consulta: dict[UUID, list[tuple[Any, Any]]] = {}
    for cid, doc, occ in inquiry_rows:
        inquiries_por_consulta.setdefault(cid, []).append((doc, occ))

    upserted = 0
    anterior_por_cnpj: dict[str, SerasaPjConsulta] = {}
    for c in consultas:
        anterior = anterior_por_cnpj.get(c.cnpj)
        anterior_por_cnpj[c.cnpj] = c

        atual_counts = {f: int(getattr(c, f) or 0) for f in _NEG_FIELDS}
        anterior_counts = (
            {f: int(getattr(anterior, f) or 0) for f in _NEG_FIELDS}
            if anterior is not None
            else None
        )
        longitudinal = compute_longitudinal(atual_counts, anterior_counts)

        inqs = inquiries_por_consulta.get(c.id, [])
        janela_90d = c.consulted_at.date() - timedelta(days=90)
        inquiries_90d = sum(
            1 for _, occ in inqs if occ is not None and occ >= janela_90d
        )
        consultantes = len({doc for doc, _ in inqs if doc})

        row: dict[str, Any] = {
            "tenant_id": tenant_id,
            "raw_id": c.raw_id,
            "consulta_id": c.id,
            "cnpj": c.cnpj,
            "consulted_at": c.consulted_at,
            "origem": (
                "bitfin_relay"
                if origem_por_raw.get(c.raw_id) is not None
                else "direta"
            ),
            "msg_class": classify_serasa_negative_summary_message(
                c.negative_summary_message
            ),
            "suspeita_liminar": bool(c.suspeita_liminar),
            **atual_counts,
            "valor_total_restricoes": c.valor_total_restricoes,
            "inquiries_90d": inquiries_90d if inqs else None,
            "inquiries_12m": (
                int(inquiries_12m[c.id])
                if c.id in inquiries_12m
                else None
            ),
            "consultantes_distintos": consultantes if inqs else None,
            "tem_payment_history": c.id in tem_buckets,
            "idade_empresa_anos": idade_empresa_anos(
                c.data_constituicao, c.consulted_at
            ),
            "rj_no_nome": "RECUPERACAO JUDICIAL"
            in (c.razao_social or "").upper(),
            "prev_raw_id": anterior.raw_id if anterior else None,
            "dias_desde_anterior": (
                (c.consulted_at - anterior.consulted_at).days
                if anterior
                else None
            ),
            **longitudinal,
            "extractor_version": EXTRACTOR_VERSION,
        }

        table = SerasaPjLiminarFeature.__table__
        stmt = pg_insert(table).values(row)
        update_cols = {
            col.name: stmt.excluded[col.name]
            for col in table.columns
            if col.name
            not in {"id", "tenant_id", "raw_id", "built_at", "label_liminar"}
            and col.name in row
        }
        # label_liminar fora do update de proposito: curadoria externa
        # sobrevive a re-extracao.
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["tenant_id", "raw_id"], set_=update_cols
            )
        )
        upserted += 1

    return upserted
