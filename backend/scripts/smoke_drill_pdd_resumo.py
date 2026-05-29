"""Smoke do `resumo` + `efeito_vagao` no drill PDD (tools grossas, 2026-05-29).

Valida a camada nova que moveu a "regra dura -- NAO inverter" + a heuristica de
"efeito vagao" do prompt do agente para dentro da tool `get_drill_pdd`:

  1. RECONCILIACAO: resumo.delta_liquido == pdd_granular_ex_wop_d0 -
     pdd_granular_ex_wop_d1 (a constituicao/reversao split fecha com o
     consolidado ex-WOP).
  2. constituicao_total >= 0, reversao_total <= 0, impacto_pl_sub == -delta_liquido.
  3. Integridade de cada grupo de efeito_vagao: qtd == vencidos + a_vencer,
     vencidos >= 1, qtd >= 2.
  4. Casos reais (independente confirmado via SQL):
       - 20/05: MEGA PACK PLASTICOS arrastado p/ faixa B (1 vencido + 1 a vencer).
       - 11/05: RIO DE JANEIRO REFRESCOS p/ faixa F (Σ PDD ~R$ 32,9k).
  5. sugestao.classificacao_sugerida coerente com resumo.direcao.

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

from app.agentic.tools.controladoria.cota_sub import _sugestao_drill_pdd  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.modules.controladoria.services.cota_sub_drill_pdd import (  # noqa: E402
    compute_drill_pdd,
)

_failures: list[str] = []
TOL = Decimal("1.0")


def _check(cond: bool, label: str) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _failures.append(label)


def _fmt(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def _cenario(
    db, *, tenant_id, ua_id, data_d0: date, sacado_esperado: str, faixa_esperada: str,
) -> None:
    print(f"\n=== REALINVEST {data_d0.isoformat()} ===")
    r = await compute_drill_pdd(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0)
    res = r.resumo
    assert res is not None, "resumo ausente (granular indisponivel?)"

    print(f"  constituicao={_fmt(res.constituicao_total)}  reversao={_fmt(res.reversao_total)}  "
          f"liquido={_fmt(res.delta_liquido)}  direcao={res.direcao}  "
          f"impacto_pl={_fmt(res.impacto_pl_sub)}")
    print(f"  ex_wop d1={_fmt(r.pdd_granular_ex_wop_d1)} d0={_fmt(r.pdd_granular_ex_wop_d0)}")
    print(f"  efeito_vagao: {len(r.efeito_vagao)} grupo(s)")
    for v in r.efeito_vagao[:6]:
        print(f"    - {v.sacado_nome[:34]:34} ->{v.faixa_para} qtd={v.qtd_papeis} "
              f"(venc={v.qtd_vencidos}/arr={v.qtd_a_vencer_arrastados}) "
              f"Σpdd={_fmt(v.sum_delta_pdd)} puxador={v.documento_puxador}")

    # 1. RECONCILIACAO com consolidado ex-WOP.
    ex_wop_delta = r.pdd_granular_ex_wop_d0 - r.pdd_granular_ex_wop_d1
    _check(abs(res.delta_liquido - ex_wop_delta) < TOL,
           f"delta_liquido ({_fmt(res.delta_liquido)}) == Δ granular ex-WOP ({_fmt(ex_wop_delta)})")

    # 2. Sinais.
    _check(res.constituicao_total >= 0, "constituicao_total >= 0")
    _check(res.reversao_total <= 0, "reversao_total <= 0")
    _check(res.impacto_pl_sub == -res.delta_liquido, "impacto_pl_sub == -delta_liquido")
    _check(abs((res.constituicao_total + res.reversao_total) - res.delta_liquido) < TOL,
           "constituicao + reversao == delta_liquido")

    # 3. Integridade dos grupos de vagao.
    grupos_ok = all(
        v.qtd_papeis == v.qtd_vencidos + v.qtd_a_vencer_arrastados
        and v.qtd_vencidos >= 1 and v.qtd_papeis >= 2
        and len(v.documentos_arrastados) == v.qtd_a_vencer_arrastados
        for v in r.efeito_vagao
    )
    _check(grupos_ok, "todos grupos vagao: qtd == venc+arrastados, venc>=1, qtd>=2")

    # 4. Caso real esperado presente.
    achou = next(
        (v for v in r.efeito_vagao
         if sacado_esperado in v.sacado_nome and v.faixa_para == faixa_esperada),
        None,
    )
    _check(achou is not None,
           f"efeito_vagao contem '{sacado_esperado}' -> faixa {faixa_esperada}")

    # 5. sugestao coerente.
    sug = _sugestao_drill_pdd(r)
    esperada_classif = {"constituicao": "constituicao_pdd",
                        "reversao": "reversao_pdd", "neutro": None}[res.direcao]
    print(f"  sugestao.classificacao = {sug['classificacao_sugerida']} (esperado {esperada_classif})")
    print(f"  alerta = {sug['alerta_sugerido']['entidade'] if sug['alerta_sugerido'] else None}")
    print(f"  resumo: {sug['resumo_factual']}")
    _check(sug["classificacao_sugerida"] == esperada_classif,
           f"classificacao_sugerida == {esperada_classif}")


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
        await _cenario(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=date(2026, 5, 20),
                       sacado_esperado="MEGA PACK PLASTICOS", faixa_esperada="B")
        await _cenario(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=date(2026, 5, 11),
                       sacado_esperado="RIO DE JANEIRO REFRESCOS", faixa_esperada="F")
    await engine.dispose()

    print(f"\n{'='*80}")
    if _failures:
        print(f"FALHOU — {len(_failures)} assercoes:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("TODAS as assercoes passaram. resumo + efeito_vagao OK.")


if __name__ == "__main__":
    asyncio.run(main())
