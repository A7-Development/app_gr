"""One-shot scan de gaps historicos -- enfileira backfill_jobs.

Dois modos:

**(1) MODO COVERAGE (default) -- usa get_source_coverage**

Detecta gaps via coverage service (mesma logica do watermark scanner, range
default 730d). Respeita `before_first_sync`: dias anteriores ao primeiro
fetched_at de um endpoint nao sao tratados como gap.

Uso pra cura recente:
    .venv\\Scripts\\python.exe scripts/oneshot_backfill_freshness.py \\
        --tenant-id <uuid> --source admin:qitech --range-days 365

**(2) MODO HISTORICO -- usa wh_dim_dia_util como ancora**

Quando `--from-date` e passado, IGNORA before_first_sync e usa o calendario
de dias uteis (`wh_dim_dia_util`) como ancora. Para cada endpoint:
    target_dates = DUs no range [from..to]
    gap_dates    = target_dates - dias_ja_com_http_200
    enfileira gap_dates como backfill_job

Necessario pra ingestao "tudo desde 2021" -- modo coverage nao alcanca
porque o periodo inteiro vira `before_first_sync` quando o endpoint ainda
nao tinha sido configurado.

Uso pra historico completo:
    .venv\\Scripts\\python.exe scripts/oneshot_backfill_freshness.py \\
        --tenant-id <uuid> --source admin:qitech \\
        --from-date 2021-01-01 --invoked-by ricardo

    # Limitar a 1 endpoint:
    .venv\\Scripts\\python.exe scripts/oneshot_backfill_freshness.py \\
        --tenant-id <uuid> --source admin:qitech \\
        --from-date 2021-01-01 --only market.outros_fundos --dry-run

    # Familia inteira via prefixo:
    .venv\\Scripts\\python.exe scripts/oneshot_backfill_freshness.py \\
        --tenant-id <uuid> --source admin:qitech \\
        --from-date 2021-01-01 --only "market.*" --dry-run

Idempotente: re-rodar so adiciona o que ainda nao tem 200. Pula endpoints
com backfill pending/running ja em andamento.

Tempo esperado em modo historico 2021->hoje (10 market.* x ~1300 DUs =
~13000 chamadas):
    - backfill_worker em INTERVAL_SECONDS=5 (default): ~18h drenando
    - backfill_worker em INTERVAL_SECONDS=1 (acelerado): ~3.6h drenando
Pra acelerar temporariamente, editar `app/scheduler/jobs/backfill_worker.py`
linha 23 (`INTERVAL_SECONDS = 1`) + `systemctl restart gr-api`, e reverter
depois.

Args:
    --tenant-id <uuid>      OBRIGATORIO. Tenant alvo.
    --source <slug>         OBRIGATORIO. Source slug (ex.: admin:qitech).
    --range-days <int>      Modo coverage. Default 730 (=MAX_RANGE_DAYS).
    --from-date <date>      Modo historico. Ativa modo historico.
    --to-date <date>        Modo historico. Default = hoje (UTC).
    --only <pattern>        Filtro de endpoint. Suporta sufixo "*" pra
                            familia (ex.: "market.*").
    --invoked-by <str>      Default "cli:oneshot". Vai em backfill_job.created_by.
    --dry-run               Lista gaps sem criar backfill_job.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text

# Side-effect imports (registry SQLAlchemy completo).
import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.coverage import (
    fetch_qitech_coverage,
    qitech_endpoint_supports_coverage,
)
from app.modules.integracoes.models.tenant_source_endpoint_config import (
    TenantSourceEndpointConfig,
)
from app.modules.integracoes.services.backfill_service import (
    create_backfill_job,
    list_active_backfill_jobs,
)
from app.modules.integracoes.services.coverage import (
    CoverageStatus,
    get_source_coverage,
)


def _parse_date(s: str | None) -> date | None:
    if s is None:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


# Endpoints com fluxo assincrono (request -> webhook callback) — excluidos
# do batch por default. Regra explicita do projeto: "tudo assincrono roda
# separado" -- batches grandes de assincronos podem inflar fila de jobs
# do vendor mais rapido do que o callback drena, e geram ruido no monitor.
# Pra rodar SO assincronos: --include-async --only market.fidc_estoque
#
# YAGNI: hardcode aqui ate aparecer 2o adapter assincrono — quando aparecer,
# promover pra flag `is_async` em `EndpointSpec` (app/shared/endpoint_catalog.py).
_ASYNC_ENDPOINTS: frozenset[str] = frozenset({"market.fidc_estoque"})


def _matches_only(endpoint_name: str, only: str | None) -> bool:
    """Filtro --only com suporte a sufixo `*` (ex.: 'market.*')."""
    if only is None:
        return True
    if only.endswith("*"):
        return endpoint_name.startswith(only[:-1])
    return endpoint_name == only


async def _list_all_dates_in_range(
    db, *, tenant_id: UUID, start: date, end: date
) -> list[date]:
    """Le wh_dim_dia_util e devolve TODOS os dias no range (DU + fds + feriado).

    Por que NAO filtrar fds/feriado (decisao 2026-05-15, Ricardo):

        Manter a regra "raw e a fonte unica da verdade do que existe". O
        scheduler diario (`daily_at`) ja chama em fds/feriado e o vendor
        responde com 400-envelope-vazio -- isso vira raw classificada como
        `not_published` no coverage. Pra o backfill historico ficar
        consistente com o recente, precisa chamar em TODOS os dias tambem
        -- senao fds antigo aparece como `weekend` (calendario) e fds
        recente como `not_published` (raw), confundindo o operador.

        Custo: ~30% chamadas extras (fds + feriado em 4.5 anos =~ 700 dias
        a mais por endpoint). Aceitavel pra QiTech (custo zero). Em fontes
        pagas (Serasa) reavaliar -- talvez criar flag `--skip-weekends`
        opt-in.

    Pra incluir/excluir fds/feriado, o filtro fica visivel via output
    do script (mostrar contadores DU/FDS/feriado separadamente seria
    melhoria futura).
    """
    sql = text(
        """
        SELECT data
        FROM wh_dim_dia_util
        WHERE tenant_id = :tenant_id
          AND data BETWEEN :start AND :end
        ORDER BY data
        """
    )
    rows = await db.execute(
        sql, {"tenant_id": tenant_id, "start": start, "end": end}
    )
    return [r[0] for r in rows.all()]


async def _dates_ja_ok(
    db,
    *,
    endpoint_name: str,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    start: date,
    end: date,
) -> set[date]:
    """Datas que ja tem raw com http_status=200 (sucesso real).

    `not_published` (4xx-as-row) NAO conta como ok -- queremos re-tentar.
    Mas se o endpoint estiver com 401/403 cronico, vai falhar de novo
    e ficar em `dates_failed` do backfill_job, sem reenfileirar eternamente.
    """
    rows = await fetch_qitech_coverage(
        db,
        endpoint_name=endpoint_name,
        tenant_id=tenant_id,
        unidade_administrativa_id=unidade_administrativa_id,
        start_date=start,
        end_date=end,
    )
    return {
        r.data_posicao
        for r in rows
        if r.http_status is not None and 200 <= r.http_status < 300
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--source", required=True, help="ex.: admin:qitech")
    parser.add_argument("--range-days", type=int, default=730)
    parser.add_argument("--from-date", default=None, help="modo historico")
    parser.add_argument("--to-date", default=None, help="modo historico (default hoje)")
    parser.add_argument("--only", default=None, help="filtro: 'market.*' ou 'market.cpr'")
    parser.add_argument(
        "--include-async",
        action="store_true",
        help=(
            "Inclui endpoints assincronos (request->webhook). Default exclui. "
            f"Hoje: {sorted(_ASYNC_ENDPOINTS)}"
        ),
    )
    parser.add_argument("--invoked-by", default="cli:oneshot")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        tenant_id = UUID(args.tenant_id)
    except ValueError:
        print(f"ERRO: --tenant-id invalido: {args.tenant_id!r}", file=sys.stderr)
        return 2

    try:
        source_type = SourceType(args.source)
    except ValueError:
        valid = ", ".join(s.value for s in SourceType)
        print(f"ERRO: --source invalido: {args.source!r}. Validos: {valid}", file=sys.stderr)
        return 2

    try:
        from_date = _parse_date(args.from_date)
        to_date = _parse_date(args.to_date) or datetime.now(UTC).date()
    except ValueError as e:
        print(f"ERRO: data invalida: {e}", file=sys.stderr)
        return 2

    historic_mode = from_date is not None
    if historic_mode and from_date > to_date:
        print("ERRO: --from-date > --to-date", file=sys.stderr)
        return 2

    summary: dict[str, Any] = {
        "endpoints_scanned": 0,
        "endpoints_with_gaps": 0,
        "endpoints_skipped_active_job": 0,
        "endpoints_skipped_only_filter": 0,
        "endpoints_skipped_async": 0,
        "jobs_created": 0,
        "total_gap_dates": 0,
        "errors": [],
    }

    async with AsyncSessionLocal() as db:
        stmt = select(TenantSourceEndpointConfig).where(
            TenantSourceEndpointConfig.tenant_id == tenant_id,
            TenantSourceEndpointConfig.source_type == source_type,
            TenantSourceEndpointConfig.enabled.is_(True),
            TenantSourceEndpointConfig.environment == Environment.PRODUCTION,
            TenantSourceEndpointConfig.schedule_kind != "on_demand",
        )
        configs = list((await db.execute(stmt)).scalars().all())

        if not configs:
            print(
                f"Nenhum endpoint TSEC enabled+production+!on_demand "
                f"pra tenant={tenant_id} source={source_type.value}",
                file=sys.stderr,
            )
            return 1

        # Filtros: --only + exclusao de assincronos (a menos que --include-async).
        filtered = []
        for cfg in configs:
            if not _matches_only(cfg.endpoint_name, args.only):
                summary["endpoints_skipped_only_filter"] += 1
                continue
            if (
                cfg.endpoint_name in _ASYNC_ENDPOINTS
                and not args.include_async
            ):
                summary["endpoints_skipped_async"] += 1
                continue
            filtered.append(cfg)
        configs = filtered

        if not configs:
            reason = (
                f"--only {args.only!r}" if args.only else "filtros aplicados"
            )
            print(
                f"Nenhum endpoint sobrou apos {reason} "
                f"(skipped_filter={summary['endpoints_skipped_only_filter']}, "
                f"skipped_async={summary['endpoints_skipped_async']}). "
                "Pra incluir assincronos: --include-async.",
                file=sys.stderr,
            )
            return 1

        groups: dict[UUID | None, list[TenantSourceEndpointConfig]] = defaultdict(list)
        for cfg in configs:
            groups[cfg.unidade_administrativa_id].append(cfg)

        mode_label = f"HISTORICO ({from_date} -> {to_date})" if historic_mode else f"COVERAGE (range_days={args.range_days})"
        print(f"\n=== Modo: {mode_label} ===")
        if args.only:
            print(f"=== Filtro --only: {args.only} ===")

        for ua_id, cfgs_in_group in groups.items():
            print(
                f"\n--- Grupo: tenant={tenant_id} source={source_type.value} ua={ua_id} ---"
            )
            if historic_mode:
                await _scan_group_historic(
                    db,
                    tenant_id=tenant_id,
                    source_type=source_type,
                    ua_id=ua_id,
                    cfgs=cfgs_in_group,
                    from_date=from_date,
                    to_date=to_date,
                    invoked_by=args.invoked_by,
                    dry_run=args.dry_run,
                    summary=summary,
                )
            else:
                await _scan_group_coverage(
                    db,
                    tenant_id=tenant_id,
                    source_type=source_type,
                    ua_id=ua_id,
                    cfgs=cfgs_in_group,
                    range_days=args.range_days,
                    invoked_by=args.invoked_by,
                    dry_run=args.dry_run,
                    summary=summary,
                )

    mode = "DRY-RUN" if args.dry_run else "EXECUTADO"
    print(f"\n=== Resumo ({mode}) ===")
    print(f"  endpoints_scanned        = {summary['endpoints_scanned']}")
    print(f"  endpoints_with_gaps      = {summary['endpoints_with_gaps']}")
    print(f"  endpoints_skipped_active = {summary['endpoints_skipped_active_job']}")
    print(f"  endpoints_skipped_filter = {summary['endpoints_skipped_only_filter']}")
    print(f"  endpoints_skipped_async  = {summary['endpoints_skipped_async']}")
    print(f"  jobs_created             = {summary['jobs_created']}")
    print(f"  total_gap_dates          = {summary['total_gap_dates']}")
    print(f"  errors                   = {len(summary['errors'])}")
    for err in summary["errors"]:
        print(f"    - {err}")

    if args.dry_run:
        print(
            "\nDRY-RUN: nenhum backfill_job criado. "
            "Re-rode sem --dry-run pra enfileirar."
        )

    return 0 if not summary["errors"] else 1


async def _scan_group_coverage(
    db,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    ua_id: UUID | None,
    cfgs: list[TenantSourceEndpointConfig],
    range_days: int,
    invoked_by: str,
    dry_run: bool,
    summary: dict[str, Any],
) -> None:
    """Modo coverage: usa get_source_coverage (respeita before_first_sync)."""
    try:
        coverage = await get_source_coverage(
            db,
            source_type=source_type,
            tenant_id=tenant_id,
            unidade_administrativa_id=ua_id,
            range_days=range_days,
        )
    except Exception as e:
        msg = f"coverage_fetch ua={ua_id}: {type(e).__name__}: {e}"
        summary["errors"].append(msg)
        print(f"  ERRO: {msg}", file=sys.stderr)
        return

    coverage_by_name = {e.name: e for e in coverage.endpoints}
    print(f"  range = {coverage.start_date} -> {coverage.end_date}")

    for cfg in cfgs:
        summary["endpoints_scanned"] += 1
        ep = coverage_by_name.get(cfg.endpoint_name)

        if ep is None or not ep.supported:
            print(f"  - {cfg.endpoint_name:<40} unsupported")
            continue
        if ep.count_gap <= 0:
            print(
                f"  - {cfg.endpoint_name:<40} ok={ep.count_ok:<4} "
                f"part={ep.count_partial:<3} np={ep.count_not_published:<3} gap=0"
            )
            continue

        gap_dates = [d.data for d in ep.days if d.status == CoverageStatus.GAP]
        await _maybe_enqueue(
            db,
            cfg=cfg,
            gap_dates=gap_dates,
            invoked_by=invoked_by,
            dry_run=dry_run,
            summary=summary,
        )


async def _scan_group_historic(
    db,
    *,
    tenant_id: UUID,
    source_type: SourceType,
    ua_id: UUID | None,
    cfgs: list[TenantSourceEndpointConfig],
    from_date: date,
    to_date: date,
    invoked_by: str,
    dry_run: bool,
    summary: dict[str, Any],
) -> None:
    """Modo historico: usa wh_dim_dia_util como ancora (ignora before_first_sync).

    Pra cada endpoint, target = TODOS os dias no range (DU + fds + feriado);
    gap = target - dias_ja_com_200. Ver docstring de
    `_list_all_dates_in_range` para o porque incluir fds/feriado.
    """
    all_dates = await _list_all_dates_in_range(
        db, tenant_id=tenant_id, start=from_date, end=to_date
    )
    if not all_dates:
        msg = f"Nenhum dia no range {from_date}..{to_date} (wh_dim_dia_util populado?)"
        summary["errors"].append(msg)
        print(f"  ERRO: {msg}", file=sys.stderr)
        return

    target_set = set(all_dates)
    print(f"  range = {from_date} -> {to_date} ({len(all_dates)} dias - inclui fds/feriado)")

    for cfg in cfgs:
        summary["endpoints_scanned"] += 1
        if not qitech_endpoint_supports_coverage(cfg.endpoint_name):
            print(f"  - {cfg.endpoint_name:<40} unsupported (sem coverage helper)")
            continue

        ja_ok = await _dates_ja_ok(
            db,
            endpoint_name=cfg.endpoint_name,
            tenant_id=tenant_id,
            unidade_administrativa_id=ua_id,
            start=from_date,
            end=to_date,
        )
        gap_dates = sorted(target_set - ja_ok)
        n_ok = len(ja_ok & target_set)
        if not gap_dates:
            print(
                f"  - {cfg.endpoint_name:<40} dias={len(all_dates):<4} "
                f"ok={n_ok:<4} gap=0"
            )
            continue

        print(
            f"  - {cfg.endpoint_name:<40} dias={len(all_dates):<4} "
            f"ok={n_ok:<4} gap={len(gap_dates)}",
            end="",
        )
        await _maybe_enqueue(
            db,
            cfg=cfg,
            gap_dates=gap_dates,
            invoked_by=invoked_by,
            dry_run=dry_run,
            summary=summary,
            inline=True,
        )


async def _maybe_enqueue(
    db,
    *,
    cfg: TenantSourceEndpointConfig,
    gap_dates: list[date],
    invoked_by: str,
    dry_run: bool,
    summary: dict[str, Any],
    inline: bool = False,
) -> None:
    """Decide se enfileira backfill_job; pula se ha job ativo da mesma chave."""
    if not gap_dates:
        return

    summary["endpoints_with_gaps"] += 1
    summary["total_gap_dates"] += len(gap_dates)

    # Dedupe vs backfill ativo da mesma chave.
    active = await list_active_backfill_jobs(
        db,
        tenant_id=cfg.tenant_id,
        source_type=cfg.source_type,
        endpoint_name=cfg.endpoint_name,
    )
    active_same_ua = [
        j for j in active
        if j.unidade_administrativa_id == cfg.unidade_administrativa_id
    ]
    line_prefix = "" if inline else f"  - {cfg.endpoint_name:<40} gaps={len(gap_dates):<4} "

    if active_same_ua:
        summary["endpoints_skipped_active_job"] += 1
        active_ids = ", ".join(str(j.id) for j in active_same_ua)
        msg = f"SKIP (backfill ativo: {active_ids})"
        print(f"{line_prefix}{msg}" if not inline else f" {msg}")
        return

    if dry_run:
        first_5 = ", ".join(d.isoformat() for d in gap_dates[:5])
        more = f" (+{len(gap_dates) - 5} mais)" if len(gap_dates) > 5 else ""
        msg = f"DRY-RUN: [{first_5}{more}]"
        print(f"{line_prefix}{msg}" if not inline else f" {msg}")
        return

    try:
        job = await create_backfill_job(
            db,
            tenant_id=cfg.tenant_id,
            source_type=cfg.source_type,
            environment=cfg.environment,
            unidade_administrativa_id=cfg.unidade_administrativa_id,
            endpoint_name=cfg.endpoint_name,
            dates=gap_dates,
            created_by=invoked_by,
        )
        summary["jobs_created"] += 1
        msg = f"ENFILEIRADO job={job.id}"
        print(f"{line_prefix}{msg}" if not inline else f" {msg}")
    except Exception as e:
        msg = f"{cfg.endpoint_name}: {type(e).__name__}: {e}"
        summary["errors"].append(msg)
        err_msg = f"ERRO: {msg}"
        print(f"{line_prefix}{err_msg}" if not inline else f" {err_msg}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
