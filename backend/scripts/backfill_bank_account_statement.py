"""Backfill historico do extrato bancario QiTech (endpoint bank_account.statement).

Itera janelas MENSAIS sobre [start, end] chamando `sync_statement` (fetch QiTech
-> raw -> mapper v0.5.0 -> silver wh_extrato_bancario) pra cada conta habilitada
da UA. Idempotente: re-rodar a mesma janela faz upsert no raw (UQ por periodo) e
replace-by-partition no silver; ON CONFLICT na business key evita duplicata mesmo
com sobreposicao de janelas.

Volume por conta-mes e baixo (dezenas de lancamentos) — janela mensal nao trunca.
O script reporta a contagem por janela; valor suspeitosamente "redondo" (ex.: 100,
500, 1000 exatos) sugere cap da fonte → reduzir janela.

PUXA DADO LIVE DA QITECH (API externa) e escreve em prod. Use --dry-run primeiro.

Default end = 2026-05-08: o sync diario ja dona 2026-05-09+ (raws diarios). O
backfill cobre o historico ate a vespera, sem brigar com esses raws.

Uso:
    .venv/Scripts/python.exe scripts/backfill_bank_account_statement.py --dry-run
    .venv/Scripts/python.exe scripts/backfill_bank_account_statement.py --start 2026-04-01 --end 2026-04-30
    .venv/Scripts/python.exe scripts/backfill_bank_account_statement.py --start 2021-01-01 --end 2026-05-08
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import app.shared.identity  # noqa: E402 — carrega Tenant pra resolver FKs
import app.warehouse  # noqa: F401,E402
from app.core.enums import Environment  # noqa: E402
from app.modules.integracoes.adapters.admin.qitech.bank_account_sync import (  # noqa: E402
    sync_statement,
)
from app.modules.integracoes.adapters.admin.qitech.custodia import (  # noqa: E402
    get_qitech_config_for_tenant,
)

# Defaults REALINVEST / a7-credit (mesma UA dos raws existentes).
_DEFAULT_TENANT = "7f00cc2b-8bb4-483f-87b7-b1db24d20902"
_DEFAULT_UA = "6170ce55-b566-42ba-a3e7-5ea8dde56b64"


def _month_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Quebra [start, end] em janelas [1o dia do mes .. ultimo dia do mes],
    com a primeira clampada em `start` e a ultima em `end`."""
    windows: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        # ultimo dia do mes de `cur`
        if cur.month == 12:
            next_month_first = date(cur.year + 1, 1, 1)
        else:
            next_month_first = date(cur.year, cur.month + 1, 1)
        month_end = next_month_first - timedelta(days=1)
        win_end = min(month_end, end)
        windows.append((cur, win_end))
        cur = next_month_first
    return windows


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant-id", default=_DEFAULT_TENANT)
    ap.add_argument("--ua-id", default=_DEFAULT_UA)
    ap.add_argument("--start", default="2021-01-01", help="YYYY-MM-DD inclusivo")
    ap.add_argument("--end", default="2026-05-08", help="YYYY-MM-DD inclusivo")
    ap.add_argument("--sleep", type=float, default=0.5, help="Pausa entre chamadas (s)")
    ap.add_argument("--dry-run", action="store_true", help="So lista janelas, sem chamar QiTech")
    ap.add_argument("--conta", default=None, help="So esta conta (ex.: 4532543); default = todas habilitadas")
    args = ap.parse_args()

    tenant_id = UUID(args.tenant_id)
    ua_id = UUID(args.ua_id)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if end < start:
        print(f"ERRO: end ({end}) < start ({start})")
        sys.exit(1)

    windows = _month_windows(start, end)
    print(f"== Backfill extrato {start}..{end} — {len(windows)} janela(s) mensal(is) ==\n")

    if args.dry_run:
        config = await get_qitech_config_for_tenant(
            tenant_id=tenant_id, environment=Environment.PRODUCTION,
            unidade_administrativa_id=ua_id,
        )
        if config is None or not config.has_credentials():
            print("AVISO: sem config/credenciais QiTech pra essa UA (so dry-run consegue listar).")
            accounts = []
        else:
            accounts = config.enabled_bank_accounts()
        if args.conta:
            accounts = tuple(a for a in accounts if a.conta == args.conta)
        print(f"contas habilitadas: {[(a.agencia, a.conta) for a in accounts]}")
        for ini, fim in windows:
            print(f"  {ini} .. {fim}")
        return

    config = await get_qitech_config_for_tenant(
        tenant_id=tenant_id, environment=Environment.PRODUCTION,
        unidade_administrativa_id=ua_id,
    )
    if config is None or not config.has_credentials():
        print("ERRO: sem config/credenciais QiTech pra essa UA.")
        sys.exit(1)
    accounts = config.enabled_bank_accounts()
    if args.conta:
        accounts = tuple(a for a in accounts if a.conta == args.conta)
    if not accounts:
        print("ERRO: nenhuma conta bancaria habilitada na UA (ou filtro --conta nao casou).")
        sys.exit(1)

    total_rows = 0
    total_err = 0
    for acc in accounts:
        print(f"\n--- conta {acc.agencia}/{acc.conta} ---")
        for ini, fim in windows:
            step = await sync_statement(
                tenant_id=tenant_id,
                unidade_administrativa_id=ua_id,
                environment=Environment.PRODUCTION,
                config=config,
                agencia=acc.agencia,
                conta=acc.conta,
                inicio=ini,
                fim=fim,
            )
            n = step.get("canonical_rows_upserted", 0)
            http = step.get("raw_http_status")
            errs = step.get("errors") or []
            total_rows += n
            if errs:
                total_err += 1
                print(f"  {ini}..{fim}: HTTP {http} ERRO: {errs}")
            else:
                flag = "  <-- valor redondo?" if n in (100, 200, 500, 1000) else ""
                print(f"  {ini}..{fim}: HTTP {http} -> {n} movimento(s){flag}")
            await asyncio.sleep(args.sleep)

    print(f"\n== fim: {total_rows} movimentos gravados, {total_err} janela(s) com erro ==")


if __name__ == "__main__":
    asyncio.run(main())
