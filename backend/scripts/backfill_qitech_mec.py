"""Backfill QiTech MEC: sync dia a dia entre --start e --end (so o endpoint MEC).

Variante focada do `backfill_qitech_2026.py`: chama apenas `sync_mec` em vez
de `sync_all`. Default desde 2021-01-01 ate ontem (D-1 UTC). Importante para
analises evolutivas de cota (variacao mensal/anual/total ao longo dos anos).

Pipeline por dia (id`entico ao do scheduler em prod):
    fetch /netreport/report/market/mec/{aaaa-mm-dd}
        -> upsert wh_qitech_raw_relatorio (raw / bronze)
        -> map_mec(payload, ...) -> rows
        -> bulk upsert wh_mec_evolucao_cotas (silver / canonico)

Idempotente: re-rodar um dia ja processado faz upsert (raw atualiza
`fetched_at` + `payload_sha256`; silver atualiza colunas via UQ
`(tenant_id, source_id)`). Fim de semana / feriado: QiTech devolve 400 com
shape canonico de "sem resultados" — o adapter trata como sucesso vazio.

Multi-UA: se --ua nao for passado, itera TODAS as UAs do tenant com config
QiTech em production. Loop externo = UA, loop interno = dia.

Decision log: grava 1 entry por (UA, dia) com `decision_type=SYNC`,
`rule_or_model=qitech_adapter`, output=step. Mantem rastreabilidade do
backfill no audit trail (CLAUDE.md sec 14.2).

Uso (de backend/, com .venv ativo):
    .venv\\Scripts\\python.exe scripts/backfill_qitech_mec.py
    .venv\\Scripts\\python.exe scripts/backfill_qitech_mec.py --start 2021-01-01 --end 2026-05-09
    .venv\\Scripts\\python.exe scripts/backfill_qitech_mec.py --tenant <uuid>
    .venv\\Scripts\\python.exe scripts/backfill_qitech_mec.py --ua <uuid>
    .venv\\Scripts\\python.exe scripts/backfill_qitech_mec.py --resume-from 2023-06-15
    .venv\\Scripts\\python.exe scripts/backfill_qitech_mec.py --skip-weekends

Args:
    --start <aaaa-mm-dd>      default 2021-01-01
    --end <aaaa-mm-dd>        default ontem (D-1 UTC)
    --tenant <uuid>           default a7-credit
    --ua <uuid>               opcional. Sem isso, itera todas UAs do tenant
                              que tenham config QiTech.
    --resume-from <date>      pula dias anteriores (util pra retomar apos crash)
    --skip-weekends           nao chama em sabado/domingo (acelera ~28%)
    --sleep <seconds>         pausa entre dias (default 0.3s, alivia API)

Tempo esperado: ~2-3s/dia x ~1800 dias (5 anos) x N UAs. Com --skip-weekends
e --sleep 0.3, ~1300 dias uteis x 3.3s = ~70min por UA.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

# Side-effect imports (registry SQLAlchemy completo).
import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.etl import sync_mec
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
    list_configs,
)
from app.shared.audit_log.decision_log import DecisionLog, DecisionType

A7_CREDIT_TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")


def _yesterday() -> date:
    return (datetime.now(UTC) - timedelta(days=1)).date()


def _daterange(start: date, end: date) -> Iterator[date]:
    cur = start
    while cur <= end:
        yield cur
        cur = cur + timedelta(days=1)


async def _log_decision(
    *,
    tenant_id: UUID,
    unidade_administrativa_id: UUID | None,
    data_posicao: date,
    environment: Environment,
    step: dict,
    triggered_by: str,
) -> None:
    """1 entry de decision_log por (UA, dia) — equivalente ao que sync_all faz.

    Como esse script chama sync_mec direto (nao sync_all), o audit trail
    nao acontece automaticamente. Replicamos aqui pra preservar a regra
    do CLAUDE.md sec 14.2 (toda decisao/sync registrado).
    """
    async with AsyncSessionLocal() as db:
        db.add(
            DecisionLog(
                tenant_id=tenant_id,
                decision_type=DecisionType.SYNC,
                inputs_ref={
                    "data_posicao": data_posicao.isoformat(),
                    "environment": environment.value,
                    "tipo_de_mercado": "mec",
                    "unidade_administrativa_id": (
                        str(unidade_administrativa_id)
                        if unidade_administrativa_id
                        else None
                    ),
                },
                rule_or_model="qitech_adapter",
                rule_or_model_version=ADAPTER_VERSION,
                output=step,
                explanation=(
                    "OK"
                    if step.get("ok")
                    else f"{len(step.get('errors') or [])} erro(s): "
                    f"{step.get('errors')}"
                ),
                triggered_by=triggered_by,
            )
        )
        await db.commit()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--tenant", default=str(A7_CREDIT_TENANT_ID))
    parser.add_argument("--ua", default=None)
    parser.add_argument("--resume-from", default=None)
    parser.add_argument("--skip-weekends", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.3)
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else _yesterday()
    resume_from = (
        date.fromisoformat(args.resume_from) if args.resume_from else None
    )
    tenant_id = UUID(args.tenant)
    ua = UUID(args.ua) if args.ua else None

    if start > end:
        print(f"[ERRO] start ({start}) > end ({end})")
        return 1

    # 1. Resolve quais (UA, config) iterar
    async with AsyncSessionLocal() as db:
        if ua is not None:
            cfg_row = await get_config(
                db,
                tenant_id,
                SourceType.ADMIN_QITECH,
                Environment.PRODUCTION,
                unidade_administrativa_id=ua,
            )
            if cfg_row is None:
                print(
                    f"[ERRO] sem config qitech para tenant={tenant_id} ua={ua} "
                    f"env=production"
                )
                return 1
            cfg_rows = [cfg_row]
        else:
            cfg_rows = list(
                await list_configs(
                    db,
                    tenant_id,
                    SourceType.ADMIN_QITECH,
                    Environment.PRODUCTION,
                )
            )
            if not cfg_rows:
                print(
                    f"[ERRO] tenant={tenant_id} nao tem nenhuma config qitech "
                    f"(legacy NULL nem por UA) em env=production. "
                    f"Veja em tenant_source_config quais UAs existem."
                )
                return 1

        targets: list[tuple[UUID | None, QiTechConfig]] = []
        for row in cfg_rows:
            plain = decrypt_config(row.config)
            cfg = QiTechConfig.from_dict(plain)
            if not cfg.has_credentials():
                print(
                    f"[WARN] config tenant={tenant_id} "
                    f"ua={row.unidade_administrativa_id} "
                    f"sem credenciais — pulando"
                )
                continue
            targets.append((row.unidade_administrativa_id, cfg))

    if not targets:
        print("[ERRO] nenhuma config com credenciais valida — abortando")
        return 1

    days_total = (end - start).days + 1
    print(
        f"[backfill-qitech-mec] tenant={tenant_id} env=production "
        f"range={start.isoformat()} -> {end.isoformat()} "
        f"({days_total} dias) UAs={len(targets)} "
        f"skip_weekends={args.skip_weekends} sleep={args.sleep}s"
    )
    for i, (ua_id, _) in enumerate(targets, 1):
        print(f"  UA {i}: {ua_id or '(legacy NULL)'}")

    # 2. Itera UA (externo) -> dia (interno)
    grand_days_processed = 0
    grand_days_skipped = 0
    grand_rows_total = 0
    grand_days_with_errors: list[tuple[UUID | None, date, list[str]]] = []

    triggered_by = "backfill_qitech_mec:cli"

    for ua_idx, (ua_id, config) in enumerate(targets, 1):
        print()
        print("#" * 90)
        print(f"# UA {ua_idx}/{len(targets)}: {ua_id or '(legacy NULL)'}")
        print("#" * 90)
        header = (
            f"{'DATA':<12} {'WD':<4} {'STATUS':<6} {'ROWS':<7} "
            f"{'ELAPSED':<9} ERROS"
        )
        print(header)
        print("-" * 90)

        for d in _daterange(start, end):
            wd = d.strftime("%a")

            if resume_from and d < resume_from:
                grand_days_skipped += 1
                continue

            if args.skip_weekends and d.weekday() >= 5:
                print(
                    f"{d.isoformat():<12} {wd:<4} {'SKIP':<6} -       "
                    f"-        weekend"
                )
                grand_days_skipped += 1
                continue

            try:
                step = await sync_mec(
                    tenant_id=tenant_id,
                    environment=Environment.PRODUCTION,
                    config=config,
                    data_posicao=d,
                    unidade_administrativa_id=ua_id,
                )
            except Exception as e:
                msg = f"crash: {type(e).__name__}: {e}"
                print(
                    f"{d.isoformat():<12} {wd:<4} {'CRASH':<6} -       "
                    f"-        {msg}"
                )
                grand_days_with_errors.append((ua_id, d, [msg]))
                continue

            grand_days_processed += 1
            rows_upserted = int(step.get("canonical_rows_upserted") or 0)
            grand_rows_total += rows_upserted
            errors = step.get("errors") or []
            status = "OK" if step["ok"] else "ERR"
            print(
                f"{d.isoformat():<12} {wd:<4} {status:<6} "
                f"{rows_upserted:<7} "
                f"{step.get('elapsed_seconds', 0):<9} "
                f"{len(errors)} erro(s)"
            )
            if errors:
                grand_days_with_errors.append((ua_id, d, errors))

            try:
                await _log_decision(
                    tenant_id=tenant_id,
                    unidade_administrativa_id=ua_id,
                    data_posicao=d,
                    environment=Environment.PRODUCTION,
                    step=step,
                    triggered_by=triggered_by,
                )
            except Exception as e:
                # Decision log e auditoria, nao bloqueia o backfill.
                print(f"  [WARN] decision_log falhou: {type(e).__name__}: {e}")

            if args.sleep > 0:
                await asyncio.sleep(args.sleep)

    print()
    print("=" * 90)
    print(
        f"FIM: UAs={len(targets)} "
        f"dias_processados={grand_days_processed} "
        f"dias_pulados={grand_days_skipped} "
        f"rows_ingested_total={grand_rows_total} "
        f"dias_com_erro={len(grand_days_with_errors)}"
    )
    if grand_days_with_errors:
        print()
        print("DIAS COM ERRO (primeiro erro de cada dia):")
        for ua_id, d, errs in grand_days_with_errors[:50]:
            print(f"  ua={ua_id or 'NULL'} {d.isoformat()}: {errs[0]}")
        if len(grand_days_with_errors) > 50:
            print(f"  ... e mais {len(grand_days_with_errors) - 50} dia(s)")
        print()
        print(
            "Pra retomar dias que falharam: --resume-from <primeira-data> "
            "(eventualmente combinado com --ua <uuid> pra escopar)"
        )

    return 0 if not grand_days_with_errors else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
