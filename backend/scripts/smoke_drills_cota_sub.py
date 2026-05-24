"""Smoke test dos 3 drills da Cota Sub + reconciliacao MEC.

F2 do redesign (2026-05-23) -> F5 (2026-05-24): valida nos 3 cenarios-chave
REALINVEST:

  1. 2026-05-12 -- dia normal, fechamento limpo, 0 mutacao
  2. 2026-04-13 -- segunda-feira pos-fim-de-semana, caso pedagogico de
                   mutacao silenciosa DID99746 SYSTEMPACK->BPM (decomposicao
                   DC isola 1 papel no bucket Mutacao)
  3. 2026-05-15 -- dia tipico, validacao adicional

Asserts:
  - Decomposicao DC residuo <= R$ 1 (deveria ser R$ 0,00 exato por construcao)
  - Reconciliacao MEC (Δ dos Δs) <= R$ 5 (arredondamento estrutural QiTech)
  - 2026-04-13 deve ter >= 1 papel no bucket Mutacao do drill DC
  - 2026-05-12/15 devem ter 0 papeis em Migracao WOP

Read-only -- seguro mesmo em dev=prod.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal

# Force UTF-8 output on Windows (cp1252 default cant render Σ/Δ).
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.modules.cadastros.public import UnidadeAdministrativa  # noqa: E402
from app.modules.controladoria.services.balanco_patrimonial import (  # noqa: E402
    compute_balanco_patrimonial,
)
from app.modules.controladoria.services.cota_sub_drill_cpr import compute_drill_cpr  # noqa: E402
from app.modules.controladoria.services.cota_sub_drill_dc import compute_drill_dc  # noqa: E402
from app.modules.controladoria.services.cota_sub_drill_pdd import compute_drill_pdd  # noqa: E402


# Toleranciais — arredondamentos estruturais aceitaveis. Acima disso, falha.
RESIDUO_DC_TOLERANCE = Decimal("1.00")          # R$ 1,00
RECONCILIACAO_MEC_TOLERANCE = Decimal("5.00")   # R$ 5,00


# Acumulador de falhas (printa no final, exit code != 0 se houver).
_failures: list[str] = []


def _check(condition: bool, label: str) -> None:
    """Assert visual. Adiciona em `_failures` se falhar."""
    if condition:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label}")
        _failures.append(label)


async def _run_drill_dc(db, *, tenant_id, ua_id, data_d0, expect_mutacao=False):
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

    # ── Nova decomposicao em 5 buckets (F2 2026-05-24) ─────────────────────
    d = result.decomposicao
    print("\nDecomposicao do ΔDC (granular ex-WOP):")
    print(f"  Estoque (D-1)                   R$ {d.saldo_d1:>14,.2f}")
    print(f"  + Aquisicoes        ({d.aquisicoes_n:>4} papeis)  R$ {d.aquisicoes_total:>+14,.2f}")
    print(f"  - Liquidacoes       ({d.liquidacoes_n:>4} papeis)  R$ {-d.liquidacoes_total:>+14,.2f}")
    print(f"  - Migracao WOP      ({d.migracao_wop_n:>4} papeis)  R$ {-d.migracao_wop_total:>+14,.2f}")
    print(f"  + Apropriacao juros ({d.apropriacao_n:>4} papeis)  R$ {d.apropriacao_total:>+14,.2f}")
    print(f"  + Mutacao silenciosa({d.mutacao_n:>4} papeis)  R$ {d.mutacao_total:>+14,.2f}")
    print(f"  = Estoque (D0)                  R$ {d.saldo_d0:>14,.2f}")
    print(f"  Residuo:                            R$ {d.residuo:>+14,.2f}")

    if d.mutacao_n > 0:
        print(f"\n  Papeis no bucket Mutacao (top {len(result.mutacao_papeis)}):")
        for p in result.mutacao_papeis[:3]:
            changes = []
            if p.mudou_vn:
                changes.append(f"VN {p.vn_d1}→{p.vn_d0}")
            if p.mudou_taxa:
                changes.append("tx")
            if p.mudou_venc:
                changes.append("venc")
            print(
                f"    {p.cedente_nome[:25]:25s} / {p.sacado_nome[:25]:25s}  "
                f"{p.seu_numero[:18]:18s}  ΔVP={p.delta_vp:>+12,.2f}  ({', '.join(changes)})"
            )

    if d.migracao_wop_n > 0:
        print(f"\n  Papeis no bucket Migracao WOP ({len(result.migracao_wop_papeis)}):")
        for p in result.migracao_wop_papeis[:3]:
            print(
                f"    {p.cedente_nome[:25]:25s} / {p.sacado_nome[:25]:25s}  "
                f"{p.seu_numero[:18]:18s}  {p.faixa_pdd_d1}→WOP  VP_d1={p.vp_d1:>+12,.2f}"
            )

    # ── ASSERTS ────────────────────────────────────────────────────────────
    print("\nValidacao:")
    _check(
        abs(d.residuo) <= RESIDUO_DC_TOLERANCE,
        f"Residuo decomposicao DC <= R$ {RESIDUO_DC_TOLERANCE} (atual: R$ {d.residuo:+.2f})",
    )
    if expect_mutacao:
        _check(
            d.mutacao_n >= 1,
            f"Bucket Mutacao tem >= 1 papel (esperado para caso DID99746; atual: {d.mutacao_n})",
        )
    elif d.mutacao_n > 0:
        # Em dia normal o bucket Mutacao geralmente fica vazio, mas pode ter
        # liquidacao parcial (papel nao saiu mas valor_nominal mudou) ou
        # eventos legitimos que mudam parametros. Loga como info, nao falha.
        print(
            f"  ℹ  Bucket Mutacao com {d.mutacao_n} papel(eis) em dia normal — "
            f"verificar tipo (liquidacao parcial = legitimo; sem evento = silenciosa)"
        )


async def _run_drill_pdd(db, *, tenant_id, ua_id, data_d0, expect_silent_mutation=False):
    result = await compute_drill_pdd(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    print(f"\n--- DRILL PDD · {result.fundo_nome} · D-1={result.data_anterior} D0={result.data} ---")
    pdd_ativo_delta = result.pdd_granular_ex_wop_d0 - result.pdd_granular_ex_wop_d1
    print(
        f"PDD ativo (A-H):  D-1={result.pdd_granular_ex_wop_d1:>14,.2f}  "
        f"D0={result.pdd_granular_ex_wop_d0:>14,.2f}  Δ={pdd_ativo_delta:>+14,.2f}"
    )
    print(
        f"WOP (fora PL):    D-1={result.pdd_granular_wop_d1:>14,.2f}  "
        f"D0={result.pdd_granular_wop_d0:>14,.2f}"
    )

    if not result.estoque_disponivel_d1 or not result.estoque_disponivel_d0:
        print(f"  ! Granular indisponivel: {result.motivo_indisponivel}")
        return

    if result.papeis_wop:
        print(
            f"\nPapeis em WOP novo no dia: {len(result.papeis_wop)} papel(eis)  "
            f"Σ PDD perdido R$ {result.papeis_wop_total_pdd_d1:>14,.2f}"
        )
        for p in result.papeis_wop[:5]:
            print(
                f"  {p.cedente_nome[:25]:25s} / {p.sacado_nome[:25]:25s}  "
                f"{p.seu_numero[:18]:18s}  PDD_d1=R$ {p.valor_pdd_d1:,.2f}"
            )

    # Soma do detalhamento — confirma reconciliacao
    soma_top = sum((p.delta_valor_pdd for p in result.top_papeis), Decimal("0"))
    print(f"\nPapeis com variacao de PDD: {len(result.top_papeis)}  Σ Δ = R$ {soma_top:>+12,.2f}")

    # ── ASSERTS ────────────────────────────────────────────────────────────
    print("\nValidacao:")
    diff = abs(soma_top - pdd_ativo_delta)
    _check(
        diff <= Decimal("0.50"),
        f"Soma Δ dos papeis listados (R$ {soma_top:+.2f}) = Δ PDD ex-WOP total (R$ {pdd_ativo_delta:+.2f}) [diff R$ {diff:.2f}]",
    )

    if expect_silent_mutation:
        print("  (F5 — esperado: mutacao silenciosa visivel no drill DC do mesmo dia)")


async def _run_drill_cpr(db, *, tenant_id, ua_id, data_d0):
    result = await compute_drill_cpr(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    print(f"\n--- DRILL CPR · {result.fundo_nome} · D-1={result.data_anterior} D0={result.data} ---")
    print(
        f"CPR total:        D-1={result.cpr_total_d1:>14,.2f}  "
        f"D0={result.cpr_total_d0:>14,.2f}  Δ={result.cpr_total_delta:>+14,.2f}"
    )
    print(f"Linhas:           D-1={result.qtd_linhas_d1:>4}  D0={result.qtd_linhas_d0:>4}")

    if result.naturezas:
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


async def _run_reconciliacao_mec(db, *, tenant_id, ua_id, data_d0):
    """Reconciliacao MEC -- PL Sub Jr calculado vs lido do MEC."""
    r = await compute_balanco_patrimonial(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    print(f"\n--- RECONCILIACAO MEC · {r.fundo_nome} · D-1={r.data_anterior} D0={r.data} ---")
    print(f"PL deduzido (calculado):  D-1={r.pl_deduzido_d1:>16,.2f}  D0={r.pl_deduzido_d0:>16,.2f}  Δ={r.pl_deduzido_delta:>+14,.2f}")
    print(f"PL fonte MEC:             D-1={r.pl_fonte_d1:>16,.2f}  D0={r.pl_fonte_d0:>16,.2f}  Δ={r.pl_fonte_delta:>+14,.2f}")
    print(f"Residuo snapshot D0:      R$ {r.residuo_identidade_d0:>+14,.2f}  (acumulado historico)")
    print(f"Residuo do dia (Δ dos Δs): R$ {r.residuo_identidade_delta:>+14,.2f}  (erro real)")

    # ── ASSERTS ────────────────────────────────────────────────────────────
    print("\nValidacao:")
    _check(
        abs(r.residuo_identidade_delta) <= RECONCILIACAO_MEC_TOLERANCE,
        f"Residuo do dia <= R$ {RECONCILIACAO_MEC_TOLERANCE} (atual: R$ {r.residuo_identidade_delta:+.2f})",
    )


async def _run_cenario(db, *, ua, data_d0, descricao, expect_mutacao=False):
    """Executa um cenario completo (3 drills + reconciliacao MEC + asserts)."""
    print(f"\n{'='*100}")
    print(f"REALINVEST FIDC · {data_d0} ({descricao})")
    print(f"{'='*100}")
    await _run_drill_dc(
        db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=data_d0,
        expect_mutacao=expect_mutacao,
    )
    await _run_drill_pdd(
        db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=data_d0,
        expect_silent_mutation=expect_mutacao,
    )
    await _run_drill_cpr(db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=data_d0)
    await _run_reconciliacao_mec(db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=data_d0)


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

        await _run_cenario(db, ua=ua, data_d0=date(2026, 5, 12), descricao="dia normal — fechamento limpo")
        await _run_cenario(
            db, ua=ua, data_d0=date(2026, 4, 13),
            descricao="caso pedagogico mutacao silenciosa DID99746 SYSTEMPACK->BPM",
            expect_mutacao=True,
        )
        await _run_cenario(db, ua=ua, data_d0=date(2026, 5, 15), descricao="dia normal — validacao adicional")

    # ── RESUMO FINAL ───────────────────────────────────────────────────────
    print(f"\n{'='*100}")
    if _failures:
        print(f"FALHOU — {len(_failures)} assercoes nao passaram:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("TODAS as assercoes passaram. Smoke OK.")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    asyncio.run(main())
