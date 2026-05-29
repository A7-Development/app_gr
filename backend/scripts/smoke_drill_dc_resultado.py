"""Smoke do `resultado_do_dia` no drill DC (tools grossas, 2026-05-29).

Valida a camada nova que moveu a "regra dura de sinal" do prompt do agente
para dentro da tool `get_drill_dc`:

  1. renda_multa_juros == -Σ(sum_ajuste<0) e desconto_concedido == Σ(sum_ajuste>0)
     (reconcilia com os por_tipo do proprio payload).
  2. impacto_resultado_brl == -sum_ajuste em cada tipo e -ajuste em cada linha.
  3. ajuste_liquido_resultado == renda_multa_juros - desconto_concedido.
  4. carrego_apropriacao == decomposicao.apropriacao_total; giro == buckets.
  5. sugestao.classificacao_sugerida coerente:
       - 14/05 (lote BAIXA POR DEPOSITO SACADO, multa/juros ~R$ 35,6k) ->
         evento_pontual_explicado (resultado_outlier).
       - 20/05 (dia tipico no DC) -> carrego_normal.

Read-only. dev=prod seguro.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.agentic.tools.controladoria.cota_sub import _sugestao_drill_dc  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.modules.controladoria.services.cota_sub_drill_dc import (  # noqa: E402
    compute_drill_dc,
)

_failures: list[str] = []
TOL = Decimal("0.01")


def _check(cond: bool, label: str) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _failures.append(label)


def _fmt(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def _cenario(db, *, tenant_id, ua_id, data_d0: date, esperado_classif: str) -> None:
    print(f"\n=== REALINVEST {data_d0.isoformat()} ===")
    r = await compute_drill_dc(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0)
    res = r.resultado_do_dia
    assert res is not None, "resultado_do_dia ausente"

    print(f"  carrego={_fmt(res.carrego_apropriacao)}  "
          f"multa/juros={_fmt(res.renda_multa_juros)}  "
          f"desconto={_fmt(res.desconto_concedido)}  "
          f"ajuste_liq={_fmt(res.ajuste_liquido_resultado)}")
    print(f"  mutacao={_fmt(res.mutacao_total)}  wop={_fmt(res.migracao_wop_total)}  "
          f"motor={res.motor_dominante}  outlier={res.resultado_outlier}")
    print(f"  giro: aquis={_fmt(res.giro_aquisicoes)}  liq={_fmt(res.giro_liquidacoes)}")

    # 1. renda/desconto reconciliam com os por_tipo (fonte independente).
    renda_recalc = sum(
        (-t.sum_ajuste for t in r.liquidacoes_por_tipo if t.sum_ajuste < 0), Decimal("0"),
    )
    desconto_recalc = sum(
        (t.sum_ajuste for t in r.liquidacoes_por_tipo if t.sum_ajuste > 0), Decimal("0"),
    )
    # por_tipo agrega por tipo; renda/desconto do service sao split por LINHA.
    # Sao iguais quando nenhum tipo tem ajuste de sinais mistos (caso REALINVEST).
    _check(abs(res.renda_multa_juros - renda_recalc) < TOL,
           f"renda_multa_juros ({_fmt(res.renda_multa_juros)}) == -Σ(por_tipo ajuste<0)")
    _check(abs(res.desconto_concedido - desconto_recalc) < TOL,
           f"desconto_concedido ({_fmt(res.desconto_concedido)}) == Σ(por_tipo ajuste>0)")

    # 2. impacto_resultado_brl == -sum_ajuste em cada tipo.
    sinais_ok = all(
        abs(t.impacto_resultado_brl - (-t.sum_ajuste)) < TOL for t in r.liquidacoes_por_tipo
    )
    _check(sinais_ok, "impacto_resultado_brl == -sum_ajuste em todos os tipos")
    linhas_ok = all(
        abs(ln.impacto_resultado_brl - (-ln.ajuste)) < TOL for ln in r.liquidacoes_top
    )
    _check(linhas_ok, "impacto_resultado_brl == -ajuste em todas as linhas top")

    # 3. ajuste_liquido == renda - desconto.
    _check(abs(res.ajuste_liquido_resultado - (res.renda_multa_juros - res.desconto_concedido)) < TOL,
           "ajuste_liquido == renda - desconto")

    # 4. carrego/giro espelham a decomposicao.
    _check(res.carrego_apropriacao == r.decomposicao.apropriacao_total,
           "carrego == decomposicao.apropriacao_total")
    _check(res.giro_aquisicoes == r.decomposicao.aquisicoes_total
           and res.giro_liquidacoes == r.decomposicao.liquidacoes_total,
           "giro == buckets aquisicoes/liquidacoes")

    # 5. sugestao.
    sug = _sugestao_drill_dc(r)
    print(f"  sugestao.classificacao = {sug['classificacao_sugerida']}  "
          f"(esperado {esperado_classif})")
    print(f"  alerta = {sug['alerta_sugerido']['tipo'] if sug['alerta_sugerido'] else None}")
    print(f"  resumo: {sug['resumo_factual']}")
    _check(sug["classificacao_sugerida"] == esperado_classif,
           f"classificacao_sugerida == {esperado_classif}")


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
        await _cenario(db, tenant_id=tenant_id, ua_id=ua_id,
                       data_d0=date(2026, 5, 14), esperado_classif="evento_pontual_explicado")
        await _cenario(db, tenant_id=tenant_id, ua_id=ua_id,
                       data_d0=date(2026, 5, 20), esperado_classif="carrego_normal")
    await engine.dispose()

    print(f"\n{'='*80}")
    if _failures:
        print(f"FALHOU — {len(_failures)} assercoes:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("TODAS as assercoes passaram. resultado_do_dia OK.")


if __name__ == "__main__":
    asyncio.run(main())
