"""L2 Operacoes — helpers compartilhados.

Arquivo originalmente continha tanto as agregacoes publicas (get_resumo,
get_volume, get_taxa, ...) quanto helpers privados consumidos por outros
servicos. As agregacoes publicas legadas foram removidas na substituicao
de /bi/operacoes pela /bi/operacoes2 (2026-05-17); este modulo fica como
toolbox de helpers privados que `services/operacoes2.py` importa
diretamente.

Todas as queries:
  - sao escopadas por `tenant_id`
  - filtram `efetivada = true` (so operacoes que realmente aconteceram)
  - aplicam os filtros globais (periodo, produto, ua, cedente, gerente)
  - rodam contra `wh_operacao` (fato canonico no warehouse)

Medias ponderadas (taxa, prazo) sao ponderadas por `total_bruto` conforme
convencao do PowerBI atual (metrica por volume, nao por contagem).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Date,
    Numeric,
    String,
    and_,
    cast,
    func,
    literal_column,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bi.schemas.common import Provenance
from app.shared.audit_log.sync_health import last_data_update_at
from app.warehouse.dim import DimProduto, DimUnidadeAdministrativa
from app.warehouse.operacao import Operacao


def _produto_expr() -> ColumnElement[str]:
    """Extrai sigla do produto de `modalidade` (ex.: 'FAT-DM' -> 'FAT').

    Usa `literal_column` para inlining dos literais — se forem bind params, cada
    chamada gera `$N` diferentes e Postgres falha no GROUP BY com
    `column "modalidade" must appear in the GROUP BY clause`.
    """
    return cast(
        literal_column("split_part(wh_operacao.modalidade, '-', 1)"),
        String,
    )


def _apply_filters(
    stmt: Any,
    *,
    tenant_id: UUID,
    periodo_inicio: date | None,
    periodo_fim: date | None,
    produto_sigla: list[str] | None,
    ua_id: list[int] | None,
    cedente_id: int | None,
    sacado_id: int | None,
    gerente_documento: str | None,
) -> Any:
    """Aplica filtros globais + escopo de tenant + `efetivada=true`."""
    conditions: list[ColumnElement[bool]] = [
        Operacao.tenant_id == tenant_id,
        Operacao.efetivada.is_(True),
        Operacao.data_de_efetivacao.is_not(None),
    ]
    if periodo_inicio is not None:
        conditions.append(cast(Operacao.data_de_efetivacao, Date) >= periodo_inicio)
    if periodo_fim is not None:
        conditions.append(cast(Operacao.data_de_efetivacao, Date) <= periodo_fim)
    if produto_sigla:
        # Normaliza uppercase e aplica WHERE IN — multi-select do frontend.
        conditions.append(_produto_expr().in_([s.upper() for s in produto_sigla]))
    if ua_id:
        conditions.append(Operacao.unidade_administrativa_id.in_(ua_id))
    # cedente_id / sacado_id / gerente_documento nao ficam em wh_operacao — usar
    # wh_operacao_item (junto com wh_titulo_snapshot) em iteracao futura.
    return stmt.where(and_(*conditions))


def _weighted_avg(value: ColumnElement[Any], weight: ColumnElement[Any]) -> ColumnElement[Any]:
    """Media ponderada: SUM(value*weight) / NULLIF(SUM(weight), 0)."""
    return cast(
        func.sum(value * weight) / func.nullif(func.sum(weight), 0),
        Numeric(18, 6),
    )


def _as_float(v: Decimal | int | float | None) -> float:
    if v is None:
        return 0.0
    return float(v)


async def _build_provenance(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> Provenance:
    """Calcula proveniencia agregada para a resposta atual.

    - `last_source_updated_at` vem das linhas filtradas (MAX dentro do set).
    - `last_sync_at` vem de `MAX(wh_operacao.ingested_at)` no tenant inteiro
      (independe do filtro) — responde "quando dados frescos chegaram nesta
      tabela". Sobrevive a falhas parciais de outros sub-tasks do mesmo
      adapter (DRE pode estar quebrado e operacao continuar atualizando).
    """
    base = select(
        func.count(Operacao.id),
        func.max(Operacao.source_updated_at),
    )
    stmt = _apply_filters(base, tenant_id=tenant_id, **filters)
    row = (await db.execute(stmt)).one()
    row_count, last_source_updated = row
    last_sync = await last_data_update_at(db, tenant_id, Operacao)
    return Provenance(
        source_type="erp:bitfin",
        source_ids=["wh_operacao"],
        last_sync_at=last_sync,
        last_source_updated_at=last_source_updated,
        trust_level="high",
        ingested_by_version="bitfin_adapter_v1.0.0",
        row_count=int(row_count or 0),
    )


def _fmt_moeda_compacta_pt(valor: float) -> str:
    """Formata valor em BRL compacto pt-BR. Ex.: 118_200_000 -> 'R$ 118,2 mi'.

    Usado exclusivamente na narrativa do takeaway — nao substituir
    Intl.NumberFormat do frontend em outros lugares.
    """
    abs_v = abs(valor)
    if abs_v >= 1_000_000_000:
        return f"R$ {valor / 1_000_000_000:.1f} bi".replace(".", ",")
    if abs_v >= 1_000_000:
        return f"R$ {valor / 1_000_000:.1f} mi".replace(".", ",")
    if abs_v >= 1_000:
        return f"R$ {valor / 1_000:.1f} mil".replace(".", ",")
    return f"R$ {valor:.0f}"


def _shift_period_back(
    periodo_inicio: date | None, periodo_fim: date | None
) -> tuple[date | None, date | None]:
    """Retorna o periodo imediatamente anterior de MESMO TAMANHO.

    Ex.: (2026-01-01, 2026-03-31) -> (2025-10-01, 2025-12-31).
    Usado em calculos de delta (volume atual vs periodo anterior).
    Retorna (None, None) se qualquer ponta do periodo estiver ausente.
    """
    if periodo_inicio is None or periodo_fim is None:
        return None, None
    length = (periodo_fim - periodo_inicio).days
    prev_fim = periodo_inicio - timedelta(days=1)
    prev_inicio = prev_fim - timedelta(days=length)
    return prev_inicio, prev_fim


async def _scalar_sum_volume(
    db: AsyncSession,
    tenant_id: UUID,
    base_filters: dict[str, Any],
    periodo_inicio: date | None,
    periodo_fim: date | None,
) -> float:
    """SUM de total_bruto com periodo explicito (ignora o do base_filters)."""
    overridden = {**base_filters, "periodo_inicio": periodo_inicio, "periodo_fim": periodo_fim}
    stmt = _apply_filters(
        select(func.coalesce(func.sum(Operacao.total_bruto), 0)),
        tenant_id=tenant_id,
        **overridden,
    )
    return _as_float((await db.execute(stmt)).scalar_one())


async def _scalar_count_ops(
    db: AsyncSession,
    tenant_id: UUID,
    base_filters: dict[str, Any],
    periodo_inicio: date | None,
    periodo_fim: date | None,
) -> int:
    """COUNT de operacoes com periodo explicito."""
    overridden = {**base_filters, "periodo_inicio": periodo_inicio, "periodo_fim": periodo_fim}
    stmt = _apply_filters(
        select(func.count(Operacao.id)),
        tenant_id=tenant_id,
        **overridden,
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def _scalar_sum_titulos(
    db: AsyncSession,
    tenant_id: UUID,
    base_filters: dict[str, Any],
    periodo_inicio: date | None,
    periodo_fim: date | None,
) -> int:
    """SUM de quantidade_de_titulos com periodo explicito."""
    overridden = {**base_filters, "periodo_inicio": periodo_inicio, "periodo_fim": periodo_fim}
    stmt = _apply_filters(
        select(func.coalesce(func.sum(Operacao.quantidade_de_titulos), 0)),
        tenant_id=tenant_id,
        **overridden,
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


_MES_PT = (
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)


def _fmt_mes_curto_pt(d: date) -> str:
    """'2025-04-15' -> 'abr/25'. Independente de locale do servidor."""
    return f"{_MES_PT[d.month - 1]}/{d.year % 100:02d}"


def _fmt_comparacao_label_pt(
    prev_inicio: date | None, prev_fim: date | None
) -> str:
    """Texto de tooltip que descreve o range concreto comparado pelo delta.

    Exemplos:
      - mesmo mes      -> "vs mar/25"
      - 12 meses       -> "vs mai/24 a abr/25"
      - sem base       -> "sem base de comparacao"
    """
    if prev_inicio is None or prev_fim is None:
        return "sem base de comparacao"
    if (
        prev_inicio.year == prev_fim.year
        and prev_inicio.month == prev_fim.month
    ):
        return f"vs {_fmt_mes_curto_pt(prev_inicio)}"
    return f"vs {_fmt_mes_curto_pt(prev_inicio)} a {_fmt_mes_curto_pt(prev_fim)}"


def _safe_pct_change(current: float, previous: float) -> float | None:
    """(current - previous) / previous * 100. None quando previous == 0."""
    if previous == 0:
        return None
    return (current - previous) / previous * 100


async def _ua_id_to_nome_map(
    db: AsyncSession, tenant_id: UUID
) -> dict[int, str]:
    """Mapa {ua_id: nome} para enriquecer agregacoes por UA com label amigavel."""
    stmt = select(
        DimUnidadeAdministrativa.ua_id, DimUnidadeAdministrativa.nome
    ).where(DimUnidadeAdministrativa.tenant_id == tenant_id)
    rows = (await db.execute(stmt)).all()
    return {row.ua_id: row.nome for row in rows}


async def _produto_sigla_to_nome_map(
    db: AsyncSession, tenant_id: UUID
) -> dict[str, str]:
    """Mapa {sigla: nome} para exibir label amigavel em takeaway/narrativas."""
    stmt = select(DimProduto.sigla, DimProduto.nome).where(
        DimProduto.tenant_id == tenant_id
    )
    rows = (await db.execute(stmt)).all()
    return {row.sigla: row.nome for row in rows}


# ─── operacoes4 (Mes Corrente · controladoria) — receita por bucket ────────
#
# Os helpers abaixo expoem agregacoes de RECEITA em REGIME CAIXA usando
# wh_operacao (4 buckets: desagio, tarifa_cessao, tarifas_operacionais,
# outras). Sao consumidos por `services/operacoes4.py` (endpoint
# /lens-receitas) e por `services/operacoes2.py` (enriquece colunas de
# Receita/Yield nas tabelas L5 e L7 das paginas de mes corrente).
#
# IOF (`total_de_iof`) NAO entra nos buckets — e passthrough, fica fora do
# yield e da composicao. Multa, mora, cobranca e aditivo NAO existem em
# wh_operacao; sao eventos pos-cessao em wh_dre_mensal (regime competencia).
# Ver CLAUDE.md banner operacoes4 + handoff SPEC.


def _receita_desagio_expr() -> ColumnElement[Any]:
    """SQL expr do bucket desagio."""
    return func.coalesce(func.sum(Operacao.total_de_juros), 0)


def _receita_tarifa_cessao_expr() -> ColumnElement[Any]:
    """SQL expr do bucket tarifa de cessao."""
    return func.coalesce(func.sum(Operacao.total_dos_comunicados_de_cessao), 0)


def _receita_tarifas_operacionais_expr() -> ColumnElement[Any]:
    """SQL expr do bucket tarifas operacionais (CF+CFI+RB+DD)."""
    return func.coalesce(
        func.sum(
            Operacao.total_das_consultas_financeiras
            + Operacao.total_das_consultas_fiscais
            + Operacao.total_dos_registros_bancarios
            + Operacao.total_dos_documentos_digitais
        ),
        0,
    )


def _receita_outras_expr() -> ColumnElement[Any]:
    """SQL expr do bucket outras (ad_valorem + rebate; zero em prod hoje)."""
    return func.coalesce(
        func.sum(Operacao.total_de_ad_valorem + Operacao.total_de_rebate),
        0,
    )


def _receita_total_expr() -> ColumnElement[Any]:
    """SQL expr da receita total (soma dos 4 buckets, REGIME CAIXA).

    Bate com o calculo de `_agg_kpi.receita` em `services/operacoes2.py`
    (juros + cf + cfi + rb + cc + dd). Ad_valorem e rebate sao zero hoje
    em prod mas entram pra robustez quando comecarem a aparecer.
    """
    return func.coalesce(
        func.sum(
            Operacao.total_de_juros
            + Operacao.total_dos_comunicados_de_cessao
            + Operacao.total_das_consultas_financeiras
            + Operacao.total_das_consultas_fiscais
            + Operacao.total_dos_registros_bancarios
            + Operacao.total_dos_documentos_digitais
            + Operacao.total_de_ad_valorem
            + Operacao.total_de_rebate
        ),
        0,
    )


async def _calcular_receita_composicao(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    filters: dict[str, Any],
    parity_filters: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Retorna receita por bucket no MTD + paridade DU + shares e deltas.

    Output:
      {
        "desagio": {valor, parity, share_pct, delta_pct},
        "tarifa_cessao": {...},
        "tarifas_operacionais": {...},
        "outras": {...},
        "_total": {valor, parity, delta_pct},
      }

    `filters` = janela MTD. `parity_filters` = janela equivalente nos mesmos
    N DUs do mes anterior. Ambos passam por `_apply_filters` (regra dura
    CLAUDE.md §7.2).
    """
    base_select = select(
        _receita_desagio_expr().label("desagio"),
        _receita_tarifa_cessao_expr().label("tarifa_cessao"),
        _receita_tarifas_operacionais_expr().label("tarifas_operacionais"),
        _receita_outras_expr().label("outras"),
    )

    mtd_stmt = _apply_filters(base_select, tenant_id=tenant_id, **filters)
    mtd = (await db.execute(mtd_stmt)).one()

    par_stmt = _apply_filters(base_select, tenant_id=tenant_id, **parity_filters)
    par = (await db.execute(par_stmt)).one()

    buckets = ("desagio", "tarifa_cessao", "tarifas_operacionais", "outras")

    mtd_vals = {b: _as_float(getattr(mtd, b)) for b in buckets}
    par_vals = {b: _as_float(getattr(par, b)) for b in buckets}

    total_mtd = sum(mtd_vals.values())
    total_par = sum(par_vals.values())

    out: dict[str, dict[str, Any]] = {}
    for b in buckets:
        share = (mtd_vals[b] / total_mtd * 100.0) if total_mtd > 0 else 0.0
        delta = _safe_pct_change(mtd_vals[b], par_vals[b])
        out[b] = {
            "valor": mtd_vals[b],
            "parity": par_vals[b],
            "share_pct": share,
            "delta_pct": delta,
        }

    out["_total"] = {
        "valor": total_mtd,
        "parity": total_par,
        "delta_pct": _safe_pct_change(total_mtd, total_par),
    }
    return out


