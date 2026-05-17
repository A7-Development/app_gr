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
