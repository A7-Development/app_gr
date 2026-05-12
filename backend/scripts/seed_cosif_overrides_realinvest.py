"""Seed dos overrides COSIF do REALINVEST.

Simula o que o admin do tenant a7-credit preencheria via UI
`/admin/controladoria/cosif/<fundo>/overrides` apos ver os pendentes:

  wh_saldo_conta_corrente / BRADESCO   -> 1.1.2.80.00.002
  wh_saldo_conta_corrente / SOCOPA     -> 1.1.2.80.00.007
  wh_saldo_conta_corrente / CONCILIA   -> 4.9.9.30.90.005
  wh_posicao_cota_fundo  / REALIAVE    -> 1.6.1.30.00.001
  wh_posicao_cota_fundo  / REALIVEN    -> 1.6.1.30.00.002
  wh_posicao_outros_ativos / PDD       -> 1.6.9.97.00.001

Idempotente — usa ON CONFLICT do UQ.

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/seed_cosif_overrides_realinvest.py
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from sqlalchemy import text


OVERRIDES: list[tuple[str, str, str, str | None]] = [
    # (silver_origin, identificador, cosif, classe)
    ("wh_saldo_conta_corrente", "BRADESCO", "1.1.2.80.00.002", None),
    ("wh_saldo_conta_corrente", "SOCOPA",   "1.1.2.80.00.007", None),
    ("wh_saldo_conta_corrente", "CONCILIA", "4.9.9.30.90.005", None),
    ("wh_posicao_cota_fundo",   "REALIAVE", "1.6.1.30.00.001", None),
    ("wh_posicao_cota_fundo",   "REALIVEN", "1.6.1.30.00.002", None),
    ("wh_posicao_outros_ativos","PDD",      "1.6.9.97.00.001", None),
]


async def main() -> int:
    async with AsyncSessionLocal() as db:
        tenant_id = await db.scalar(
            text("SELECT id FROM tenants WHERE slug = 'a7-credit'")
        )
        ua_id = await db.scalar(
            text(
                "SELECT id FROM cadastros_unidade_administrativa "
                "WHERE nome = 'REALINVEST FIDC'"
            )
        )
        if tenant_id is None or ua_id is None:
            print("Tenant ou UA REALINVEST FIDC nao encontrados.", file=sys.stderr)
            return 1

        for silv, ident, cosif, classe in OVERRIDES:
            await db.execute(text("""
                INSERT INTO tenant_papel_classificacao
                  (tenant_id, fundo_id, silver_origin, identificador,
                   cosif_override, classe_sr_mez_sub, motivo)
                VALUES
                  (:t, :f, :s, :i, :c, :cls, :motivo)
                ON CONFLICT (tenant_id, fundo_id, silver_origin, identificador)
                DO UPDATE SET cosif_override = EXCLUDED.cosif_override,
                              classe_sr_mez_sub = EXCLUDED.classe_sr_mez_sub
            """), {
                "t": tenant_id, "f": ua_id, "s": silv, "i": ident,
                "c": cosif, "cls": classe,
                "motivo": "Seed inicial REALINVEST (migration ba7032c76c17).",
            })
            print(f"  override: {silv} / {ident} -> {cosif}")
        await db.commit()
        print(f"\n{len(OVERRIDES)} overrides aplicados (idempotente).")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
