"""Backfill raw_id em rows historicas das silvers QiTech (Fase 1.6).

Popula a coluna raw_id (FK pra wh_qitech_raw_<X>) em rows silver que
foram ingeridas ANTES da migration c8a3d2b1f7e9 (Fase 1.1, 2026-05-20).
Apos backfill, rows com raw_id=NULL ainda caem no path UPSERT legado;
rows com raw_id preenchido entram no caminho replace-by-partition em
re-sync.

Idempotente: rola um UPDATE por silver com `WHERE raw_id IS NULL`. Pode
ser interrompido e reiniciado sem efeito colateral.

Uso:
    .venv/Scripts/python.exe scripts/backfill_qitech_raw_id.py [--dry-run] [--silver=<name>] [--batch-size=N]

    --dry-run        Conta candidatos por silver sem atualizar.
    --silver=NAME    Roda so 1 silver (ex.: wh_posicao_cota_fundo).
    --batch-size=N   Tamanho do lote (default 5000). Atualiza ate zerar.

Cobertura:
- 9 silvers market (raw_relatorio): JOIN direto por
  (tenant_id, tipo_de_mercado, data_posicao, ua_id).
- 2 silvers bank_account (raws dedicados): JOIN por
  (tenant_id, ua_id, agencia, conta, data_posicao).
- 5 silvers custodia (raw_relatorio): pulados — ainda usam UPSERT
  legado em custodia.py (Fase 1.3 deliberadamente nao tocou). Backfill
  desses entra quando o refactor de _persist_raw_split_by_window
  propagar raw_id ao caller.

Excluso: wh_movimento_caixa — tech debt em
[[project_qitech_business_key_uq]].
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Garante que o app/ resolve quando rodado de qualquer cwd
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import app.shared.identity  # noqa: F401 — carrega Tenant pra resolver FKs
import app.warehouse  # noqa: F401
from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402

# ─── Mapping silver -> raw + tipo_de_mercado ────────────────────────────────

# Market: JOIN com wh_qitech_raw_relatorio por (tenant_id, tipo_de_mercado,
# data_posicao, unidade_administrativa_id).
MARKET_SILVERS: dict[str, str] = {
    "wh_posicao_cota_fundo":     "outros-fundos",
    "wh_saldo_conta_corrente":   "conta-corrente",
    "wh_saldo_tesouraria":       "tesouraria",
    "wh_posicao_outros_ativos":  "outros-ativos",
    "wh_cpr_movimento":          "cpr",
    "wh_mec_evolucao_cotas":     "mec",
    "wh_rentabilidade_fundo":    "rentabilidade",
    "wh_posicao_renda_fixa":     "rf",
    "wh_posicao_compromissada":  "rf-compromissadas",
}

# Bank account: JOIN com raw dedicado por (tenant, ua, agencia, conta, data).
BANK_SILVERS: dict[str, dict[str, str]] = {
    "wh_saldo_bancario_diario": {
        "raw_table": "wh_qitech_raw_bank_account_balance",
        "join_kind": "by_data_posicao",  # ambos tem data_posicao
    },
    "wh_extrato_bancario": {
        "raw_table": "wh_qitech_raw_bank_account_statement",
        "join_kind": "by_periodo",  # silver tem data_lancamento; raw tem periodo_inicio/fim
    },
}

# Custodia: pulado nesta fase (ainda em UPSERT legado).
CUSTODIA_SILVERS = [
    "wh_aquisicao_recebivel",
    "wh_liquidacao_recebivel",
    "wh_estoque_recebivel",
    "wh_movimento_aberto",
    "wh_operacao_remessa",
]


# ─── Queries por kind ───────────────────────────────────────────────────────

def market_update_sql(silver: str, tipo: str, batch_size: int) -> str:
    """UPDATE em batch pra silver market. JOIN por (tenant, tipo, data, ua)."""
    return f"""
        WITH batch AS (
            SELECT s.id, r.id AS new_raw_id
            FROM {silver} s
            JOIN wh_qitech_raw_relatorio r
              ON  r.tenant_id = s.tenant_id
              AND r.tipo_de_mercado = :tipo
              AND r.data_posicao = s.data_posicao
              AND r.unidade_administrativa_id IS NOT DISTINCT FROM s.unidade_administrativa_id
            WHERE s.raw_id IS NULL
            LIMIT {batch_size}
        )
        UPDATE {silver} t
        SET raw_id = batch.new_raw_id
        FROM batch
        WHERE t.id = batch.id
    """


def bank_balance_update_sql(silver: str, raw_table: str, batch_size: int) -> str:
    """JOIN por (tenant, ua, agencia, conta, data_posicao)."""
    return f"""
        WITH batch AS (
            SELECT s.id, r.id AS new_raw_id
            FROM {silver} s
            JOIN {raw_table} r
              ON  r.tenant_id = s.tenant_id
              AND r.unidade_administrativa_id IS NOT DISTINCT FROM s.unidade_administrativa_id
              AND r.agencia = s.agencia
              AND r.conta = s.conta
              AND r.data_posicao = s.data_posicao
            WHERE s.raw_id IS NULL
            LIMIT {batch_size}
        )
        UPDATE {silver} t
        SET raw_id = batch.new_raw_id
        FROM batch
        WHERE t.id = batch.id
    """


def bank_statement_update_sql(silver: str, raw_table: str, batch_size: int) -> str:
    """JOIN por (tenant, ua, agencia, conta) AND raw.periodo cobre data_lancamento.

    Se houver multiplos periodos sobrepostos cobrindo o mesmo lancamento, escolhemos
    o periodo mais recente (max fetched_at) — semantica: "ultimo fetch que cobriu
    o dia eh quem manda na silver row". Em prod nao deveria ter sobreposicao mas
    proteja contra a chance.
    """
    return f"""
        WITH candidates AS (
            SELECT
                s.id AS silver_id,
                r.id AS raw_id_candidate,
                r.fetched_at,
                ROW_NUMBER() OVER (
                    PARTITION BY s.id
                    ORDER BY r.fetched_at DESC, r.id DESC
                ) AS rn
            FROM {silver} s
            JOIN {raw_table} r
              ON  r.tenant_id = s.tenant_id
              AND r.unidade_administrativa_id IS NOT DISTINCT FROM s.unidade_administrativa_id
              AND r.agencia = s.agencia
              AND r.conta = s.conta
              AND s.data_lancamento >= r.periodo_inicio
              AND s.data_lancamento <= r.periodo_fim
            WHERE s.raw_id IS NULL
        ),
        batch AS (
            SELECT silver_id, raw_id_candidate AS new_raw_id
            FROM candidates
            WHERE rn = 1
            LIMIT {batch_size}
        )
        UPDATE {silver} t
        SET raw_id = batch.new_raw_id
        FROM batch
        WHERE t.id = batch.silver_id
    """


def count_pending_sql(silver: str) -> str:
    return f"SELECT COUNT(*) FROM {silver} WHERE raw_id IS NULL"


# ─── Driver ────────────────────────────────────────────────────────────────


async def backfill_silver(
    silver: str,
    *,
    update_sql: str,
    params: dict,
    dry_run: bool,
    batch_size: int,
) -> tuple[int, int]:
    """Roda backfill pra 1 silver. Retorna (initial_pending, updated_total)."""
    async with AsyncSessionLocal() as db:
        initial = (await db.execute(text(count_pending_sql(silver)))).scalar() or 0

    if initial == 0:
        return initial, 0
    if dry_run:
        return initial, 0

    updated_total = 0
    while True:
        async with AsyncSessionLocal() as db:
            res = await db.execute(text(update_sql), params)
            rowcount = res.rowcount or 0
            await db.commit()
        if rowcount == 0:
            break
        updated_total += rowcount
        print(f"  {silver}: +{rowcount} (running total {updated_total} / {initial})")
        # Loop continua ate update retornar 0 rows — sinal de que ou
        # populou tudo o que dava match, ou esgotou candidatos.

    return initial, updated_total


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="So conta candidatos.")
    ap.add_argument(
        "--silver",
        type=str,
        default=None,
        help="Roda so 1 silver. Default: todos.",
    )
    ap.add_argument(
        "--batch-size", type=int, default=5000, help="Tamanho do lote (default 5000)."
    )
    args = ap.parse_args()

    targets: list[tuple[str, str, dict]] = []

    # Market
    for silver, tipo in MARKET_SILVERS.items():
        if args.silver and args.silver != silver:
            continue
        targets.append((
            silver,
            market_update_sql(silver, tipo, args.batch_size),
            {"tipo": tipo},
        ))

    # Bank
    for silver, meta in BANK_SILVERS.items():
        if args.silver and args.silver != silver:
            continue
        raw_table = meta["raw_table"]
        kind = meta["join_kind"]
        if kind == "by_data_posicao":
            sql = bank_balance_update_sql(silver, raw_table, args.batch_size)
        elif kind == "by_periodo":
            sql = bank_statement_update_sql(silver, raw_table, args.batch_size)
        else:
            raise ValueError(f"unknown join_kind for {silver}: {kind}")
        targets.append((silver, sql, {}))

    if args.silver and not targets:
        if args.silver in CUSTODIA_SILVERS:
            print(
                f"AVISO: {args.silver} eh custodia — pulado nesta fase (ainda usa "
                f"UPSERT legado em custodia.py). Adicionar quando refactor de "
                f"_persist_raw_split_by_window propagar raw_id ao caller."
            )
            return
        print(f"ERRO: silver desconhecido: {args.silver}")
        sys.exit(1)

    mode = "DRY-RUN" if args.dry_run else "BACKFILL"
    print(f"== {mode} (batch_size={args.batch_size}) ==\n")

    total_initial = 0
    total_updated = 0
    skipped_zero = 0
    for silver, sql, params in targets:
        initial, updated = await backfill_silver(
            silver,
            update_sql=sql,
            params=params,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
        total_initial += initial
        total_updated += updated
        if initial == 0:
            skipped_zero += 1
            continue
        if args.dry_run:
            print(f"  {silver}: {initial} candidatos com raw_id IS NULL")
        else:
            remaining = initial - updated
            mark = "OK" if remaining == 0 else "PARCIAL"
            print(
                f"  {silver}: {mark} — {updated}/{initial} populados, "
                f"{remaining} sem match (raw nao existe)"
            )

    if args.silver is None and not args.dry_run and skipped_zero > 0:
        print(
            f"\n(Silvers ja com raw_id 100% preenchido: {skipped_zero} — pulados)"
        )

    # Custodia: report sempre, mesmo no escopo geral, pra deixar claro que
    # foi consciente.
    if args.silver is None:
        print(
            f"\n## Custodia ({len(CUSTODIA_SILVERS)} silvers): pulados — ainda em "
            f"UPSERT legado. Refactor de _persist_raw_split_by_window pendente."
        )

    print(
        f"\n== Total: {total_initial} candidatos, {total_updated} populados =="
    )


if __name__ == "__main__":
    asyncio.run(main())
