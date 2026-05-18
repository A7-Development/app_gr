"""Debug script — quebra Apropriacao DC nos componentes brutos pra
encontrar o overflow de R$ 92 MI em REALINVEST 06/05/2026.

Chama os helpers `_estoque_a_vencer/_vencidos`, `_aquisicoes`, `_liquidados`
direto, mostrando os 8 numeros que entram em `_apropriacao_dc` + recalcula
o `apropriacao` total no formato planilha.

Uso:
    DATABASE_URL=... python scripts/debug_apropriacao_dc.py 2026-05-06
    DATABASE_URL=... python scripts/debug_apropriacao_dc.py 2026-05-06 2026-05-13
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.cadastros.models.unidade_administrativa import UnidadeAdministrativa
from app.modules.controladoria.services.cota_sub import (
    _aquisicoes,
    _estoque_a_vencer,
    _estoque_vencidos,
    _liquidados,
)


REALINVEST_NAME = "REALINVEST FIDC"
REALINVEST_DOC = "42449234000160"


async def _diag(db: AsyncSession, tenant_id, ua_id, d0: date) -> None:
    d_prev = d0 - timedelta(days=1)

    print(f"\n==== {d_prev} -> {d0} ====")
    av_d1 = await _estoque_a_vencer(db, tenant_id, REALINVEST_DOC, d_prev)
    av_d0 = await _estoque_a_vencer(db, tenant_id, REALINVEST_DOC, d0)
    ve_d1 = await _estoque_vencidos(db, tenant_id, REALINVEST_DOC, d_prev)
    ve_d0 = await _estoque_vencidos(db, tenant_id, REALINVEST_DOC, d0)
    av_aq = await _aquisicoes(db, tenant_id, ua_id, d_prev, d0, a_vencer_ref_data=d0)
    ve_aq = await _aquisicoes(db, tenant_id, ua_id, d_prev, d0, a_vencer_ref_data=None)
    av_li = await _liquidados(db, tenant_id, ua_id, d_prev, d0, apenas_vencidos=False)
    ve_li = await _liquidados(db, tenant_id, ua_id, d_prev, d0, apenas_vencidos=True)

    av_apr = av_d0 - (av_d1 + av_aq + av_li)
    ve_apr = ve_d0 - (ve_d1 + ve_aq + ve_li)
    total = av_apr + ve_apr

    print(f"  A VENCER")
    print(f"    estoque_d_prev:  R$ {float(av_d1):>16,.2f}")
    print(f"    estoque_d0:      R$ {float(av_d0):>16,.2f}")
    print(f"    aquisicoes:      R$ {float(av_aq):>16,.2f}")
    print(f"    liquidados:      R$ {float(av_li):>16,.2f}  (sinal: ja negado)")
    print(f"    -> apropriacao:  R$ {float(av_apr):>16,.2f}")
    print(f"  VENCIDOS")
    print(f"    estoque_d_prev:  R$ {float(ve_d1):>16,.2f}")
    print(f"    estoque_d0:      R$ {float(ve_d0):>16,.2f}")
    print(f"    aquisicoes:      R$ {float(ve_aq):>16,.2f}")
    print(f"    liquidados:      R$ {float(ve_li):>16,.2f}")
    print(f"    -> apropriacao:  R$ {float(ve_apr):>16,.2f}")
    print(f"  TOTAL:             R$ {float(total):>16,.2f}")


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL nao setada")

    args = sys.argv[1:] or ["2026-05-06"]
    dates = [date.fromisoformat(a) for a in args]

    engine = create_async_engine(db_url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as db:
        ua = (
            await db.execute(
                select(UnidadeAdministrativa).where(
                    UnidadeAdministrativa.nome == REALINVEST_NAME
                )
            )
        ).scalar_one_or_none()
        if not ua:
            raise SystemExit(f"UA {REALINVEST_NAME!r} nao encontrada")
        print(f"Tenant={ua.tenant_id} UA={ua.id} ({REALINVEST_NAME}, doc={REALINVEST_DOC})")

        for d0 in dates:
            await _diag(db, ua.tenant_id, ua.id, d0)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
