"""Smoke test dos 3 drills da Cota Sub (F2 do redesign, 2026-05-23).

Roda compute_drill_dc/pdd/cpr contra REALINVEST em 2 datas:
  - 2026-05-15 (dia tipico — fechamento limpo)
  - 2026-04-13 (segunda-feira — espera-se detectar mutacao silenciosa
                DID99746 SYSTEMPACK→BPM no PDD, ver memo F5)

Read-only — seguro mesmo em dev=prod.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

# Force UTF-8 output on Windows (cp1252 default cant render Σ/Δ).
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.modules.cadastros.public import UnidadeAdministrativa  # noqa: E402
from app.modules.controladoria.services.cota_sub_drill_cpr import compute_drill_cpr  # noqa: E402
from app.modules.controladoria.services.cota_sub_drill_dc import compute_drill_dc  # noqa: E402
from app.modules.controladoria.services.cota_sub_drill_pdd import compute_drill_pdd  # noqa: E402


async def _run_drill_dc(db, *, tenant_id, ua_id, data_d0):
    result = await compute_drill_dc(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    print(f"\n--- DRILL DC · {result.fundo_nome} · D-1={result.data_anterior} D0={result.data} ---")
    print(f"Aquisicoes:       {result.aquisicoes_qtd:>4} papeis  R$ {result.aquisicoes_total:>14,.2f}")
    print(f"Liquidacoes:      {result.liquidacoes_qtd:>4} papeis  R$ {result.liquidacoes_total:>14,.2f}")
    print("\nLiquidacoes por tipo_movimento:")
    for t in result.liquidacoes_por_tipo:
        print(
            f"  {t.tipo_movimento:35s} qtd={t.qtd_papeis:>3}  "
            f"pago={t.sum_valor_pago:>14,.2f}  ganho={t.ganho_liquido:>+12,.2f}"
        )
    a = result.apropriacao
    print("\nApropriacao derivada:")
    print(f"  ΔEstoque (consolidado)   R$ {a.delta_estoque:>+14,.2f}  ({a.estoque_d1:,.2f} → {a.estoque_d0:,.2f})")
    print(f"  + Liquidacoes (saida)    R$ {a.liquidacoes_total:>+14,.2f}")
    print(f"  - Aquisicoes (entrada)   R$ {a.aquisicoes_total:>+14,.2f}")
    print(f"  = Apropriacao            R$ {a.apropriacao:>+14,.2f}")


async def _run_drill_pdd(db, *, tenant_id, ua_id, data_d0, expect_silent_mutation=False):
    result = await compute_drill_pdd(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    print(f"\n--- DRILL PDD · {result.fundo_nome} · D-1={result.data_anterior} D0={result.data} ---")
    print(f"PDD consolidado:  D-1={result.pdd_consolidado_d1:>14,.2f}  D0={result.pdd_consolidado_d0:>14,.2f}  Δ={result.pdd_consolidado_delta:>+14,.2f}")
    print(f"PDD granular:     D-1={result.pdd_granular_d1:>14,.2f}  D0={result.pdd_granular_d0:>14,.2f}")
    if not result.estoque_disponivel_d1 or not result.estoque_disponivel_d0:
        print(f"  ! Granular indisponivel: {result.motivo_indisponivel}")
        return

    print("\nMatriz de migracao (top celulas por |Δ PDD|):")
    print(f"  {'De':5s} {'Para':5s} {'Qtd':>5s}  {'Σ Δ PDD':>14s}")
    for cel in result.matriz[:12]:
        marker = "  ⚠" if cel.faixa_para == "WOP" else "   "
        print(
            f"{marker}{cel.faixa_de:5s} {cel.faixa_para:5s} {cel.qtd_papeis:>5}  "
            f"{cel.sum_delta_pdd:>+14,.2f}"
        )

    if result.papeis_wop:
        print(f"\nPapeis em WOP (write-off):  {len(result.papeis_wop)} papel(eis)  Σ PDD perdido R$ {result.papeis_wop_total_pdd_d1:>14,.2f}")
        for p in result.papeis_wop[:5]:
            print(
                f"  {p.cedente_nome[:25]:25s} / {p.sacado_nome[:25]:25s}  "
                f"{p.seu_numero[:15]:15s}  PDD_d1=R$ {p.valor_pdd_d1:,.2f}"
            )

    print(f"\nTop {len(result.top_papeis)} papeis por |Δ PDD|:")
    for p in result.top_papeis[:5]:
        print(
            f"  {p.cedente_nome[:25]:25s} / {p.sacado_nome[:25]:25s}  "
            f"{p.faixa_pdd_d1 or '—':>3s}→{p.faixa_pdd_d0 or '—':3s}  "
            f"Δ R$ {p.delta_valor_pdd:>+12,.2f}"
        )

    if expect_silent_mutation:
        # F5 — DID99746 valor_nominal -R$ 22.795 entre 10/04 e 13/04
        print("\n  (F5 — esperado: mutacao silenciosa DID99746 ou similar)")


async def _run_drill_cpr(db, *, tenant_id, ua_id, data_d0):
    result = await compute_drill_cpr(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    print(f"\n--- DRILL CPR · {result.fundo_nome} · D-1={result.data_anterior} D0={result.data} ---")
    print(f"CPR total:        D-1={result.cpr_total_d1:>14,.2f}  D0={result.cpr_total_d0:>14,.2f}  Δ={result.cpr_total_delta:>+14,.2f}")
    print(f"Linhas:           D-1={result.qtd_linhas_d1:>4}  D0={result.qtd_linhas_d0:>4}")

    print("\nPor natureza:")
    for n in result.naturezas:
        print(
            f"  {n.label:50s} qtd={n.qtd_linhas:>4}  "
            f"Δ R$ {n.sum_delta:>+14,.2f}"
        )

    if result.aportes_engaiolados:
        print(f"\nAportes engaiolados detectados: {len(result.aportes_engaiolados)}")
        for ev in result.aportes_engaiolados:
            print(
                f"  [{ev.estado:>10s}] {ev.descricao[:40]:40s}  "
                f"D-1={ev.valor_d1:>+14,.2f}  D0={ev.valor_d0:>+14,.2f}  "
                f"Δ={ev.delta_valor:>+14,.2f}"
            )


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

        print(f"\n{'='*100}")
        print("REALINVEST FIDC · 2026-05-15 (dia tipico)")
        print(f"{'='*100}")
        await _run_drill_dc(db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=date(2026, 5, 15))
        await _run_drill_pdd(db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=date(2026, 5, 15))
        await _run_drill_cpr(db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=date(2026, 5, 15))

        print(f"\n{'='*100}")
        print("REALINVEST FIDC · 2026-04-13 (caso pedagogico mutacao silenciosa DID99746)")
        print(f"{'='*100}")
        await _run_drill_dc(db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=date(2026, 4, 13))
        await _run_drill_pdd(
            db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=date(2026, 4, 13),
            expect_silent_mutation=True,
        )
        await _run_drill_cpr(db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=date(2026, 4, 13))


if __name__ == "__main__":
    asyncio.run(main())
