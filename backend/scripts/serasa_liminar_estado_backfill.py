"""Backfill cronologico da maquina de estados de liminar (sentinela).

Uso (do diretorio backend/):

    .venv\\Scripts\\python.exe scripts/serasa_liminar_estado_backfill.py

Pre-requisito: `scripts/serasa_pj_remap_all.py` ja rodado (colunas
`negative_summary_message` / `suspeita_liminar` populadas no silver).

Reaplica a sentinela (`process_consulta`) sobre TODAS as consultas silver
em ordem cronologica — a guarda de ordem da sentinela torna o replay
idempotente (re-rodar nao duplica transicao nem regride estado).

Esperado no primeiro run (dados 2026-06-10): 32 CNPJs entram em
`suspeita_ativa` (32 transicoes `entrada_suspeita` no decision_log);
zero `liminar_caida` / `transicao_ambigua` (nenhum CNPJ transicionou
dentro da janela historica).
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter

from sqlalchemy import select

import app.shared.identity.tenant
import app.warehouse  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.services.serasa_liminar_sentinela import (
    ConsultaAvaliada,
    has_negativos_visiveis,
    process_consulta,
)
from app.warehouse.serasa_liminar_estado import SerasaLiminarEstado
from app.warehouse.serasa_pj_consulta import SerasaPjConsulta

_NEG_COUNT_FIELDS = (
    "count_pefin",
    "count_refin",
    "count_protesto",
    "count_cheque",
    "count_falencias",
    "count_acoes_judiciais",
)


async def main() -> int:
    async with AsyncSessionLocal() as db:
        consultas = (
            (
                await db.execute(
                    select(SerasaPjConsulta).order_by(
                        SerasaPjConsulta.consulted_at,
                        SerasaPjConsulta.cnpj,
                    )
                )
            )
            .scalars()
            .all()
        )

    total = len(consultas)
    print(f"[backfill] {total} consultas silver em ordem cronologica")

    transicoes: Counter[str] = Counter()
    async with AsyncSessionLocal() as db:
        for i, c in enumerate(consultas, start=1):
            row = {f: getattr(c, f) for f in _NEG_COUNT_FIELDS}
            t = await process_consulta(
                db,
                ConsultaAvaliada(
                    tenant_id=c.tenant_id,
                    cnpj=c.cnpj,
                    raw_id=c.raw_id,
                    consulted_at=c.consulted_at,
                    negative_summary_message=c.negative_summary_message,
                    negativos_visiveis=has_negativos_visiveis(row),
                    triggered_by="system:liminar_backfill",
                ),
            )
            if t:
                transicoes[t] += 1
            if i % 500 == 0 or i == total:
                print(f"[backfill] {i}/{total}")
        await db.commit()

    print("\n[backfill] transicoes disparadas:")
    for nome, n in transicoes.most_common():
        print(f"  {nome}: {n}")
    if not transicoes:
        print("  (nenhuma)")

    async with AsyncSessionLocal() as db:
        estados = (
            await db.execute(
                select(
                    SerasaLiminarEstado.estado,
                    SerasaLiminarEstado.cnpj,
                ).order_by(SerasaLiminarEstado.estado)
            )
        ).all()
    por_estado: Counter[str] = Counter(e for e, _ in estados)
    print("\n[backfill] estados finais:")
    for estado, n in por_estado.most_common():
        print(f"  {estado}: {n} cnpjs")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
