"""Read-only: roda classify_cpr_nature sobre TODO o universo de descricoes do CPR
(REALINVEST) e mostra a natureza atribuida, total por natureza e os flags
(nao_classificado / sinal contra-natureza). Nao escreve nada."""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from decimal import Decimal

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.modules.controladoria.services.cpr_natureza import (  # noqa: E402
    NATUREZA_INFO,
    classify_cpr_nature,
)

CNPJ = "42449234000160"


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT descricao,
                           count(*) AS n,
                           sum(valor)::numeric AS soma,
                           min(valor)::numeric AS menor,
                           max(valor)::numeric AS maior
                    FROM wh_cpr_movimento
                    WHERE unidade_administrativa_id =
                          (SELECT id FROM cadastros_unidade_administrativa WHERE cnpj=:c)
                    GROUP BY descricao
                    """
                ),
                {"c": CNPJ},
            )
        ).all()

    por_nat: dict[str, list] = defaultdict(list)
    tot_nat: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    flags: list[str] = []
    for r in rows:
        nat = classify_cpr_nature(r.descricao)
        por_nat[nat].append(r)
        tot_nat[nat] += Decimal(r.soma or 0)
        lado = NATUREZA_INFO[nat][0]
        # sinal contra-natureza: ativo deveria somar >=0, passivo <=0 (no agregado)
        soma = Decimal(r.soma or 0)
        if nat == "nao_classificado":
            flags.append(f"  [NAO CLASS] {r.descricao!r}  n={r.n} soma={soma:.2f}")
        elif lado == "ativo" and soma < 0:
            flags.append(f"  [ativo<0]   {nat:20} {r.descricao!r} soma={soma:.2f}")
        elif lado == "passivo" and soma > 0:
            flags.append(f"  [passivo>0] {nat:20} {r.descricao!r} soma={soma:.2f}")

    print("=== NATUREZA x total agregado (REALINVEST, historico completo) ===\n")
    for nat in sorted(tot_nat, key=lambda k: -abs(tot_nat[k])):
        lado, _grupo, dono = NATUREZA_INFO[nat]
        print(f"{nat:20} [{lado:7}] total={tot_nat[nat]:>16,.2f}  "
              f"({len(por_nat[nat])} descricoes)  -> {dono}")
    print("\n=== descricoes por natureza ===")
    for nat in NATUREZA_INFO:
        if nat not in por_nat:
            continue
        print(f"\n--- {nat} ---")
        for r in sorted(por_nat[nat], key=lambda x: -abs(Decimal(x.soma or 0)))[:40]:
            print(f"  {Decimal(r.soma or 0):>15,.2f}  n={r.n:<5} {r.descricao!r}")

    print("\n=== FLAGS (revisar) ===")
    if flags:
        print("\n".join(flags))
    else:
        print("  (nenhum — classificacao limpa)")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
