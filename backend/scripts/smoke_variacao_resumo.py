"""Smoke do Resumo do dia (waterfall por grupo) — `compute_variacao_resumo`.

Valida o fechamento por construcao e a reconciliacao MEC contra dados reais:

  1. Sigma grupos.impacto_pl_sub == cota_delta  (Disponibilidades e o plug).
  2. cota_delta == pl_sub_calc_d0 - pl_sub_calc_d1.
  3. reconciliacao.residuo == cota_delta - variacao_mec.
  4. Render dos 6 grupos + Disponibilidades (o plug) pra inspecao visual —
     se o plug ficar material/absurdo, e sinal de giro nao capturado.

Read-only. dev=prod seguro. Cenarios REALINVEST.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.modules.controladoria.services.variacao_resumo import (  # noqa: E402
    compute_variacao_resumo,
)

_failures: list[str] = []
TOL = Decimal("0.02")


def _check(cond: bool, label: str) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _failures.append(label)


def _fmt(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def _cenario(db, *, tenant_id, ua_id, data_d0: date) -> None:
    print(f"\n=== REALINVEST {data_d0.isoformat()} ===")
    r = await compute_variacao_resumo(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0)

    print(f"  PL Sub D-1 (MEC) = {_fmt(r.pl_sub_mec_d1)}   D0 (MEC) = {_fmt(r.pl_sub_mec_d0)}")
    print(f"  Grupos (impacto giro-limpo no PL Sub):")
    soma = Decimal("0")
    for g in r.grupos:
        soma += g.impacto_pl_sub
        print(f"    {g.label:26} {_fmt(g.impacto_pl_sub):>16}   [{g.natureza}]")
    print(f"    {'= Sigma grupos':26} {_fmt(soma):>16}")
    print(f"  cota_delta (apresentada) = {_fmt(r.cota_delta)}")
    print(f"  giro_total (nota neutra) = {_fmt(r.giro_total)}")
    print(f"  Reconciliacao: apresentada={_fmt(r.reconciliacao.variacao_apresentada)} "
          f"MEC={_fmt(r.reconciliacao.variacao_mec)} "
          f"residuo={_fmt(r.reconciliacao.residuo)} fecha={r.reconciliacao.fecha}")
    if r.atencoes:
        print(f"  Atencoes ({len(r.atencoes)}):")
        for a in r.atencoes:
            print(f"    [{a.tipo:24}] {a.descricao[:60]:60} {_fmt(a.valor):>14}  -> {a.grupo_label}")
    else:
        print("  Atencoes: nenhuma")

    # 1. Fechamento por construcao.
    _check(abs(soma - r.cota_delta) < TOL, "Sigma grupos.impacto == cota_delta (plug fecha)")
    # 2. cota_delta == delta do PL calc.
    _check(abs(r.cota_delta - (r.pl_sub_calc_d0 - r.pl_sub_calc_d1)) < TOL,
           "cota_delta == pl_sub_calc_d0 - pl_sub_calc_d1")
    # 3. residuo == apresentada - MEC.
    _check(abs(r.reconciliacao.residuo - (r.cota_delta - r.reconciliacao.variacao_mec)) < TOL,
           "residuo == apresentada - MEC")
    # 4. 6 grupos presentes.
    _check(len(r.grupos) == 6, "6 grupos no waterfall")


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        row = (
            await db.execute(
                text(
                    "SELECT t.id, ua.id FROM tenants t "
                    "JOIN cadastros_unidade_administrativa ua ON ua.tenant_id=t.id "
                    "WHERE t.slug='a7-credit' AND ua.cnpj='42449234000160' LIMIT 1"
                )
            )
        ).first()
        if row is None:
            print("ERRO: REALINVEST nao encontrado.")
            sys.exit(1)
        tenant_id, ua_id = row
        for d in (date(2026, 5, 29), date(2026, 5, 20), date(2026, 5, 14)):
            try:
                await _cenario(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=d)
            except Exception as exc:  # noqa: BLE001
                print(f"  ERRO no cenario {d}: {type(exc).__name__}: {exc}")
                _failures.append(f"cenario {d}: {exc}")
    await engine.dispose()

    print(f"\n{'='*80}")
    if _failures:
        print(f"FALHOU — {len(_failures)} assercoes:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("TODAS as assercoes passaram. Resumo do dia OK (soma fecha + reconcilia).")


if __name__ == "__main__":
    asyncio.run(main())
