"""Controladoria · Estoque Carteira — service de agregacao do bundle.

Le APENAS de silver (`wh_estoque_recebivel`, CLAUDE.md §13.2.1) e calcula
KPIs + breakdowns no SQL — escala pra carteira com 100k+ titulos sem mover
tudo pra Python.

Defaults:
    - `data_referencia=None` → resolve para max(data_referencia) no escopo
      (tenant + fundo opcional). Sem isso, primeiro acesso a pagina precisaria
      adivinhar a data, e o usuario nao tem como saber qual e a ultima
      sincronizada antes de abrir a tela.
    - `fundo_id=None` → escopo = tenant inteiro (todas as UAs). Tipico
      tenant FIDC tem 1 UA fundo, entao essa default e razoavel.

Top-N + "Outros":
    Para sacados e originadores, o servico retorna top 10 + 1 row sintetica
    "Outros" agregando a cauda. Isso evita o frontend ter que decidir o que
    fazer com 800 cedentes — e tambem evita download desnecessario de cauda
    longa.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.models.unidade_administrativa import (
    UnidadeAdministrativa,
)
from app.modules.controladoria.services import reports as reports_service
from app.modules.integracoes.public import get_report_spec
from app.warehouse.estoque_recebivel import EstoqueRecebivel

_SLUG = "qitech-estoque-carteira"
_TOP_N = 10


async def get_carteira_bundle(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_id: UUID | None,
    data_referencia: date | None,
) -> dict[str, Any]:
    """Bundle agregado da carteira FIDC numa data de referencia.

    Resolve `fundo_id` → `fundo_doc` via `cadastros_unidade_administrativa.cnpj`.
    Quando o UA nao tem CNPJ cadastrado, o filtro de fundo e silenciosamente
    descartado e o escopo vira "tenant inteiro" (mesmo comportamento da Phase 1
    em `services/reports.py`).

    Quando nao ha row em `wh_estoque_recebivel` no escopo, retorna bundle
    com `is_empty=True` e KPIs zerados — frontend mostra EmptyState.
    """
    # 1. Resolve fundo_id -> cnpj_fundo (digits-only).
    cnpj_fundo: str | None = None
    if fundo_id is not None:
        cnpj_fundo = await _resolve_fundo_doc(
            db, tenant_id=tenant_id, fundo_id=fundo_id
        )

    # 2. Default data_referencia = ultima disponivel no escopo.
    if data_referencia is None:
        data_referencia = await _resolve_max_data_referencia(
            db, tenant_id=tenant_id, cnpj_fundo=cnpj_fundo
        )

    # 3. Proveniencia (sempre, mesmo no caso vazio — frontend mostra
    # "ultima sincronizacao" no footer mesmo quando ainda nao chegou dado
    # do fundo X).
    spec = get_report_spec(_SLUG)
    if spec is None:
        # Slug deveria existir — bug se chegou aqui. Falha alta.
        raise RuntimeError(
            f"slug {_SLUG!r} nao encontrado no report_catalog — bug de seed"
        )
    proveniencia = await reports_service.get_report_provenance(
        db, spec=spec, tenant_id=tenant_id
    )

    if data_referencia is None:
        # Sem dado nenhum no escopo.
        return _empty_bundle(
            data_referencia=None,
            fundo_doc=cnpj_fundo,
            fundo_nome=None,
            provenance=proveniencia,
        )

    # 4. Fundo metadata (nome) — primeiro registro do escopo.
    fundo_meta = await _fetch_fundo_metadata(
        db,
        tenant_id=tenant_id,
        cnpj_fundo=cnpj_fundo,
        data_referencia=data_referencia,
    )

    # 5. KPIs + top-5 concentracao numa unica passada onde possivel.
    where_predicates = _scope_predicates(
        tenant_id=tenant_id,
        cnpj_fundo=cnpj_fundo,
        data_referencia=data_referencia,
    )

    kpis_row = await _aggregate_kpis(db, where_predicates=where_predicates)
    nominal_total = Decimal(kpis_row["nominal"])
    if nominal_total <= 0:
        return _empty_bundle(
            data_referencia=data_referencia,
            fundo_doc=fundo_meta.get("fundo_doc") or cnpj_fundo,
            fundo_nome=fundo_meta.get("fundo_nome"),
            provenance=proveniencia,
        )

    pdd_total = Decimal(kpis_row["pdd"])
    vencido_nominal = Decimal(kpis_row["vencido_nominal"])
    qtd_titulos = int(kpis_row["qtd"])
    presente_total = Decimal(kpis_row["presente"])
    aquisicao_total = Decimal(kpis_row["aquisicao"])

    pct_vencido = float(vencido_nominal / nominal_total * Decimal("100"))
    pdd_medio_pct = float(pdd_total / nominal_total * Decimal("100"))

    # Concentracao top1/top5 por sacado e por cedente — 4 numeros, computados
    # em paralelo conceitual (cada um e uma subquery).
    top1_sac, top5_sac = await _topn_sums_grouped(
        db,
        where_predicates=where_predicates,
        chave_col=EstoqueRecebivel.sacado_doc,
    )
    top1_ced, top5_ced = await _topn_sums_grouped(
        db,
        where_predicates=where_predicates,
        chave_col=EstoqueRecebivel.cedente_doc,
    )
    concentracao_top1_sac = float(top1_sac / nominal_total * Decimal("100"))
    concentracao_top5_sac = float(top5_sac / nominal_total * Decimal("100"))
    concentracao_top1_ced = float(top1_ced / nominal_total * Decimal("100"))
    concentracao_top5_ced = float(top5_ced / nominal_total * Decimal("100"))

    # 6. Breakdowns.
    por_faixa_pdd = await _breakdown_por_faixa_pdd(
        db, where_predicates=where_predicates, total=nominal_total
    )
    por_situacao = await _breakdown_por_situacao(
        db, where_predicates=where_predicates, total=nominal_total
    )
    por_coobrigacao = await _breakdown_por_coobrigacao(
        db, where_predicates=where_predicates, total=nominal_total
    )
    por_produto = await _breakdown_por_produto(
        db, where_predicates=where_predicates, total=nominal_total
    )
    top_sacados = await _breakdown_top_n_with_outros(
        db,
        where_predicates=where_predicates,
        total=nominal_total,
        chave_col=EstoqueRecebivel.sacado_doc,
        nome_col=EstoqueRecebivel.sacado_nome,
        top_n=_TOP_N,
    )
    top_cedentes = await _breakdown_top_n_with_outros(
        db,
        where_predicates=where_predicates,
        total=nominal_total,
        chave_col=EstoqueRecebivel.cedente_doc,
        nome_col=EstoqueRecebivel.cedente_nome,
        top_n=_TOP_N,
    )
    por_originador = await _breakdown_top_n_with_outros(
        db,
        where_predicates=where_predicates,
        total=nominal_total,
        chave_col=EstoqueRecebivel.originador_doc,
        nome_col=EstoqueRecebivel.originador_nome,
        top_n=_TOP_N,
    )

    return {
        "data_referencia": data_referencia,
        "fundo_doc": fundo_meta.get("fundo_doc") or cnpj_fundo,
        "fundo_nome": fundo_meta.get("fundo_nome"),
        "kpis": {
            "valor_nominal_total": nominal_total,
            "valor_presente_total": presente_total,
            "valor_aquisicao_total": aquisicao_total,
            "valor_pdd_total": pdd_total,
            "qtd_titulos": qtd_titulos,
            "pct_vencido": pct_vencido,
            "pdd_medio_pct": pdd_medio_pct,
            "concentracao_top1_sacados_pct": concentracao_top1_sac,
            "concentracao_top5_sacados_pct": concentracao_top5_sac,
            "concentracao_top1_cedentes_pct": concentracao_top1_ced,
            "concentracao_top5_cedentes_pct": concentracao_top5_ced,
        },
        "por_faixa_pdd": por_faixa_pdd,
        "top_sacados": top_sacados,
        "top_cedentes": top_cedentes,
        "por_originador": por_originador,
        "por_produto": por_produto,
        "por_situacao": por_situacao,
        "por_coobrigacao": por_coobrigacao,
        "provenance": proveniencia,
        "is_empty": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internos
# ─────────────────────────────────────────────────────────────────────────────


def _scope_predicates(
    *,
    tenant_id: UUID,
    cnpj_fundo: str | None,
    data_referencia: date,
) -> list[Any]:
    """WHERE base de todas as queries. tenant_id obrigatorio (§10)."""
    predicates: list[Any] = [
        EstoqueRecebivel.tenant_id == tenant_id,
        EstoqueRecebivel.data_referencia == data_referencia,
    ]
    if cnpj_fundo is not None:
        predicates.append(EstoqueRecebivel.fundo_doc == cnpj_fundo)
    return predicates


async def _resolve_fundo_doc(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_id: UUID,
) -> str | None:
    """UA -> CNPJ (digits-only). None se UA nao existe ou sem CNPJ."""
    stmt = select(UnidadeAdministrativa.cnpj).where(
        UnidadeAdministrativa.id == fundo_id,
        UnidadeAdministrativa.tenant_id == tenant_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _resolve_max_data_referencia(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj_fundo: str | None,
) -> date | None:
    stmt = select(func.max(EstoqueRecebivel.data_referencia)).where(
        EstoqueRecebivel.tenant_id == tenant_id,
    )
    if cnpj_fundo is not None:
        stmt = stmt.where(EstoqueRecebivel.fundo_doc == cnpj_fundo)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _fetch_fundo_metadata(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj_fundo: str | None,
    data_referencia: date,
) -> dict[str, str | None]:
    """Pega fundo_doc + fundo_nome do primeiro registro do escopo."""
    stmt = (
        select(EstoqueRecebivel.fundo_doc, EstoqueRecebivel.fundo_nome)
        .where(
            EstoqueRecebivel.tenant_id == tenant_id,
            EstoqueRecebivel.data_referencia == data_referencia,
        )
        .limit(1)
    )
    if cnpj_fundo is not None:
        stmt = stmt.where(EstoqueRecebivel.fundo_doc == cnpj_fundo)
    row = (await db.execute(stmt)).first()
    if row is None:
        return {"fundo_doc": cnpj_fundo, "fundo_nome": None}
    return {"fundo_doc": row.fundo_doc, "fundo_nome": row.fundo_nome}


async def _aggregate_kpis(
    db: AsyncSession,
    *,
    where_predicates: list[Any],
) -> dict[str, Decimal | int]:
    stmt = select(
        func.coalesce(func.sum(EstoqueRecebivel.valor_nominal), 0).label("nominal"),
        func.coalesce(func.sum(EstoqueRecebivel.valor_presente), 0).label("presente"),
        func.coalesce(func.sum(EstoqueRecebivel.valor_aquisicao), 0).label("aquisicao"),
        func.coalesce(func.sum(EstoqueRecebivel.valor_pdd), 0).label("pdd"),
        func.count(EstoqueRecebivel.id).label("qtd"),
        func.coalesce(
            func.sum(
                case(
                    (
                        EstoqueRecebivel.situacao_recebivel == "Vencido",
                        EstoqueRecebivel.valor_nominal,
                    ),
                    else_=Decimal("0"),
                )
            ),
            0,
        ).label("vencido_nominal"),
    ).where(*where_predicates)
    row = (await db.execute(stmt)).one()
    return {
        "nominal": row.nominal,
        "presente": row.presente,
        "aquisicao": row.aquisicao,
        "pdd": row.pdd,
        "qtd": row.qtd,
        "vencido_nominal": row.vencido_nominal,
    }


async def _topn_sums_grouped(
    db: AsyncSession,
    *,
    where_predicates: list[Any],
    chave_col: Any,
) -> tuple[Decimal, Decimal]:
    """Retorna (top1_sum, top5_sum) do valor_nominal agrupado pela `chave_col`.

    Usado para concentracao por sacado / cedente — duas metricas vindas da
    mesma agregacao (ordenada desc), so trocando o LIMIT.
    """
    grouped = (
        select(func.sum(EstoqueRecebivel.valor_nominal).label("v"))
        .where(*where_predicates)
        .group_by(chave_col)
        .order_by(func.sum(EstoqueRecebivel.valor_nominal).desc())
    )
    top5_sub = grouped.limit(5).subquery()
    top1_sub = grouped.limit(1).subquery()
    top5 = Decimal(
        (await db.execute(select(func.coalesce(func.sum(top5_sub.c.v), 0)))).scalar_one() or 0
    )
    top1 = Decimal(
        (await db.execute(select(func.coalesce(func.sum(top1_sub.c.v), 0)))).scalar_one() or 0
    )
    return top1, top5


async def _breakdown_por_faixa_pdd(
    db: AsyncSession,
    *,
    where_predicates: list[Any],
    total: Decimal,
) -> list[dict[str, Any]]:
    """Breakdown por faixa Bacen, filtrado a titulos com valor_pdd > 0.

    Decisao do operador 2026-05-10: faixa A (PDD=0% por regra Bacen 2682) so
    polui a visualizacao. Excluindo titulos com valor_pdd=0, o card so mostra
    onde de fato ha provisao — faixas B-H tipicamente.
    """
    stmt = (
        select(
            EstoqueRecebivel.faixa_pdd,
            func.sum(EstoqueRecebivel.valor_nominal).label("nominal"),
            func.sum(EstoqueRecebivel.valor_pdd).label("pdd"),
            func.count().label("qtd"),
        )
        .where(*where_predicates, EstoqueRecebivel.valor_pdd > 0)
        .group_by(EstoqueRecebivel.faixa_pdd)
        .order_by(EstoqueRecebivel.faixa_pdd.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "chave": r.faixa_pdd,
            "label": f"Faixa {r.faixa_pdd}",
            "valor_nominal": Decimal(r.nominal or 0),
            # Decomposicao real de PDD por faixa Bacen 2682 (soma do bucket).
            # E essa serie que o card "PDD por faixa" plota — a soma das
            # barras casa com `kpis.valor_pdd_total` (decisao 2026-05-10).
            "valor_pdd": Decimal(r.pdd or 0),
            "qtd_titulos": int(r.qtd),
            "pct_do_total": _pct(Decimal(r.nominal or 0), total),
        }
        for r in rows
    ]


async def _breakdown_por_produto(
    db: AsyncSession,
    *,
    where_predicates: list[Any],
    total: Decimal,
) -> list[dict[str, Any]]:
    """Por tipo_recebivel (cheque, duplicata, NF, CCB, ...)."""
    stmt = (
        select(
            EstoqueRecebivel.tipo_recebivel,
            func.sum(EstoqueRecebivel.valor_nominal).label("nominal"),
            func.count().label("qtd"),
        )
        .where(*where_predicates)
        .group_by(EstoqueRecebivel.tipo_recebivel)
        .order_by(func.sum(EstoqueRecebivel.valor_nominal).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "chave": r.tipo_recebivel,
            "label": r.tipo_recebivel,
            "valor_nominal": Decimal(r.nominal or 0),
            "qtd_titulos": int(r.qtd),
            "pct_do_total": _pct(Decimal(r.nominal or 0), total),
        }
        for r in rows
    ]


async def _breakdown_por_coobrigacao(
    db: AsyncSession,
    *,
    where_predicates: list[Any],
    total: Decimal,
) -> list[dict[str, Any]]:
    """Por coobrigacao (cedente garante credito?) — bool com 2 buckets."""
    stmt = (
        select(
            EstoqueRecebivel.coobrigacao,
            func.sum(EstoqueRecebivel.valor_nominal).label("nominal"),
            func.count().label("qtd"),
        )
        .where(*where_predicates)
        .group_by(EstoqueRecebivel.coobrigacao)
        .order_by(EstoqueRecebivel.coobrigacao.desc())  # Sim primeiro
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "chave": "sim" if r.coobrigacao else "nao",
            "label": "Com coobrigacao" if r.coobrigacao else "Sem coobrigacao",
            "valor_nominal": Decimal(r.nominal or 0),
            "qtd_titulos": int(r.qtd),
            "pct_do_total": _pct(Decimal(r.nominal or 0), total),
        }
        for r in rows
    ]


async def _breakdown_por_situacao(
    db: AsyncSession,
    *,
    where_predicates: list[Any],
    total: Decimal,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            EstoqueRecebivel.situacao_recebivel,
            func.sum(EstoqueRecebivel.valor_nominal).label("nominal"),
            func.count().label("qtd"),
        )
        .where(*where_predicates)
        .group_by(EstoqueRecebivel.situacao_recebivel)
        .order_by(func.sum(EstoqueRecebivel.valor_nominal).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "chave": r.situacao_recebivel,
            "label": r.situacao_recebivel,
            "valor_nominal": Decimal(r.nominal or 0),
            "qtd_titulos": int(r.qtd),
            "pct_do_total": _pct(Decimal(r.nominal or 0), total),
        }
        for r in rows
    ]


async def _breakdown_top_n_with_outros(
    db: AsyncSession,
    *,
    where_predicates: list[Any],
    total: Decimal,
    chave_col: Any,
    nome_col: Any,
    top_n: int,
) -> list[dict[str, Any]]:
    """Top N + row sintetica 'Outros' com a cauda."""
    stmt = (
        select(
            chave_col.label("chave"),
            func.max(nome_col).label("nome"),
            func.sum(EstoqueRecebivel.valor_nominal).label("nominal"),
            func.count().label("qtd"),
        )
        .where(*where_predicates)
        .group_by(chave_col)
        .order_by(func.sum(EstoqueRecebivel.valor_nominal).desc())
    )
    rows = (await db.execute(stmt)).all()
    top = rows[:top_n]
    cauda = rows[top_n:]

    items: list[dict[str, Any]] = [
        {
            "chave": r.chave,
            "label": r.nome or r.chave,
            "valor_nominal": Decimal(r.nominal or 0),
            "qtd_titulos": int(r.qtd),
            "pct_do_total": _pct(Decimal(r.nominal or 0), total),
        }
        for r in top
    ]

    if cauda:
        cauda_nominal = sum((Decimal(r.nominal or 0) for r in cauda), Decimal("0"))
        cauda_qtd = sum(int(r.qtd) for r in cauda)
        items.append(
            {
                "chave": "__outros__",
                "label": f"Outros ({len(cauda)})",
                "valor_nominal": cauda_nominal,
                "qtd_titulos": cauda_qtd,
                "pct_do_total": _pct(cauda_nominal, total),
            }
        )

    return items


def _pct(parte: Decimal, total: Decimal) -> float:
    if total <= 0:
        return 0.0
    return float(parte / total * Decimal("100"))


def _empty_bundle(
    *,
    data_referencia: date | None,
    fundo_doc: str | None,
    fundo_nome: str | None,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Bundle zerado quando o escopo nao tem dado. Frontend renderiza EmptyState."""
    return {
        "data_referencia": data_referencia,
        "fundo_doc": fundo_doc,
        "fundo_nome": fundo_nome,
        "kpis": {
            "valor_nominal_total": Decimal("0"),
            "valor_presente_total": Decimal("0"),
            "valor_aquisicao_total": Decimal("0"),
            "valor_pdd_total": Decimal("0"),
            "qtd_titulos": 0,
            "pct_vencido": 0.0,
            "pdd_medio_pct": 0.0,
            "concentracao_top1_sacados_pct": 0.0,
            "concentracao_top5_sacados_pct": 0.0,
            "concentracao_top1_cedentes_pct": 0.0,
            "concentracao_top5_cedentes_pct": 0.0,
        },
        "por_faixa_pdd": [],
        "top_sacados": [],
        "top_cedentes": [],
        "por_originador": [],
        "por_produto": [],
        "por_situacao": [],
        "por_coobrigacao": [],
        "provenance": provenance,
        "is_empty": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Export CSV — todas as linhas escopadas (tenant + fundo + data_ref)
# ─────────────────────────────────────────────────────────────────────────────

# Ordem canonica das colunas, espelha o que o usuario pediu na UI da tabela.
# Headers em UPPER_SNAKE — convencao de export pra planilha (operacao usa
# import-mapper em Excel/PowerBI, headers UPPER sao mais ergonomicos).
EXPORT_COLUMNS: tuple[str, ...] = (
    "NOME_CEDENTE",
    "DOC_CEDENTE",
    "NOME_SACADO",
    "DOC_SACADO",
    "SEU_NUMERO",
    "NU_DOCUMENTO",
    "TIPO_RECEBIVEL",
    "VALOR_NOMINAL",
    "VALOR_PRESENTE",
    "VALOR_AQUISICAO",
    "VALOR_PDD",
    "FAIXA_PDD",
    "DATA_REFERENCIA",
    "DATA_VENCIMENTO_ORIGINAL",
    "DATA_VENCIMENTO_AJUSTADA",
    "DATA_EMISSAO",
    "DATA_AQUISICAO",
    "PRAZO",
    "PRAZO_ATUAL",
    "SITUACAO_RECEBIVEL",
    "TAXA_CESSAO",
    "TX_RECEBIVEL",
    "COOBRIGACAO",
)


async def stream_carteira_csv(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_id: UUID | None,
    data_referencia: date | None,
):
    """Generator que produz CSV (semicolon-separated, BR locale) linha-a-linha.

    Respeita os mesmos filtros do bundle (tenant_id + fundo_doc opcional +
    data_referencia obrigatoria). Se `data_referencia=None`, resolve pro
    max disponivel — mesmo comportamento do bundle, pra consistencia.

    Decisoes de formato BR:
        - Delimitador `;` (Excel pt-BR abre direto sem precisar import wizard)
        - Decimal `,` (locale BR)
        - Datas DD/MM/YYYY
        - Booleano SIM/NAO
        - Encoding UTF-8 com BOM (`\\ufeff`) pra Excel reconhecer acentos
    """
    import csv
    import io

    # Resolve cnpj_fundo e data_referencia (mesma logica do bundle)
    cnpj_fundo: str | None = None
    if fundo_id is not None:
        cnpj_fundo = await _resolve_fundo_doc(
            db, tenant_id=tenant_id, fundo_id=fundo_id
        )
    if data_referencia is None:
        data_referencia = await _resolve_max_data_referencia(
            db, tenant_id=tenant_id, cnpj_fundo=cnpj_fundo
        )

    # Header sempre, mesmo sem rows — Excel abre arquivo "vazio" legivel.
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    # BOM pra Excel BR reconhecer UTF-8
    buf.write("﻿")
    writer.writerow(EXPORT_COLUMNS)
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate()

    if data_referencia is None:
        return

    # Stream rows direto do silver — sem materializar 100k titulos em memoria.
    stmt = select(EstoqueRecebivel).where(
        *_scope_predicates(
            tenant_id=tenant_id,
            cnpj_fundo=cnpj_fundo,
            data_referencia=data_referencia,
        )
    ).execution_options(yield_per=500)

    result = await db.stream_scalars(stmt)
    async for partition in result.partitions():
        for r in partition:
            writer.writerow(_row_to_csv(r, data_referencia))
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()


def _row_to_csv(r: EstoqueRecebivel, data_ref: date) -> list[str]:
    """Converte uma row do silver pro layout CSV BR."""
    return [
        r.cedente_nome or "",
        r.cedente_doc or "",
        r.sacado_nome or "",
        r.sacado_doc or "",
        r.seu_numero or "",
        r.numero_documento or "",
        r.tipo_recebivel or "",
        _br_decimal(r.valor_nominal),
        _br_decimal(r.valor_presente),
        _br_decimal(r.valor_aquisicao),
        _br_decimal(r.valor_pdd),
        r.faixa_pdd or "",
        _br_date(r.data_referencia),
        _br_date(r.data_vencimento_original),
        _br_date(r.data_vencimento_ajustada),
        _br_date(r.data_emissao),
        _br_date(r.data_aquisicao),
        str(r.prazo) if r.prazo is not None else "",
        _prazo_atual_str(data_ref, r.data_vencimento_ajustada),
        r.situacao_recebivel or "",
        _br_decimal(r.taxa_cessao, places=10),
        _br_decimal(r.taxa_recebivel, places=10),
        "SIM" if r.coobrigacao else "NAO",
    ]


def _br_decimal(value: Decimal | None, *, places: int = 2) -> str:
    """Formata decimal com virgula como separador (locale BR). Sem separador
    de milhar (planilha aplica formatacao quando o usuario quer)."""
    if value is None:
        return ""
    quantized = value.quantize(Decimal("1." + "0" * places)) if places > 0 else value
    return str(quantized).replace(".", ",")


def _br_date(value: date | None) -> str:
    if value is None:
        return ""
    return value.strftime("%d/%m/%Y")


def _prazo_atual_str(data_ref: date, vcto: date | None) -> str:
    """Dias entre data_referencia e data_vencimento_ajustada. Pode ser negativo
    (em atraso). Vazio se vcto e null."""
    if vcto is None:
        return ""
    return str((vcto - data_ref).days)


def _prazo_atual_int(data_ref: date, vcto: date | None) -> int | None:
    """Variante numerica do _prazo_atual_str — usada no export XLSX onde a
    coluna fica como tipo numerico (Excel aplica formatacao/sort nativa)."""
    if vcto is None:
        return None
    return (vcto - data_ref).days


# ─────────────────────────────────────────────────────────────────────────────
# Export XLSX — native types (Excel aplica locale do usuario). Memory-friendly
# via openpyxl write_only mode.
# ─────────────────────────────────────────────────────────────────────────────


async def build_carteira_xlsx(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_id: UUID | None,
    data_referencia: date | None,
) -> bytes:
    """Gera o arquivo XLSX completo da carteira (uma sheet 'Carteira').

    write_only=True mantem footprint de memoria ~constante: rows nao ficam
    todas em memoria antes do save. Valores sao native types (Decimal, date,
    int) — Excel formata no locale do usuario (decimal/data BR sem precisar
    de wizard).

    Retorna bytes prontos pra StreamingResponse. Para 100k titulos, o arquivo
    fica em ~3-5 MB.
    """
    from io import BytesIO

    from openpyxl import Workbook

    # Resolve cnpj_fundo e data_referencia (mesma logica do bundle/CSV).
    cnpj_fundo: str | None = None
    if fundo_id is not None:
        cnpj_fundo = await _resolve_fundo_doc(
            db, tenant_id=tenant_id, fundo_id=fundo_id
        )
    if data_referencia is None:
        data_referencia = await _resolve_max_data_referencia(
            db, tenant_id=tenant_id, cnpj_fundo=cnpj_fundo
        )

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Carteira")
    ws.append(list(EXPORT_COLUMNS))

    if data_referencia is not None:
        stmt = (
            select(EstoqueRecebivel)
            .where(
                *_scope_predicates(
                    tenant_id=tenant_id,
                    cnpj_fundo=cnpj_fundo,
                    data_referencia=data_referencia,
                )
            )
            .execution_options(yield_per=500)
        )
        result = await db.stream_scalars(stmt)
        async for partition in result.partitions():
            for r in partition:
                ws.append(_row_to_xlsx(r, data_referencia))

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _row_to_xlsx(r: EstoqueRecebivel, data_ref: date) -> list[Any]:
    """Converte row do silver pro layout XLSX usando native types.

    Diferenca para `_row_to_csv`:
        - Decimais ficam Decimal (Excel reconhece como numero).
        - Dates ficam date (Excel formata locale do usuario).
        - Prazo atual fica int (sortable, filtravel como numero).
        - Coobrigacao fica string "SIM"/"NAO" (user-facing, igual ao CSV).
    """
    return [
        r.cedente_nome or "",
        r.cedente_doc or "",
        r.sacado_nome or "",
        r.sacado_doc or "",
        r.seu_numero or "",
        r.numero_documento or "",
        r.tipo_recebivel or "",
        r.valor_nominal,
        r.valor_presente,
        r.valor_aquisicao,
        r.valor_pdd,
        r.faixa_pdd or "",
        r.data_referencia,
        r.data_vencimento_original,
        r.data_vencimento_ajustada,
        r.data_emissao,
        r.data_aquisicao,
        r.prazo,
        _prazo_atual_int(data_ref, r.data_vencimento_ajustada),
        r.situacao_recebivel or "",
        r.taxa_cessao,
        r.taxa_recebivel,
        "SIM" if r.coobrigacao else "NAO",
    ]
