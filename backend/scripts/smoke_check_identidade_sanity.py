"""Smoke do Nivel 1 grosso em check_identidade_contabil (tools grossas, 2026-05-29).

Valida que a decisao do Nivel 1 (antes regras no prompt v8) vem pronta e
consistente na tool: severidade pelas bandas R$100/R$5.000, deve_continuar,
alerta_sugerido e acao_sugerida.

Asserções:
  1. Consistencia interna por dia: severidade/deve_continuar/alerta/acao
     derivam corretamente das bandas a partir de |residuo|.
  2. 22/05 (furo material conhecido ~-12k): severidade critico, deve_continuar
     False, alerta+acao presentes.
  3. Dia tipico (12/05): severidade ok, deve_continuar True, sem alerta/acao.

Read-only. dev=prod seguro.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.agentic._scope import ScopedContext  # noqa: E402
from app.agentic.tools.controladoria.cota_sub import check_identidade_contabil  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.enums import Module, Permission  # noqa: E402

_failures: list[str] = []
ATENCAO = Decimal("100")
CRITICO = Decimal("5000")


def _check(cond: bool, label: str) -> None:
    if not cond:
        print(f"  FAIL  {label}")
        _failures.append(label)


def _esperado(residuo: Decimal) -> str:
    a = abs(residuo)
    if a >= CRITICO:
        return "critico"
    if a >= ATENCAO:
        return "atencao"
    return "ok"


async def _dia(db, *, tenant_id, ua_id, data_d0: date) -> dict:
    scope = ScopedContext(
        tenant_id=tenant_id, empresa_id=None, user_id=uuid4(),
        module=Module.CONTROLADORIA, permissions={Module.CONTROLADORIA: Permission.READ},
        db=db, extras={"ua_id": str(ua_id), "data_d0": data_d0.isoformat()},
    )
    out = json.loads(await check_identidade_contabil(scope, {}))
    residuo = Decimal(str(out["residuo_brl"]))
    esp = _esperado(residuo)
    print(f"  {data_d0.isoformat()}  residuo={float(residuo):+10.2f}  sev={out['severidade']:7}  "
          f"continuar={out['deve_continuar']}  alerta={'sim' if out['alerta_sugerido'] else '-'}  "
          f"acao={'sim' if out['acao_sugerida'] else '-'}")

    # 1. Consistencia interna.
    _check(out["severidade"] == esp, f"{data_d0}: severidade == {esp}")
    _check(out["deve_continuar"] == (esp != "critico"), f"{data_d0}: deve_continuar coerente")
    _check((out["alerta_sugerido"] is not None) == (esp in ("atencao", "critico")),
           f"{data_d0}: alerta presente sse atencao/critico")
    _check((out["acao_sugerida"] is not None) == (esp == "critico"),
           f"{data_d0}: acao presente sse critico")
    if out["alerta_sugerido"]:
        _check(out["alerta_sugerido"]["tipo"] == "residuo_alto",
               f"{data_d0}: alerta tipo residuo_alto")
        _check(out["alerta_sugerido"]["severidade"] == esp,
               f"{data_d0}: alerta severidade == {esp}")
    return out


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
        tenant_id: UUID
        ua_id: UUID
        tenant_id, ua_id = row
        print("=== scan REALINVEST (Nivel 1) ===")
        dias = [date(2026, 5, d) for d in (12, 13, 14, 15, 18, 19, 20, 21, 22, 25, 26, 27)]
        outs = {}
        for d in dias:
            outs[d] = await _dia(db, tenant_id=tenant_id, ua_id=ua_id, data_d0=d)

        # 2. 22/05 furo material conhecido.
        o22 = outs[date(2026, 5, 22)]
        _check(o22["severidade"] == "critico", "22/05 severidade == critico")
        _check(o22["deve_continuar"] is False, "22/05 deve_continuar == False")
        _check(o22["acao_sugerida"] is not None, "22/05 acao_sugerida presente")

        # 3. Dia tipico limpo.
        o12 = outs[date(2026, 5, 12)]
        _check(o12["severidade"] == "ok", "12/05 severidade == ok")
        _check(o12["alerta_sugerido"] is None, "12/05 sem alerta")

    await engine.dispose()

    print(f"\n{'='*80}")
    if _failures:
        print(f"FALHOU — {len(_failures)} assercoes:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("TODAS as assercoes passaram. Nivel 1 (sanity) grosso OK.")


if __name__ == "__main__":
    asyncio.run(main())
