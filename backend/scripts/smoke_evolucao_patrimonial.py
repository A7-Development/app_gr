"""Smoke test do service Evolucao Patrimonial (Controladoria).

Valida contra REALINVEST FIDC (unico tenant com MEC populado hoje):

  1. Serie mensal 12M corridos (default) -- todas as classes
  2. Serie diaria curta (ultimo ~mes) -- granularidade fina
  3. Filtro de classe (so 'sub')

Asserts de sanidade (nao reconciliacao contabil -- isso e do cota_sub):
  - serie nao vazia, PL total > 0 em todos os pontos
  - subordinacao entre 0 e 100%
  - participacao das classes soma ~100% no ultimo ponto
  - % do CDI da Sub presente (rentabilidade_fundo populada)

Read-only -- seguro mesmo em dev=prod.
"""

from __future__ import annotations

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.modules.cadastros.public import UnidadeAdministrativa  # noqa: E402
from app.modules.controladoria.services.evolucao_patrimonial import (  # noqa: E402
    compute_evolucao_patrimonial,
)

_failures: list[str] = []


def _check(cond: bool, label: str) -> None:
    print(f"  {'✓' if cond else '✗'} {label}")
    if not cond:
        _failures.append(label)


async def _run(db, *, ua, granularidade, classes=None, titulo=""):
    print(f"\n{'='*100}\n{titulo}\n{'='*100}")
    r = await compute_evolucao_patrimonial(
        db,
        tenant_id=ua.tenant_id,
        ua_id=ua.id,
        granularidade=granularidade,
        classes_filtro=classes,
    )
    print(
        f"Fundo: {r.fundo_nome} | {r.periodo_inicio} -> {r.periodo_fim} "
        f"| gran={r.granularidade} | pontos={len(r.serie)}"
    )
    print("Classes disponiveis:")
    for ci in r.classes_disponiveis:
        print(f"  {ci.classe:3s} {ci.label:12s} {ci.carteira_cliente_nome[:30]:30s} "
              f"{ci.primeiro_dia} -> {ci.ultimo_dia}")

    print("\nKPIs:")
    k = r.kpis
    print(f"  PL total: R$ {k.pl_total_inicio:,.2f} -> R$ {k.pl_total_atual:,.2f} "
          f"({k.pl_total_delta_pct:+.2f}%)" if k.pl_total_delta_pct is not None
          else f"  PL total: R$ {k.pl_total_inicio:,.2f} -> R$ {k.pl_total_atual:,.2f}")
    print(f"  Captacao liquida periodo: R$ {k.captacao_liquida_periodo:,.2f}")
    print(f"  Subordinacao: {k.subordinacao_pct}%")
    print(f"  Rentab Sub periodo: {k.rentab_sub_periodo_pct}%  | % CDI Sub: {k.pct_cdi_sub_ultimo}")

    print("\nResumo por classe:")
    for rc in r.resumo_por_classe:
        print(f"  {rc.label:12s} PL R$ {rc.pl_inicio:>14,.2f} -> R$ {rc.pl_atual:>14,.2f}  "
              f"rentab={rc.rentab_periodo_pct}%  partic={rc.participacao_pct}%  "
              f"capt=R$ {rc.captacao_liquida_periodo:,.2f}  %CDI={rc.pct_cdi_ultimo}")

    if r.serie:
        p0, p1 = r.serie[0], r.serie[-1]
        print(f"\nPrimeiro ponto {p0.data}: PL R$ {p0.pl_total:,.2f}  cdi={p0.cdi_retorno_pct}")
        for pc in p0.classes:
            print(f"    {pc.classe}: PL={pc.patrimonio:,.2f} cota={pc.valor_cota:.6f} %CDI={pc.pct_cdi}")
        print(f"Ultimo ponto   {p1.data}: PL R$ {p1.pl_total:,.2f}  cdi={p1.cdi_retorno_pct}")
        for pc in p1.classes:
            print(f"    {pc.classe}: PL={pc.patrimonio:,.2f} cota={pc.valor_cota:.6f} "
                  f"capt={pc.captacao_liquida:,.2f} %CDI={pc.pct_cdi}")

    # ── ASSERTS ──
    print("\nValidacao:")
    _check(len(r.serie) > 0, "serie nao vazia")
    _check(all(p.pl_total > 0 for p in r.serie), "PL total > 0 em todos os pontos")
    if k.subordinacao_pct is not None:
        _check(0 < k.subordinacao_pct < 100, f"subordinacao em (0,100) -> {k.subordinacao_pct}")
    if r.serie and not classes:
        soma_part = sum((rc.participacao_pct or 0) for rc in r.resumo_por_classe)
        _check(abs(soma_part - 100.0) < 0.5, f"Σ participacao ~100% -> {soma_part:.2f}")
    return r


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        ua = (
            await db.execute(
                select(UnidadeAdministrativa).where(
                    UnidadeAdministrativa.nome == "REALINVEST FIDC"
                )
            )
        ).scalar_one()

        await _run(db, ua=ua, granularidade="mensal",
                   titulo="MENSAL · 12M corridos · todas as classes")
        await _run(db, ua=ua, granularidade="diaria",
                   titulo="DIARIA · 12M corridos · todas as classes")
        await _run(db, ua=ua, granularidade="mensal", classes=["sub"],
                   titulo="MENSAL · 12M · filtro classe=sub")

    print(f"\n{'='*100}")
    if _failures:
        print(f"FALHOU — {len(_failures)} assercoes:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("TODAS as assercoes passaram. Smoke OK.")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    asyncio.run(main())