async def _calcular_yield_du(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    filters: dict[str, Any],
    parity_filters: dict[str, Any],
) -> dict[str, Any]:
    """Yield (receita/vop) por DU do mes corrente + paridade DU do mes ant.

    Output:
      {
        "yield_mtd_por_data": {date: (receita, vop, yield_pct_or_None)},
        "yield_par_por_data": {date: (receita, vop, yield_pct_or_None)},
        "yield_wavg":        float,
        "yield_parity_wavg": float,
        "yield_delta_pp":    float | None,
      }

    Frontend (ou service consumidor) faz o pareamento DU-a-DU usando
    `wh_dim_dia_util`. Aqui retornamos so o dado bruto por data calendario
    — desacopla o yield da disponibilidade do calendario.
    """
    base_select = select(
        cast(Operacao.data_de_efetivacao, Date).label("data"),
        _receita_total_expr().label("receita"),
        func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
    ).group_by(cast(Operacao.data_de_efetivacao, Date))

    mtd_stmt = _apply_filters(base_select, tenant_id=tenant_id, **filters)
    par_stmt = _apply_filters(base_select, tenant_id=tenant_id, **parity_filters)

    def _index(rows: Any) -> dict[date, tuple[float, float, float | None]]:
        out: dict[date, tuple[float, float, float | None]] = {}
        for r in rows:
            rec = _as_float(r.receita)
            vop = _as_float(r.vop)
            y = (rec / vop * 100.0) if vop > 0 else None
            out[r.data] = (rec, vop, y)
        return out

    mtd_rows = (await db.execute(mtd_stmt)).all()
    par_rows = (await db.execute(par_stmt)).all()

    mtd_idx = _index(mtd_rows)
    par_idx = _index(par_rows)

    # Yield wavg ponderado por VOP no MTD
    sum_rec_mtd = sum(rec for rec, _vop, _y in mtd_idx.values())
    sum_vop_mtd = sum(vop for _rec, vop, _y in mtd_idx.values())
    yield_wavg = (sum_rec_mtd / sum_vop_mtd * 100.0) if sum_vop_mtd > 0 else 0.0

    sum_rec_par = sum(rec for rec, _vop, _y in par_idx.values())
    sum_vop_par = sum(vop for _rec, vop, _y in par_idx.values())
    yield_parity_wavg = (
        (sum_rec_par / sum_vop_par * 100.0) if sum_vop_par > 0 else 0.0
    )

    yield_delta_pp: float | None = (
        yield_wavg - yield_parity_wavg if sum_vop_par > 0 else None
    )

    return {
        "yield_mtd_por_data": mtd_idx,
        "yield_par_por_data": par_idx,
        "yield_wavg": yield_wavg,
        "yield_parity_wavg": yield_parity_wavg,
        "yield_delta_pp": yield_delta_pp,
    }


