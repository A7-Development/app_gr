"""L2 Operacoes — servico de agregacoes.

Todas as queries:
  - sao escopadas por `tenant_id`
  - filtram `efetivada = true` (so operacoes que realmente aconteceram)
  - aplicam os filtros globais (periodo, produto, ua, cedente, gerente)
  - rodam contra `wh_operacao` (fato canonico no warehouse)

Medias ponderadas (taxa, prazo) sao ponderadas por `total_bruto` conforme
convencao do PowerBI atual (metrica por volume, nao por contagem).
"""

from __future__ import annotations

from collections.abc import Sequence
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

from app.modules.bi.schemas.common import KPI, CategoryValue, Point, Provenance
from app.modules.bi.schemas.operacoes import (
    CategoryValueDelta,
    OperacoesResumo,
    PointDim,
    SeriesEDiaUtil,
    SeriesEPrazo,
    SeriesEReceita,
    SeriesETaxa,
    SeriesETicket,
    SeriesEVolume,
    TopCedenteItem,
    VolumeResumoDeltas,
)
from app.shared.audit_log.sync_health import last_sync_at
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


def _tipo_recebivel_expr() -> ColumnElement[str]:
    """Extrai tipo do recebivel (ex.: 'FAT-DM' -> 'DM')."""
    return cast(
        literal_column("split_part(wh_operacao.modalidade, '-', 2)"),
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
    - `last_sync_at` vem do `decision_log` (global, independe do filtro) —
      responde "o pipeline esta vivo?" mesmo quando o set filtrado nao tem
      linhas novas.
    """
    base = select(
        func.count(Operacao.id),
        func.max(Operacao.source_updated_at),
    )
    stmt = _apply_filters(base, tenant_id=tenant_id, **filters)
    row = (await db.execute(stmt)).one()
    row_count, last_source_updated = row
    last_sync = await last_sync_at(db, tenant_id, rule_or_model="bitfin_adapter")
    return Provenance(
        source_type="erp:bitfin",
        source_ids=["wh_operacao"],
        last_sync_at=last_sync,
        last_source_updated_at=last_source_updated,
        trust_level="high",
        ingested_by_version="bitfin_adapter_v1.0.0",
        row_count=int(row_count or 0),
    )


def _kpi(
    label: str, valor: Decimal | int | float | None, unidade: str, detalhe: str | None = None
) -> KPI:
    return KPI(label=label, valor=_as_float(valor), unidade=unidade, detalhe=detalhe)


def _points(rows: Sequence[Any]) -> list[Point]:
    return [Point(periodo=r.periodo, valor=_as_float(r.valor)) for r in rows]


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


def _build_takeaway_pt(
    *,
    volume_atual: float,
    volume_anterior: float | None,
    ticket_atual: float,
    ticket_anterior: float | None,
    produto_lider_sigla: str | None,
    produto_lider_nome: str | None,
    produto_lider_share_pct: float | None,
) -> str | None:
    """Compoe narrativa factual de 1-2 frases sobre o periodo.

    Regras:
      - Sem volume (periodo vazio) -> retorna None.
      - Sem `volume_anterior` -> omite comparacao ("No periodo, volume de X").
      - Produto lider com share < 20% -> omite "puxado por" (nao e driver claro).
      - Ticket: compara apenas se ambos ticket_atual e ticket_anterior existem;
        variacoes < 1% sao classificadas como "estavel".
      - Tom sobrio, factual — nunca adjetivos subjetivos ("incrivel", "preocupante").

    Output exemplo:
      "No periodo, volume de R$ 118,2 mi (+5,2% vs anterior), puxado por
       Faturizacao (42% de participacao). Ticket medio subiu 3,1%."
    """
    if volume_atual <= 0:
        return None

    def _fmt_pct(v: float) -> str:
        return f"{v:.1f}".replace(".", ",")

    # §1 — frase de volume
    partes: list[str] = [f"No periodo, volume de {_fmt_moeda_compacta_pt(volume_atual)}"]
    if volume_anterior is not None and volume_anterior > 0:
        delta_pct = (volume_atual - volume_anterior) / volume_anterior * 100
        sinal = "+" if delta_pct >= 0 else "-"
        partes[0] += f" ({sinal}{_fmt_pct(abs(delta_pct))}% vs anterior)"

    # §2 — driver (so se share >= 20%)
    if (
        produto_lider_sigla
        and produto_lider_share_pct is not None
        and produto_lider_share_pct >= 20.0
    ):
        nome = produto_lider_nome or produto_lider_sigla
        partes[0] += f", puxado por {nome} ({produto_lider_share_pct:.0f}% de participacao)"

    frase_volume = partes[0] + "."

    # §3 — ticket (frase secundaria opcional)
    frase_ticket: str | None = None
    if ticket_atual > 0 and ticket_anterior is not None and ticket_anterior > 0:
        delta_ticket_pct = (ticket_atual - ticket_anterior) / ticket_anterior * 100
        if abs(delta_ticket_pct) < 1.0:
            frase_ticket = "Ticket medio estavel."
        else:
            verbo = "subiu" if delta_ticket_pct > 0 else "caiu"
            frase_ticket = f"Ticket medio {verbo} {_fmt_pct(abs(delta_ticket_pct))}%."

    return f"{frase_volume} {frase_ticket}" if frase_ticket else frase_volume


def _categories(rows: Sequence[Any], include_qtd: bool = True) -> list[CategoryValue]:
    return [
        CategoryValue(
            categoria=r.categoria or "(n/d)",
            valor=_as_float(r.valor),
            quantidade=int(r.quantidade)
            if include_qtd and getattr(r, "quantidade", None) is not None
            else None,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Aggregation functions (one per L3 tab + resumo)
# ---------------------------------------------------------------------------


async def get_resumo(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[OperacoesResumo, Provenance]:
    """Resumo/KPIs topo da L2 Operacoes (todas as L3 acima do fold)."""
    stmt = select(
        func.count(Operacao.id).label("qtd"),
        func.coalesce(func.sum(Operacao.total_bruto), 0).label("bruto"),
        func.coalesce(func.sum(Operacao.total_de_juros), 0).label("juros"),
        func.coalesce(func.sum(Operacao.total_das_consultas_financeiras), 0).label("tar_cf"),
        func.coalesce(func.sum(Operacao.total_dos_registros_bancarios), 0).label("tar_rb"),
        func.coalesce(func.sum(Operacao.total_das_consultas_fiscais), 0).label("tar_cfi"),
        func.coalesce(func.sum(Operacao.total_dos_comunicados_de_cessao), 0).label("tar_cc"),
        func.coalesce(func.sum(Operacao.total_dos_documentos_digitais), 0).label("tar_dd"),
        _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("taxa_pond"),
        _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("prazo_pond"),
    )
    stmt = _apply_filters(stmt, tenant_id=tenant_id, **filters)
    row = (await db.execute(stmt)).one()

    bruto = row.bruto or Decimal(0)
    qtd = int(row.qtd or 0)
    ticket = (bruto / qtd) if qtd > 0 else Decimal(0)
    receita_contratada = (
        (row.juros or 0)
        + (row.tar_cf or 0)
        + (row.tar_rb or 0)
        + (row.tar_cfi or 0)
        + (row.tar_cc or 0)
        + (row.tar_dd or 0)
    )

    # Takeaway narrativo — 2 queries extras (volume anterior + top produto).
    # Falhas silenciosas: se qualquer uma levantar/retornar vazio, takeaway
    # degrada para None e o frontend simplesmente nao renderiza a faixa.
    periodo_inicio: date | None = filters.get("periodo_inicio")
    periodo_fim: date | None = filters.get("periodo_fim")
    prev_inicio, prev_fim = _shift_period_back(periodo_inicio, periodo_fim)
    volume_anterior: float | None = None
    ticket_anterior: float | None = None
    if prev_inicio is not None and prev_fim is not None:
        volume_anterior = await _scalar_sum_volume(
            db, tenant_id, filters, prev_inicio, prev_fim
        )
        qtd_anterior = await _scalar_count_ops(
            db, tenant_id, filters, prev_inicio, prev_fim
        )
        if qtd_anterior > 0:
            ticket_anterior = volume_anterior / qtd_anterior

    # Top produto — sigla + share pct sobre o periodo atual.
    prod_sigla, prod_share = await _top_produto_para_takeaway(
        db, tenant_id, filters, _as_float(bruto)
    )
    prod_nome: str | None = None
    if prod_sigla:
        prod_nomes = await _produto_sigla_to_nome_map(db, tenant_id)
        prod_nome = prod_nomes.get(prod_sigla)

    takeaway = _build_takeaway_pt(
        volume_atual=_as_float(bruto),
        volume_anterior=volume_anterior,
        ticket_atual=_as_float(ticket),
        ticket_anterior=ticket_anterior,
        produto_lider_sigla=prod_sigla,
        produto_lider_nome=prod_nome,
        produto_lider_share_pct=prod_share,
    )

    resumo = OperacoesResumo(
        total_operacoes=_kpi("Operacoes efetivadas", qtd, "un"),
        volume_bruto=_kpi("Volume bruto", bruto, "BRL"),
        ticket_medio=_kpi("Ticket medio", ticket, "BRL"),
        taxa_media=_kpi("Taxa media (pond.)", row.taxa_pond, "%"),
        prazo_medio=_kpi("Prazo medio (pond.)", row.prazo_pond, "dias"),
        receita_contratada=_kpi("Receita contratada", receita_contratada, "BRL"),
        takeaway_pt=takeaway,
    )
    provenance = await _build_provenance(db, tenant_id, filters)
    return resumo, provenance


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


def _shift_year_back(
    periodo_inicio: date | None, periodo_fim: date | None
) -> tuple[date | None, date | None]:
    """Retorna o mesmo periodo 12 meses antes (YoY).

    Ex.: (2026-01-01, 2026-03-31) -> (2025-01-01, 2025-03-31).
    """
    if periodo_inicio is None or periodo_fim is None:
        return None, None

    def _minus_year(d: date) -> date:
        try:
            return d.replace(year=d.year - 1)
        except ValueError:
            # 29/02 em ano nao-bissexto -> 28/02
            return d.replace(year=d.year - 1, day=28)

    return _minus_year(periodo_inicio), _minus_year(periodo_fim)


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


async def _top_produto_para_takeaway(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
    volume_total: float,
) -> tuple[str | None, float | None]:
    """Retorna (sigla, share_pct) do produto com maior volume no periodo.

    Usado somente pela narrativa do takeaway — share_pct em escala 0-100.
    Retorna (None, None) quando periodo vazio ou volume_total <= 0.
    """
    if volume_total <= 0:
        return None, None
    stmt = _apply_filters(
        select(
            _produto_expr().label("sigla"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .group_by(_produto_expr())
        .order_by(func.sum(Operacao.total_bruto).desc())
        .limit(1),
        tenant_id=tenant_id,
        **filters,
    )
    row = (await db.execute(stmt)).first()
    if row is None or row.sigla is None:
        return None, None
    share_pct = _as_float(row.valor) / volume_total * 100
    return str(row.sigla), share_pct


async def get_volume(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[SeriesEVolume, Provenance]:
    """L3 Volume — serie configuravel + decomposicao + contexto + overlays.

    Ver `SeriesEVolume` (schemas/operacoes.py) para o mapa de campos ←→
    perguntas do diretor.
    """
    periodo_inicio: date | None = filters.get("periodo_inicio")
    periodo_fim: date | None = filters.get("periodo_fim")
    bucket = func.date_trunc("month", Operacao.data_de_efetivacao)

    ua_nomes = await _ua_id_to_nome_map(db, tenant_id)

    # ─────────────────────────────────────────────────────────────
    # 1. Evolucao mensal consolidada (chart principal, modo "Total")
    # ─────────────────────────────────────────────────────────────
    evo_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **filters,
    )
    evo = (await db.execute(evo_stmt)).all()

    # ─────────────────────────────────────────────────────────────
    # 2. Evolucao por produto (chart principal modo "Por produto")
    # ─────────────────────────────────────────────────────────────
    evo_prod_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            _produto_expr().label("categoria_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .group_by(bucket, _produto_expr())
        .order_by(bucket, _produto_expr()),
        tenant_id=tenant_id,
        **filters,
    )
    evo_prod = (await db.execute(evo_prod_stmt)).all()

    # ─────────────────────────────────────────────────────────────
    # 3. Evolucao por UA (chart principal modo "Por UA")
    # ─────────────────────────────────────────────────────────────
    evo_ua_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            Operacao.unidade_administrativa_id.label("ua_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .group_by(bucket, Operacao.unidade_administrativa_id)
        .order_by(bucket, Operacao.unidade_administrativa_id),
        tenant_id=tenant_id,
        **filters,
    )
    evo_ua = (await db.execute(evo_ua_stmt)).all()

    # ─────────────────────────────────────────────────────────────
    # 4. Por produto (decomposicao §3) — volume + qtd + delta vs periodo
    #    anterior + taxa e prazo medios ponderados por volume.
    # ─────────────────────────────────────────────────────────────
    prod_stmt = _apply_filters(
        select(
            _produto_expr().label("categoria_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            func.count(Operacao.id).label("quantidade"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("taxa"),
            _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("prazo"),
        )
        .group_by(_produto_expr())
        .order_by(func.sum(Operacao.total_bruto).desc()),
        tenant_id=tenant_id,
        **filters,
    )
    prod = (await db.execute(prod_stmt)).all()

    prev_inicio, prev_fim = _shift_period_back(periodo_inicio, periodo_fim)
    prod_prev: dict[str, float] = {}
    if prev_inicio and prev_fim:
        prev_filters = {**filters, "periodo_inicio": prev_inicio, "periodo_fim": prev_fim}
        prev_stmt = _apply_filters(
            select(
                _produto_expr().label("categoria_id"),
                func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            ).group_by(_produto_expr()),
            tenant_id=tenant_id,
            **prev_filters,
        )
        prod_prev = {
            str(r.categoria_id or "(n/d)"): _as_float(r.valor)
            for r in (await db.execute(prev_stmt)).all()
        }

    # ─────────────────────────────────────────────────────────────
    # 4.1 Tendencia 90d por produto — janela rolante FIXA de 90 dias
    #      (ignora o filtro de periodo) com granularidade semanal.
    #
    # Objetivo: sparkline inline na tabela do painel Indicadores.
    # Complemento: soma do periodo vs soma dos 90d anteriores gera delta_pct.
    # ─────────────────────────────────────────────────────────────
    spark90_end = periodo_fim or date.today()
    spark90_start = spark90_end - timedelta(days=90)
    spark90_prev_end = spark90_start
    spark90_prev_start = spark90_prev_end - timedelta(days=90)
    week_bucket = func.date_trunc("week", Operacao.data_de_efetivacao)

    # Semanas do periodo atual (agrupado por produto+semana)
    spark90_stmt = (
        select(
            _produto_expr().label("categoria_id"),
            cast(week_bucket, Date).label("periodo"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .where(
            Operacao.tenant_id == tenant_id,
            Operacao.efetivada.is_(True),
            Operacao.data_de_efetivacao.is_not(None),
            cast(Operacao.data_de_efetivacao, Date) >= spark90_start,
            cast(Operacao.data_de_efetivacao, Date) <= spark90_end,
        )
        .group_by(_produto_expr(), week_bucket)
        .order_by(_produto_expr(), week_bucket)
    )
    spark90_rows = (await db.execute(spark90_stmt)).all()
    spark90_by_sigla: dict[str, list[Point]] = {}
    for r in spark90_rows:
        sigla = str(r.categoria_id or "(n/d)")
        spark90_by_sigla.setdefault(sigla, []).append(
            Point(periodo=r.periodo, valor=_as_float(r.valor))
        )

    # Total dos 90d anteriores (para o delta % na coluna Tendencia)
    spark90_prev_stmt = (
        select(
            _produto_expr().label("categoria_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .where(
            Operacao.tenant_id == tenant_id,
            Operacao.efetivada.is_(True),
            Operacao.data_de_efetivacao.is_not(None),
            cast(Operacao.data_de_efetivacao, Date) >= spark90_prev_start,
            cast(Operacao.data_de_efetivacao, Date) < spark90_prev_end,
        )
        .group_by(_produto_expr())
    )
    spark90_prev_by_sigla: dict[str, float] = {
        str(r.categoria_id or "(n/d)"): _as_float(r.valor)
        for r in (await db.execute(spark90_prev_stmt)).all()
    }
    # Total atual = soma das semanas da sparkline
    spark90_curr_by_sigla: dict[str, float] = {
        sigla: sum(p.valor for p in pts)
        for sigla, pts in spark90_by_sigla.items()
    }

    # ─────────────────────────────────────────────────────────────
    # 5. Por UA (decomposicao §3) + delta
    # ─────────────────────────────────────────────────────────────
    ua_stmt = _apply_filters(
        select(
            Operacao.unidade_administrativa_id.label("ua_id"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            func.count(Operacao.id).label("quantidade"),
        )
        .group_by(Operacao.unidade_administrativa_id)
        .order_by(func.sum(Operacao.total_bruto).desc()),
        tenant_id=tenant_id,
        **filters,
    )
    ua = (await db.execute(ua_stmt)).all()

    ua_prev: dict[int, float] = {}
    if prev_inicio and prev_fim:
        prev_filters = {**filters, "periodo_inicio": prev_inicio, "periodo_fim": prev_fim}
        prev_ua_stmt = _apply_filters(
            select(
                Operacao.unidade_administrativa_id.label("ua_id"),
                func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            ).group_by(Operacao.unidade_administrativa_id),
            tenant_id=tenant_id,
            **prev_filters,
        )
        ua_prev = {
            int(r.ua_id): _as_float(r.valor)
            for r in (await db.execute(prev_ua_stmt)).all()
        }

    # ─────────────────────────────────────────────────────────────
    # 6. Overlays: evolucao mensal de taxa/prazo/ticket medio
    #    (ponderados por volume, mesmos periodos da evolucao principal)
    # ─────────────────────────────────────────────────────────────
    evo_taxa_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("valor"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **filters,
    )
    evo_taxa = (await db.execute(evo_taxa_stmt)).all()

    evo_prazo_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("valor"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **filters,
    )
    evo_prazo = (await db.execute(evo_prazo_stmt)).all()

    # Ticket medio por mes = SUM(total_bruto) / COUNT(operacoes) do mes.
    evo_ticket_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            (
                func.coalesce(func.sum(Operacao.total_bruto), 0)
                / func.nullif(func.count(Operacao.id), 0)
            ).label("valor"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **filters,
    )
    evo_ticket = (await db.execute(evo_ticket_stmt)).all()

    # ─────────────────────────────────────────────────────────────
    # 7. Resumo — KPIs de contexto (§1) com deltas e sparklines 12M
    # ─────────────────────────────────────────────────────────────
    # Volume/ticket/n_ops totais ja saem da agregacao por produto ou por mes.
    volume_total = sum(_as_float(r.valor) for r in evo)
    n_operacoes_total = sum(int(r.quantidade) for r in prod)
    ticket_medio = volume_total / n_operacoes_total if n_operacoes_total > 0 else 0.0

    # Ticket medio por TITULO — volume / soma(quantidade_de_titulos).
    # Complementa o "Ticket medio / Op.": em FIDC, uma operacao pode conter
    # varios titulos (recebiveis), entao esta metrica expressa o valor real
    # por papel cedido ("ticket unitario do recebivel").
    n_titulos_total = await _scalar_sum_titulos(
        db, tenant_id, filters, periodo_inicio, periodo_fim
    )
    ticket_medio_titulo = (
        volume_total / n_titulos_total if n_titulos_total > 0 else 0.0
    )

    # ─────────────────────────────────────────────────────────────
    # Deltas — todos contra o periodo IMEDIATAMENTE ANTERIOR DE MESMO
    # TAMANHO (`_shift_period_back`). Evita o mismatch antigo onde MoM
    # comparava ultimo-vs-penultimo-mes do filtro mas o numero exibido
    # era a soma do periodo inteiro.
    # ─────────────────────────────────────────────────────────────
    prev_inicio, prev_fim = _shift_period_back(periodo_inicio, periodo_fim)
    volume_anterior: float | None = None
    n_ops_anterior: int | None = None
    n_titulos_anterior: int | None = None
    if prev_inicio is not None and prev_fim is not None:
        volume_anterior = await _scalar_sum_volume(
            db, tenant_id, filters, prev_inicio, prev_fim
        )
        n_ops_anterior = await _scalar_count_ops(
            db, tenant_id, filters, prev_inicio, prev_fim
        )
        n_titulos_anterior = await _scalar_sum_titulos(
            db, tenant_id, filters, prev_inicio, prev_fim
        )

    volume_delta_pct = (
        _safe_pct_change(volume_total, volume_anterior)
        if volume_anterior is not None
        else None
    )
    ticket_anterior = (
        (volume_anterior / n_ops_anterior)
        if (volume_anterior is not None and n_ops_anterior is not None and n_ops_anterior > 0)
        else None
    )
    ticket_delta_pct = (
        _safe_pct_change(ticket_medio, ticket_anterior)
        if ticket_anterior is not None
        else None
    )
    ticket_titulo_anterior = (
        (volume_anterior / n_titulos_anterior)
        if (
            volume_anterior is not None
            and n_titulos_anterior is not None
            and n_titulos_anterior > 0
        )
        else None
    )
    ticket_medio_titulo_delta_pct = (
        _safe_pct_change(ticket_medio_titulo, ticket_titulo_anterior)
        if ticket_titulo_anterior is not None
        else None
    )

    comparacao_label_pt = _fmt_comparacao_label_pt(prev_inicio, prev_fim)

    # Produto lider — maior fatia % no periodo atual, com delta vs periodo anterior.
    if prod and volume_total > 0:
        top_row = prod[0]
        produto_lider_sigla = str(top_row.categoria_id or "(n/d)")
        produto_lider_pct = _as_float(top_row.valor) / volume_total * 100
        prev_total = sum(prod_prev.values())
        if prev_total > 0 and produto_lider_sigla in prod_prev:
            prev_pct = prod_prev[produto_lider_sigla] / prev_total * 100
            produto_lider_delta_pp = produto_lider_pct - prev_pct
        else:
            produto_lider_delta_pp = None
    else:
        produto_lider_sigla = "—"
        produto_lider_pct = 0.0
        produto_lider_delta_pp = None

    # Sparklines — sempre 12M corridos terminando em periodo_fim (ou hoje).
    spark_end = periodo_fim or date.today()
    spark_start = _shift_year_back(
        spark_end.replace(day=1), spark_end
    )[0] or spark_end
    # Queremos 12M: do 1o dia do mes de (end - 12M) ate end
    spark_start = spark_end.replace(day=1)
    # volta 11 meses para ter 12 pontos mensais incluindo o de end
    y, m = spark_start.year, spark_start.month - 11
    while m <= 0:
        m += 12
        y -= 1
    spark_start = date(y, m, 1)

    spark_filters = {
        **filters,
        "periodo_inicio": spark_start,
        "periodo_fim": spark_end,
        # sparklines ignoram filtros categoricos? Nao — mantem produto/ua.
        # O sparkline reflete a mesma "fatia" que o KPI mostra.
    }

    spark_vol_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **spark_filters,
    )
    spark_vol = (await db.execute(spark_vol_stmt)).all()

    spark_ops_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            func.count(Operacao.id).label("valor"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **spark_filters,
    )
    spark_ops = (await db.execute(spark_ops_stmt)).all()

    # Sparkline de ticket = vol / ops por mes
    vol_by_month = {r.periodo: _as_float(r.valor) for r in spark_vol}
    ops_by_month = {r.periodo: int(r.valor) for r in spark_ops}
    spark_ticket_pts = []
    for m_date, v in vol_by_month.items():
        q = ops_by_month.get(m_date, 0)
        spark_ticket_pts.append(
            Point(periodo=m_date, valor=(v / q) if q > 0 else 0.0)
        )

    # Sparkline de ticket por titulo = vol / qtd_titulos por mes (12M)
    spark_tits_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            func.coalesce(func.sum(Operacao.quantidade_de_titulos), 0).label("valor"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **spark_filters,
    )
    spark_tits = (await db.execute(spark_tits_stmt)).all()
    tits_by_month_spark = {r.periodo: int(r.valor) for r in spark_tits}
    spark_ticket_titulo_pts = [
        Point(
            periodo=m_date,
            valor=(v / tits_by_month_spark.get(m_date, 0))
            if tits_by_month_spark.get(m_date, 0) > 0
            else 0.0,
        )
        for m_date, v in vol_by_month.items()
    ]

    # Sparkline de "produto_lider": % do produto-lider mes a mes
    # Calcular fatia do produto-lider (sigla definida acima) em cada mes
    if produto_lider_sigla != "—":
        spark_lider_stmt = _apply_filters(
            select(
                cast(bucket, Date).label("periodo"),
                _produto_expr().label("categoria_id"),
                func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            )
            .group_by(bucket, _produto_expr())
            .order_by(bucket),
            tenant_id=tenant_id,
            **spark_filters,
        )
        spark_lider_rows = (await db.execute(spark_lider_stmt)).all()
        # Agregar por mes: valor_lider / valor_total
        totals_by_month: dict[date, float] = {}
        lider_by_month: dict[date, float] = {}
        for r in spark_lider_rows:
            v = _as_float(r.valor)
            totals_by_month[r.periodo] = totals_by_month.get(r.periodo, 0.0) + v
            if str(r.categoria_id or "") == produto_lider_sigla:
                lider_by_month[r.periodo] = v
        spark_lider_pts = [
            Point(
                periodo=p,
                valor=(lider_by_month.get(p, 0.0) / totals_by_month[p] * 100)
                if totals_by_month.get(p, 0.0) > 0
                else 0.0,
            )
            for p in sorted(totals_by_month.keys())
        ]
    else:
        spark_lider_pts = []

    # Nome completo do produto lider ("Faturizacao" vs "FAT") — lookup em
    # `wh_dim_produto`. Se o produto nao existir no dim (edge case: ETL
    # fora de sync), expoe `None` e UI cai para a sigla.
    produto_lider_nome: str | None = None
    if produto_lider_sigla != "—":
        prod_nomes = await _produto_sigla_to_nome_map(db, tenant_id)
        produto_lider_nome = prod_nomes.get(produto_lider_sigla)

    resumo_deltas = VolumeResumoDeltas(
        volume_total=volume_total,
        volume_delta_pct=volume_delta_pct,
        volume_sparkline_12m=[
            Point(periodo=r.periodo, valor=_as_float(r.valor)) for r in spark_vol
        ],
        ticket_medio=ticket_medio,
        ticket_delta_pct=ticket_delta_pct,
        ticket_sparkline_12m=spark_ticket_pts,
        ticket_medio_titulo=ticket_medio_titulo,
        ticket_medio_titulo_delta_pct=ticket_medio_titulo_delta_pct,
        ticket_medio_titulo_sparkline_12m=spark_ticket_titulo_pts,
        produto_lider_sigla=produto_lider_sigla,
        produto_lider_nome=produto_lider_nome,
        produto_lider_pct=produto_lider_pct,
        produto_lider_delta_pp=produto_lider_delta_pp,
        produto_lider_sparkline_12m=spark_lider_pts,
        comparacao_label_pt=comparacao_label_pt,
    )

    # ─────────────────────────────────────────────────────────────
    # Top cedentes — Onda 2 (wh_operacao nao tem cedente_id direto;
    # precisa join com wh_operacao_item + wh_titulo_snapshot). Por enquanto
    # lista vazia; frontend exibe placeholder "em breve".
    # ─────────────────────────────────────────────────────────────
    top_cedentes: list[TopCedenteItem] = []

    # Montagem final.
    data = SeriesEVolume(
        evolucao=_points(evo),
        evolucao_por_produto=[
            PointDim(
                periodo=r.periodo.isoformat(),
                categoria_id=str(r.categoria_id or "(n/d)"),
                categoria=str(r.categoria_id or "(n/d)"),
                valor=_as_float(r.valor),
            )
            for r in evo_prod
        ],
        evolucao_por_ua=[
            PointDim(
                periodo=r.periodo.isoformat(),
                categoria_id=str(int(r.ua_id)) if r.ua_id is not None else "0",
                categoria=(
                    ua_nomes.get(int(r.ua_id), f"UA {int(r.ua_id)}")
                    if r.ua_id is not None
                    else "(n/d)"
                ),
                valor=_as_float(r.valor),
            )
            for r in evo_ua
        ],
        por_produto=[
            CategoryValueDelta(
                categoria=str(r.categoria_id or "(n/d)"),
                categoria_id=str(r.categoria_id or "(n/d)"),
                valor=_as_float(r.valor),
                quantidade=int(r.quantidade),
                delta_pct=_safe_pct_change(
                    _as_float(r.valor),
                    prod_prev.get(str(r.categoria_id or "(n/d)"), 0.0),
                ),
                # Detalhamento analitico (exclusivo do L3 Volume > por_produto).
                taxa_media_pct=_as_float(r.taxa),
                prazo_medio_dias=_as_float(r.prazo),
                tendencia_90d=spark90_by_sigla.get(
                    str(r.categoria_id or "(n/d)"), []
                ),
                tendencia_90d_delta_pct=_safe_pct_change(
                    spark90_curr_by_sigla.get(str(r.categoria_id or "(n/d)"), 0.0),
                    spark90_prev_by_sigla.get(str(r.categoria_id or "(n/d)"), 0.0),
                ),
            )
            for r in prod
        ],
        por_ua=[
            CategoryValueDelta(
                categoria=(
                    ua_nomes.get(int(r.ua_id), f"UA {int(r.ua_id)}")
                    if r.ua_id is not None
                    else "(n/d)"
                ),
                categoria_id=str(int(r.ua_id)) if r.ua_id is not None else "0",
                valor=_as_float(r.valor),
                quantidade=int(r.quantidade),
                delta_pct=_safe_pct_change(
                    _as_float(r.valor), ua_prev.get(int(r.ua_id), 0.0)
                )
                if r.ua_id is not None
                else None,
            )
            for r in ua
        ],
        top_cedentes=top_cedentes,
        resumo=resumo_deltas,
        evolucao_taxa_media=_points(evo_taxa),
        evolucao_prazo_medio=_points(evo_prazo),
        evolucao_ticket_medio=_points(evo_ticket),
    )
    provenance = await _build_provenance(db, tenant_id, filters)
    return data, provenance


async def get_taxa(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[SeriesETaxa, Provenance]:
    """L3 Taxa — taxa de juros media ponderada por volume."""
    bucket = func.date_trunc("month", Operacao.data_de_efetivacao)

    evo_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("valor"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **filters,
    )
    evo = (await db.execute(evo_stmt)).all()

    prod_stmt = _apply_filters(
        select(
            _produto_expr().label("categoria"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("valor"),
            func.count(Operacao.id).label("quantidade"),
        )
        .group_by(_produto_expr())
        .order_by(_produto_expr()),
        tenant_id=tenant_id,
        **filters,
    )
    prod = (await db.execute(prod_stmt)).all()

    mod_stmt = _apply_filters(
        select(
            Operacao.modalidade.label("categoria"),
            _weighted_avg(Operacao.taxa_de_juros, Operacao.total_bruto).label("valor"),
            func.count(Operacao.id).label("quantidade"),
        )
        .group_by(Operacao.modalidade)
        .order_by(Operacao.modalidade),
        tenant_id=tenant_id,
        **filters,
    )
    mod = (await db.execute(mod_stmt)).all()

    data = SeriesETaxa(
        evolucao=_points(evo),
        por_produto=_categories(prod),
        por_modalidade=_categories(mod),
    )
    provenance = await _build_provenance(db, tenant_id, filters)
    return data, provenance


async def get_prazo(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[SeriesEPrazo, Provenance]:
    """L3 Prazo — prazo medio real ponderado por volume."""
    bucket = func.date_trunc("month", Operacao.data_de_efetivacao)

    evo_stmt = _apply_filters(
        select(
            cast(bucket, Date).label("periodo"),
            _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("valor"),
        )
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **filters,
    )
    evo = (await db.execute(evo_stmt)).all()

    prod_stmt = _apply_filters(
        select(
            _produto_expr().label("categoria"),
            _weighted_avg(Operacao.prazo_medio_real, Operacao.total_bruto).label("valor"),
            func.count(Operacao.id).label("quantidade"),
        )
        .group_by(_produto_expr())
        .order_by(_produto_expr()),
        tenant_id=tenant_id,
        **filters,
    )
    prod = (await db.execute(prod_stmt)).all()

    data = SeriesEPrazo(evolucao=_points(evo), por_produto=_categories(prod))
    provenance = await _build_provenance(db, tenant_id, filters)
    return data, provenance


async def get_ticket(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[SeriesETicket, Provenance]:
    """L3 Ticket — volume bruto / numero de operacoes."""
    bucket = func.date_trunc("month", Operacao.data_de_efetivacao)

    ticket_expr = cast(
        func.sum(Operacao.total_bruto) / func.nullif(func.count(Operacao.id), 0),
        Numeric(18, 4),
    )

    evo_stmt = _apply_filters(
        select(cast(bucket, Date).label("periodo"), ticket_expr.label("valor"))
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **filters,
    )
    evo = (await db.execute(evo_stmt)).all()

    prod_stmt = _apply_filters(
        select(
            _produto_expr().label("categoria"),
            ticket_expr.label("valor"),
            func.count(Operacao.id).label("quantidade"),
        )
        .group_by(_produto_expr())
        .order_by(ticket_expr.desc()),
        tenant_id=tenant_id,
        **filters,
    )
    prod = (await db.execute(prod_stmt)).all()

    # Top 10 cedentes por ticket medio (filtra >= 3 operacoes para ter estabilidade)
    ced_stmt = _apply_filters(
        select(
            cast(Operacao.conta_operacional_id, Numeric).label("categoria"),
            ticket_expr.label("valor"),
            func.count(Operacao.id).label("quantidade"),
        )
        .group_by(Operacao.conta_operacional_id)
        .having(func.count(Operacao.id) >= 3)
        .order_by(ticket_expr.desc())
        .limit(10),
        tenant_id=tenant_id,
        **filters,
    )
    ced = (await db.execute(ced_stmt)).all()

    data = SeriesETicket(
        evolucao=_points(evo),
        por_produto=_categories(prod),
        por_cedente_top=[
            CategoryValue(
                categoria=f"Conta {int(r.categoria)}",
                valor=_as_float(r.valor),
                quantidade=int(r.quantidade),
            )
            for r in ced
        ],
    )
    provenance = await _build_provenance(db, tenant_id, filters)
    return data, provenance


async def get_receita(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[SeriesEReceita, Provenance]:
    """L3 Receita contratada — juros + tarifas contratadas no ato da operacao."""
    bucket = func.date_trunc("month", Operacao.data_de_efetivacao)

    receita_expr = (
        func.coalesce(func.sum(Operacao.total_de_juros), 0)
        + func.coalesce(func.sum(Operacao.total_das_consultas_financeiras), 0)
        + func.coalesce(func.sum(Operacao.total_dos_registros_bancarios), 0)
        + func.coalesce(func.sum(Operacao.total_das_consultas_fiscais), 0)
        + func.coalesce(func.sum(Operacao.total_dos_comunicados_de_cessao), 0)
        + func.coalesce(func.sum(Operacao.total_dos_documentos_digitais), 0)
    )

    evo_stmt = _apply_filters(
        select(cast(bucket, Date).label("periodo"), receita_expr.label("valor"))
        .group_by(bucket)
        .order_by(bucket),
        tenant_id=tenant_id,
        **filters,
    )
    evo = (await db.execute(evo_stmt)).all()

    # Por componente: extrai cada parcela sum'ada uma vez
    comp_stmt = _apply_filters(
        select(
            func.coalesce(func.sum(Operacao.total_de_juros), 0).label("juros"),
            func.coalesce(func.sum(Operacao.total_das_consultas_financeiras), 0).label("cf"),
            func.coalesce(func.sum(Operacao.total_dos_registros_bancarios), 0).label("rb"),
            func.coalesce(func.sum(Operacao.total_das_consultas_fiscais), 0).label("cfi"),
            func.coalesce(func.sum(Operacao.total_dos_comunicados_de_cessao), 0).label("cc"),
            func.coalesce(func.sum(Operacao.total_dos_documentos_digitais), 0).label("dd"),
        ),
        tenant_id=tenant_id,
        **filters,
    )
    comp_row = (await db.execute(comp_stmt)).one()
    componentes = [
        CategoryValue(categoria="Juros", valor=_as_float(comp_row.juros)),
        CategoryValue(categoria="Consulta financeira", valor=_as_float(comp_row.cf)),
        CategoryValue(categoria="Registros bancarios", valor=_as_float(comp_row.rb)),
        CategoryValue(categoria="Consulta fiscal", valor=_as_float(comp_row.cfi)),
        CategoryValue(categoria="Comunicado cessao", valor=_as_float(comp_row.cc)),
        CategoryValue(categoria="Documentos digitais", valor=_as_float(comp_row.dd)),
    ]
    # remove zero
    componentes = [c for c in componentes if c.valor > 0]

    prod_stmt = _apply_filters(
        select(
            _produto_expr().label("categoria"),
            receita_expr.label("valor"),
            func.count(Operacao.id).label("quantidade"),
        )
        .group_by(_produto_expr())
        .order_by(receita_expr.desc()),
        tenant_id=tenant_id,
        **filters,
    )
    prod = (await db.execute(prod_stmt)).all()

    data = SeriesEReceita(
        evolucao=_points(evo),
        por_componente=componentes,
        por_produto=_categories(prod),
    )
    provenance = await _build_provenance(db, tenant_id, filters)
    return data, provenance


async def get_dia_util(
    db: AsyncSession, tenant_id: UUID, filters: dict[str, Any]
) -> tuple[SeriesEDiaUtil, Provenance]:
    """L3 Dia util — distribuicao de efetivacao por dia do mes / dia da semana.

    Proxy de "dia util" aqui e o `EXTRACT(day FROM data_de_efetivacao)`.
    Classificacao formal de dia util (ANBIMA) vai para sprint posterior.
    """
    dia_mes = func.extract("day", Operacao.data_de_efetivacao)
    dow = func.extract("isodow", Operacao.data_de_efetivacao)  # 1=Mon, 7=Sun

    # Por dia do mes — devolvemos como Point usando uma "data sintetica" do dia corrente
    # so para caber no schema Point{periodo,valor}. Frontend renderiza como categoria numerica.
    dia_stmt = _apply_filters(
        select(
            dia_mes.label("dia"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
        )
        .group_by(dia_mes)
        .order_by(dia_mes),
        tenant_id=tenant_id,
        **filters,
    )
    dia_rows = (await db.execute(dia_stmt)).all()
    por_dia = [
        Point(periodo=date(2000, 1, int(r.dia)), valor=_as_float(r.valor))
        for r in dia_rows
        if r.dia is not None
    ]

    dow_stmt = _apply_filters(
        select(
            dow.label("dow"),
            func.coalesce(func.sum(Operacao.total_bruto), 0).label("valor"),
            func.count(Operacao.id).label("quantidade"),
        )
        .group_by(dow)
        .order_by(dow),
        tenant_id=tenant_id,
        **filters,
    )
    dow_rows = (await db.execute(dow_stmt)).all()
    labels = {
        1: "Segunda",
        2: "Terca",
        3: "Quarta",
        4: "Quinta",
        5: "Sexta",
        6: "Sabado",
        7: "Domingo",
    }
    por_dow = [
        CategoryValue(
            categoria=labels.get(int(r.dow), "(n/d)"),
            valor=_as_float(r.valor),
            quantidade=int(r.quantidade),
        )
        for r in dow_rows
        if r.dow is not None
    ]

    data = SeriesEDiaUtil(por_dia_util=por_dia, por_dia_semana=por_dow)
    provenance = await _build_provenance(db, tenant_id, filters)
    return data, provenance
