"""Smoke do BI Operacoes2 KPI Strip — confirma se o service pega ops de hoje.

Reproduz o que o frontend envia em preset=12m default:
  - periodo_inicio = primeiro dia do mes 12 meses atras
  - periodo_fim    = hoje
  - produto_sigla  = ['FAT','CMS','DMS','NOT','INT','FOM','CCB']

Imprime:
  - vop_periodo, vop_mes_corrente, mes_corrente_label
  - last_source_updated_at e last_sync_at do provenance

Util pra distinguir bug-de-backend (service nao pega hoje) de bug-de-cache
(client mostra valor antigo apesar do backend estar correto).

Uso:
    .venv\\Scripts\\python.exe scripts/smoke_bi_operacoes2_kpi.py
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401
import app.warehouse  # noqa: F401

from app.core.database import AsyncSessionLocal
from app.modules.bi.services.operacoes2 import get_kpi_strip


TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")  # a7-credit
PRODUTO_DEFAULT = ["FAT", "CMS", "DMS", "NOT", "INT", "FOM", "CCB"]


def _twelve_m_window(today: date) -> tuple[date, date]:
    # Espelha computePresetRange do frontend para preset=12m:
    # start = primeiro dia do mes (today - 12 meses)
    base = (today.replace(day=1) - timedelta(days=1))
    base = base.replace(day=1)
    for _ in range(11):
        base = (base - timedelta(days=1)).replace(day=1)
    return base, today


async def main() -> None:
    today = date.today()
    inicio, fim = _twelve_m_window(today)
    filters = {
        "periodo_inicio": inicio,
        "periodo_fim": fim,
        "produto_sigla": PRODUTO_DEFAULT,
        "ua_id": None,
        "cedente_id": None,
        "sacado_id": None,
        "gerente_documento": None,
    }

    print(f"hoje                 = {today}")
    print(f"periodo_inicio       = {inicio}")
    print(f"periodo_fim          = {fim}")
    print(f"produto_sigla        = {PRODUTO_DEFAULT}")
    print()

    async with AsyncSessionLocal() as db:
        data, prov = await get_kpi_strip(db, TENANT_ID, filters)

    vop = data.vop
    print(f"VOP periodo          = R$ {float(vop.valor):>20,.2f}")
    print(f"VOP mes corrente     = R$ {float(vop.mes_corrente_valor):>20,.2f}")
    print(f"mes_corrente_label   = {vop.mes_corrente_label}")
    print(f"delta_pct (MoM)      = {vop.delta_pct}")
    print()
    print(f"prov.last_source_updated_at = {prov.last_source_updated_at}")
    print(f"prov.last_sync_at           = {prov.last_sync_at}")
    print(f"prov.row_count              = {prov.row_count}")


if __name__ == "__main__":
    asyncio.run(main())