async def _calcular_receita_por_dia(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    filters: dict[str, Any],
) -> dict[date, tuple[float, float | None]]:
    """Retorna {data: (receita, yield_pct)} para enriquecer L7 (tabela diaria).

    yield_pct = receita/vop em % a.m. None quando vop=0 no dia. Aplica
    `_apply_filters` — escopo de tenant + filtros globais respeitados.
    """
    stmt = _apply_filters(
        select(
            cast(Operacao.data_de_efetivacao, Date).label("data"),
            _receita_total_expr().label("receita"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("vop"),
        ).group_by(cast(Operacao.data_de_efetivacao, Date)),
        tenant_id=tenant_id,
        **filters,
    )
    rows = (await db.execute(stmt)).all()
    out: dict[date, tuple[float, float | None]] = {}
    for r in rows:
        rec = _as_float(r.receita)
        vop = _as_float(r.vop)
        y = (rec / vop * 100.0) if vop > 0 else None
        out[r.data] = (rec, y)
    return out


async def _calcular_receita_e_vop_por_op(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    filters: dict[str, Any],
) -> dict[Any, tuple[float, float]]:
    """Retorna {operacao_id: (receita, vop_bruto)} para alocacao proporcional.

    Granularidade necessaria pra alocar receita por cedente — uma operacao
    pode ter N titulos de M cedentes; receita do cedente = receita_op *
    (volume_titulos_cedente / volume_total_op).
    """
    stmt = _apply_filters(
        select(
            Operacao.operacao_id.label("op_id"),
            func.coalesce(Operacao.total_bruto, 0).label("vop"),
            (
                func.coalesce(Operacao.total_de_juros, 0)
                + func.coalesce(Operacao.total_dos_comunicados_de_cessao, 0)
                + func.coalesce(Operacao.total_das_consultas_financeiras, 0)
                + func.coalesce(Operacao.total_das_consultas_fiscais, 0)
                + func.coalesce(Operacao.total_dos_registros_bancarios, 0)
                + func.coalesce(Operacao.total_dos_documentos_digitais, 0)
                + func.coalesce(Operacao.total_de_ad_valorem, 0)
                + func.coalesce(Operacao.total_de_rebate, 0)
            ).label("receita"),
        ),
        tenant_id=tenant_id,
        **filters,
    )
    rows = (await db.execute(stmt)).all()
    return {r.op_id: (_as_float(r.receita), _as_float(r.vop)) for r in rows}


def _alocar_receita_por_cedente(
    titulos: list[dict[str, Any]],
    receita_e_vop_por_op: dict[Any, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """Aloca a receita de cada operacao proporcionalmente aos seus cedentes.

    Logica: uma operacao pode conter N titulos de M cedentes. A receita da
    op (4 buckets somados) e alocada para cada cedente proporcional ao
    `valor_base` de seus titulos dentro da op.

    Args:
        titulos: lista de dicts com chaves ['op_id', 'cedente_nome',
            'valor_base'] — output canonico de
            `services/operacoes2.py::_titulos_por_cedente_periodo`.
        receita_e_vop_por_op: {op_id: (receita_op, vop_op)} — output de
            `_calcular_receita_e_vop_por_op` no mesmo periodo.

    Returns:
        {cedente_nome: (receita_alocada, volume_mtd)} — yield calculado pelo
        caller (receita / volume_mtd em %). Cedentes sem volume nao aparecem.

    Edge cases:
      - Op nao encontrada em receita_e_vop_por_op: receita 0 alocada.
      - vop_op == 0 (raro, op anulada apos efetivacao): receita 0 alocada.
    """
    acumulado_receita: dict[str, float] = {}
    acumulado_volume: dict[str, float] = {}

    # Agrega por (op, cedente) primeiro para evitar reprocessamento.
    por_op_cedente: dict[tuple[Any, str], float] = {}
    for t in titulos:
        key = (t["op_id"], t["cedente_nome"])
        por_op_cedente[key] = por_op_cedente.get(key, 0.0) + t["valor_base"]

    # Volume total por op (para denominador da alocacao).
    volume_total_por_op: dict[Any, float] = {}
    for (op_id, _cedente), valor in por_op_cedente.items():
        volume_total_por_op[op_id] = (
            volume_total_por_op.get(op_id, 0.0) + valor
        )

    # Aloca proporcional.
    for (op_id, cedente_nome), valor_cedente in por_op_cedente.items():
        receita_op, _vop_op = receita_e_vop_por_op.get(op_id, (0.0, 0.0))
        vol_total = volume_total_por_op.get(op_id, 0.0)
        alocacao = (
            0.0 if vol_total <= 0 else receita_op * (valor_cedente / vol_total)
        )
        acumulado_receita[cedente_nome] = (
            acumulado_receita.get(cedente_nome, 0.0) + alocacao
        )
        acumulado_volume[cedente_nome] = (
            acumulado_volume.get(cedente_nome, 0.0) + valor_cedente
        )

    return {
        nome: (acumulado_receita[nome], acumulado_volume[nome])
        for nome in acumulado_receita
    }
