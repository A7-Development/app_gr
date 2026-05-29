"""Smoke da camada `sugestao` em get_decomposicao_classes (tools grossas, 2026-05-29).

Valida o mapeamento classificacao+alerta que saiu do prompt do agente:

  1. por_classe.classificacao_sugerida mapeia o enum (aporte_classe/resgate_classe/
     carrego_normal) a partir da classificacao de dominio.
  2. impacto_pl_sub_do_capital com sinal correto: prioritaria (Sr/Mez) aporte>0
     REDUZ o PL Sub (negativo); subordinada aporte>0 AUMENTA (positivo).
  3. Caso canonico REALINVEST 20/05: Mezanino aporte ~R$ 119,5k + valorizacao
     ~R$ 1,95k -> aporte_classe + alerta de captacao material.
  4. Dia sem evento de capital -> carrego_normal, sem alertas (14/05).

Read-only. dev=prod seguro.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.agentic.tools.controladoria.cota_sub import (  # noqa: E402
    _sugestao_decomposicao_classes,
)
from app.core.config import get_settings  # noqa: E402
from app.modules.controladoria.services.balanco_patrimonial import (  # noqa: E402
    compute_decomposicao_classes_mec,
)

_failures: list[str] = []


def _check(cond: bool, label: str) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _failures.append(label)


async def _cenario(db, *, tenant_id, ua_id, data_d0: date) -> dict:
    print(f"\n=== REALINVEST {data_d0.isoformat()} ===")
    r = await compute_decomposicao_classes_mec(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    r["sugestao"] = _sugestao_decomposicao_classes(r)
    sug = r["sugestao"]
    print(f"  limiar_capital = R$ {sug['limiar_capital_brl']:,.2f}")
    for c in r["classes"]:
        pc = sug["por_classe"][c["classe"]]
        print(f"    {c['label']:16} cap={c['efeito_capital']:>14,.2f} "
              f"valoriz={c['efeito_valorizacao']:>12,.2f} -> {pc['classificacao_sugerida']} "
              f"(impacto_sub {pc['impacto_pl_sub_do_capital']:+,.2f})")
    for a in sug["alertas_sugeridos"]:
        print(f"    ALERTA [{a['entidade']}]: {a['descricao']}")

    # Consistencia geral: cada classe mapeou pra um enum valido ou None.
    validos = {"aporte_classe", "resgate_classe", "carrego_normal", None}
    _check(all(pc["classificacao_sugerida"] in validos for pc in sug["por_classe"].values()),
           "classificacao_sugerida em {aporte_classe, resgate_classe, carrego_normal, None}")
    return r


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

        # 20/05: aporte Mezanino canonico.
        r20 = await _cenario(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=date(2026, 5, 20))
        mez = r20["sugestao"]["por_classe"].get("mezanino")
        _check(mez is not None and mez["classificacao_sugerida"] == "aporte_classe",
               "20/05 Mezanino -> aporte_classe")
        _check(mez is not None and mez["impacto_pl_sub_do_capital"] < 0,
               "20/05 Mezanino aporte REDUZ o PL Sub (impacto < 0)")
        _check(any("Mezanino" in a["entidade"] for a in r20["sugestao"]["alertas_sugeridos"]),
               "20/05 alerta de captacao na Mezanino presente")

        # 14/05: dia sem evento de capital material esperado.
        r14 = await _cenario(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=date(2026, 5, 14))
        _check(len(r14["sugestao"]["alertas_sugeridos"]) == 0,
               "14/05 sem alertas de captacao (so valorizacao)")

    await engine.dispose()

    print(f"\n{'='*80}")
    if _failures:
        print(f"FALHOU — {len(_failures)} assercoes:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("TODAS as assercoes passaram. sugestao de classes OK.")


if __name__ == "__main__":
    asyncio.run(main())
