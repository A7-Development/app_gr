"""Smoke do balanco ESTRUTURAL (redesign 2026-05-27).

Valida `compute_balanco_estrutural` contra `compute_balanco_patrimonial`:

  1. Identidade fecha por construcao: Σ Ativo - Σ Passivo == PL Sub.
  2. PARIDADE: PL Sub (novo) == pl_deduzido (antigo) — a reclassificacao
     (PDD contra-ativo, CPR split, Cotas Prioritarias) e PL-neutra.
  3. dc_liquido == dc_bruto - pdd.
  4. CPR: a_receber (ativo) - a_pagar_mag (passivo) == cpr net antigo.

Read-only. dev=prod seguro. Cenarios REALINVEST: 20/05 (aporte Mezanino) e
14/05 (lote de multa/juros).
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
from app.modules.controladoria.services.balanco_patrimonial import (  # noqa: E402
    compute_balanco_estrutural,
    compute_balanco_patrimonial,
)

_failures: list[str] = []
TOL = Decimal("0.01")


def _check(cond: bool, label: str) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _failures.append(label)


def _fmt(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def _cenario(db, *, tenant_id, ua_id, data_d0: date) -> None:
    print(f"\n=== REALINVEST {data_d0.isoformat()} ===")
    est = await compute_balanco_estrutural(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0)
    old = await compute_balanco_patrimonial(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0)

    # Render legivel.
    print("  ATIVO:")
    for ln in est.ativos:
        print(f"    [{ln.grupo:22}] {ln.label:30} d0={_fmt(ln.d0):>16}  ({ln.natureza})")
    print(f"    DC liquido d0 = {_fmt(est.dc_liquido_d0)}")
    print(f"    Σ ATIVO   d0 = {_fmt(est.total_ativo_d0)}")
    print("  PASSIVO:")
    for ln in est.passivos:
        print(f"    [{ln.grupo:22}] {ln.label:30} d0={_fmt(ln.d0):>16}")
    print(f"    Σ PASSIVO d0 = {_fmt(est.total_passivo_d0)}")
    print(f"  PL SUB    d0 = {_fmt(est.pl_sub_d0)}  (delta {_fmt(est.pl_sub_delta)})")
    print(f"  Reconc MEC: fonte={_fmt(est.reconciliacao.pl_fonte_d0)} "
          f"residuo_dia={_fmt(est.reconciliacao.residuo_delta)} "
          f"ok={est.reconciliacao.dentro_tolerancia}")

    # 1. Identidade fecha por construcao.
    _check(abs((est.total_ativo_d0 - est.total_passivo_d0) - est.pl_sub_d0) < TOL,
           "identidade D0: Σ Ativo - Σ Passivo == PL Sub")
    _check(abs((est.total_ativo_d1 - est.total_passivo_d1) - est.pl_sub_d1) < TOL,
           "identidade D-1: Σ Ativo - Σ Passivo == PL Sub")

    # 2. Paridade com o balanco antigo (PL-neutro).
    _check(abs(est.pl_sub_d0 - old.pl_deduzido_d0) < TOL,
           f"paridade D0: PL Sub novo ({_fmt(est.pl_sub_d0)}) == pl_deduzido antigo ({_fmt(old.pl_deduzido_d0)})")
    _check(abs(est.pl_sub_d1 - old.pl_deduzido_d1) < TOL,
           "paridade D-1: PL Sub novo == pl_deduzido antigo")
    _check(abs(est.pl_sub_delta - old.pl_deduzido_delta) < TOL,
           "paridade delta: pl_sub_delta == pl_deduzido_delta")

    # 3. dc_liquido == dc_bruto - pdd.
    dc_bruto = next(ln for ln in est.ativos if ln.key == "dc_bruto")
    pdd = next(ln for ln in est.ativos if ln.key == "pdd")
    _check(abs(est.dc_liquido_d0 - (dc_bruto.d0 - pdd.d0)) < TOL,
           "dc_liquido == dc_bruto - pdd")
    _check(pdd.natureza == "contra_ativo", "PDD natureza == contra_ativo")

    # 4. CPR split reconcilia com o net antigo.
    cpr_rec = next(ln for ln in est.ativos if ln.key == "cpr_receber")
    cpr_pag = next(ln for ln in est.passivos if ln.key == "cpr_pagar")
    cpr_old = next(c for c in old.ativos if c.key == "cpr")
    _check(abs((cpr_rec.d0 - cpr_pag.d0) - cpr_old.d0) < TOL,
           f"CPR: receber - pagar ({_fmt(cpr_rec.d0 - cpr_pag.d0)}) == net antigo ({_fmt(cpr_old.d0)})")
    _check(cpr_rec.d0 >= 0 and cpr_pag.d0 >= 0,
           "CPR a receber >= 0 e a pagar (magnitude) >= 0")

    # 5. Senior/Mezanino no grupo cotas_prioritarias.
    sr = next(ln for ln in est.passivos if ln.key == "senior")
    _check(sr.grupo == "cotas_prioritarias", "Senior no grupo cotas_prioritarias")


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
        await _cenario(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=date(2026, 5, 20))
        await _cenario(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=date(2026, 5, 14))
    await engine.dispose()

    print(f"\n{'='*80}")
    if _failures:
        print(f"FALHOU — {len(_failures)} assercoes:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("TODAS as assercoes passaram. Balanco estrutural OK.")


if __name__ == "__main__":
    asyncio.run(main())
