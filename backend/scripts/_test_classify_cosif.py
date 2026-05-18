"""Smoke test: classifica as 51 folhas COSIF do REALINVEST 13/05 e
agrega Sum d por bucket. Valida que aritmetica fecha vs balancete.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.modules.controladoria.services.balancete_diario import (
    compute_balancete_diario,
)
from app.modules.controladoria.services.cota_sub_buckets.cosif_to_bucket import (
    classify_cosif,
    is_cotas_emitidas,
    is_ignored_for_pl,
)


TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")
UA_ID     = UUID("6170ce55-b566-42ba-a3e7-5ea8dde56b64")
DATA_D0   = date(2026, 5, 13)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        bal = await compute_balancete_diario(
            db,
            tenant_id=TENANT_ID,
            fundo_id=UA_ID,
            data_d_zero=DATA_D0,
        )

        # Considera APENAS folhas analiticas (nivel >= 5 sem filho) — sinteticos
        # (3, 4) sao agregadores, somariam em duplicidade.
        # Estrategia simples: nivel >= 6 + nivel=5 sem filho. Aqui assume nivel
        # max do balancete e 6.
        # Como o calculo nao tem dependencia entre niveis aqui, vamos:
        #   - folhas analiticas = todas com nivel exatamente igual ao max do
        #     seu galho. Pra REALINVEST: nivel 6 + algumas nivel 5 sem filho.
        # Simplificacao pragmatica: pegar so as folhas com codigo de >= 6
        # segmentos OU com codigo de 5 segmentos cujo prefix nao tem filho.

        # Primeiro: agrupa por prefix pra descobrir folhas reais
        codigos_existentes = {n.codigo for n in bal.nodes if n.codigo}
        def has_child(codigo: str) -> bool:
            return any(c != codigo and c.startswith(codigo + ".") for c in codigos_existentes if c)

        folhas = [
            n for n in bal.nodes
            if n.codigo and not has_child(n.codigo)
        ]

        print(f"D-1: {bal.data_d_minus_1}  D0: {bal.data_d_zero}")
        print(f"Total folhas: {len(folhas)}")
        print()

        # Classifica cada folha
        bucket_sums: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        ignored: list[tuple[str, str, Decimal]] = []
        unmapped: list[tuple[str, str, Decimal]] = []
        cotas_special: list[tuple[str, str, Decimal]] = []

        for n in folhas:
            assert n.codigo is not None
            if is_ignored_for_pl(n.codigo):
                ignored.append((n.codigo, n.nome, n.delta))
                continue
            if is_cotas_emitidas(n.codigo):
                # Cotas Sr/Mez/Sub — quebra por classe (parcela Sr+Mez vai
                # pra remuneracao_sr_mez, parcela Sub vai pra fluxo_caixa).
                breakdowns = bal.classe_breakdown_por_cosif.get(n.codigo, [])
                cotas_special.append((n.codigo, n.nome, n.delta))
                sr_mez_delta = Decimal(0)
                sub_delta = Decimal(0)
                for b in breakdowns:
                    if b.classe in ("senior", "mezanino"):
                        sr_mez_delta += b.delta
                    elif b.classe == "subordinado":
                        sub_delta += b.delta
                bucket_sums["remuneracao_sr_mez"] += sr_mez_delta
                bucket_sums["fluxo_caixa"] += sub_delta
                continue
            bucket = classify_cosif(n.codigo)
            if bucket is None:
                unmapped.append((n.codigo, n.nome, n.delta))
                continue
            bucket_sums[bucket] += n.delta

        # Impressao
        print("--- Sum d por bucket ------------------------------")
        total = Decimal(0)
        for bucket, soma in sorted(bucket_sums.items()):
            print(f"  {bucket:25s} R$ {soma:>15,.2f}")
            total += soma
        print(f"  {'-' * 25} {'-' * 18}")
        print(f"  {'Sum buckets':25s} R$ {total:>15,.2f}")
        print()

        # Reconciliacao com balancete
        print("--- Reconciliacao ------------------------------")
        r = bal.reconciliacao
        print(f"  dPL Sub real (MEC):       R$ {r.delta_pl_cota_sub_real:>15,.2f}")
        print(f"  dPL Sub esperado (COSIF): R$ {r.delta_pl_cota_sub_esperado:>15,.2f}")
        print(f"  Residuo (real - esperado): R$ {r.residuo:>15,.2f}")
        print()
        print(f"  Sum buckets vs dPL_esperado: R$ {total - r.delta_pl_cota_sub_esperado:>15,.2f}")
        print()

        # Casos especiais
        if cotas_special:
            print("--- Cotas emitidas (quebra por classe) ----------")
            for cod, nome, delta in cotas_special:
                print(f"  {cod} | {nome} | d={delta}")
                for b in bal.classe_breakdown_por_cosif.get(cod, []):
                    print(f"      - {b.classe:14s} d={b.delta}")
            print()

        if ignored:
            print(f"--- Ignoradas (grupo 3, compensacao): {len(ignored)} --")
            for cod, nome, delta in ignored:
                print(f"  {cod} | {nome[:50]} | d={delta}")
            print()

        if unmapped:
            print(f"--- !!!FOLHAS SEM MAPPING: {len(unmapped)} --")
            for cod, nome, delta in unmapped:
                print(f"  {cod} | {nome[:50]} | d={delta}")
        else:
            print("OK Todas as folhas tem mapping definido.")


if __name__ == "__main__":
    asyncio.run(main())
