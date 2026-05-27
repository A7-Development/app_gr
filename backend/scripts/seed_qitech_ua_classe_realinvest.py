"""Seed do catalogo de classes de cota (qitech_ua_classe) do REALINVEST.

Simula o que o admin do tenant a7-credit confirmaria no onboarding da
integracao QiTech (probe + confirmar classes):

  REALINVEST       -> SUBORDINADA  (REALINVEST FIDC)
  REALINVEST MEZ   -> MEZANINO     (REALINVEST FIDC MEZANINO 1)
  REALINVEST SEN   -> SENIOR       (REALINVEST FIDC SENIOR 1)

A migration `a9f4c2e7b1d8` ja faz esse seed (guardado). Este script existe
para re-seed / outros ambientes / quando a migration ja rodou antes do
tenant/UA existirem. Idempotente — usa ON CONFLICT do UQ.

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/seed_qitech_ua_classe_realinvest.py
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal

_FUNDO_CNPJ = "42449234000160"
# (cliente_id, cliente_nome, papel) — nomes exatos de wh_mec_evolucao_cotas.
CLASSES: list[tuple[str, str, str]] = [
    ("REALINVEST", "REALINVEST FIDC", "SUBORDINADA"),
    ("REALINVEST MEZ", "REALINVEST FIDC MEZANINO 1", "MEZANINO"),
    ("REALINVEST SEN", "REALINVEST FIDC SENIOR 1", "SENIOR"),
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
            print(
                "Tenant ou UA REALINVEST FIDC nao encontrados.", file=sys.stderr
            )
            return 1

        for cliente_id, cliente_nome, papel in CLASSES:
            await db.execute(
                text("""
                    INSERT INTO qitech_ua_classe
                      (tenant_id, unidade_administrativa_id, cliente_id,
                       cliente_nome, fundo_cnpj, papel, ativo_desde)
                    VALUES
                      (:t, :u, :cid, :nome, :cnpj, :papel, DATE '2021-01-01')
                    ON CONFLICT ON CONSTRAINT uq_qitech_ua_classe
                    DO UPDATE SET cliente_nome = EXCLUDED.cliente_nome,
                                  fundo_cnpj = EXCLUDED.fundo_cnpj,
                                  papel = EXCLUDED.papel
                """),
                {
                    "t": tenant_id,
                    "u": ua_id,
                    "cid": cliente_id,
                    "nome": cliente_nome,
                    "cnpj": _FUNDO_CNPJ,
                    "papel": papel,
                },
            )
            print(f"  classe: {cliente_id} -> {papel}")
        await db.commit()
        print(f"\n{len(CLASSES)} classes aplicadas (idempotente).")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
