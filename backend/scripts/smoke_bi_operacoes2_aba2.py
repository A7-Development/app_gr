"""Smoke do BI Operacoes2 Aba 2 (Produtos & Pricing).

Espelha o filtro padrao do frontend (preset=12m) e imprime contagens + amostras
de cada bloco do bundle. Usado para validar que o service pega dados de hoje
e que filtros globais (regra dura sec7.2) sao aplicados em todas as queries.

Uso:
    .venv\\Scripts\\python.exe scripts/smoke_bi_operacoes2_aba2.py
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401
import app.warehouse  # noqa: F401

from app.core.database import AsyncSessionLocal
from app.modules.bi.services.operacoes2 import get_aba2_produtos_pricing


TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")  # a7-credit
PRODUTO_DEFAULT = ["FAT", "CMS", "DMS", "NOT", "INT", "FOM", "CCB"]


def _twelve_m_window(today: date) -> tuple[date, date]:
    base = today.replace(day=1) - timedelta(days=1)
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
        data, prov = await get_aba2_produtos_pricing(db, TENANT_ID, filters)

    # -- Linha 1 ------------------------------------------------------------
    print("---L1 — Mix temporal 12M (closed window) ---------------")
    print(f"  pontos: {len(data.mix_temporal_12m)}")
    if data.mix_temporal_12m:
        amostra = data.mix_temporal_12m[:3]
        for p in amostra:
            print(
                f"    {p.periodo} | {p.produto_sigla:<4} | "
                f"VOP R$ {p.vop:>15,.2f} | n_ops={p.n_operacoes} | "
                f"taxa={p.taxa_media:.2f}% | prazo={p.prazo_medio:.1f}d"
            )
    print(f"  lider_periodo:    {data.lider_periodo}")
    print(f"  maior_alta_mom:   {data.maior_alta_mom}")
    print(f"  maior_queda_mom:  {data.maior_queda_mom}")
    print()

    # -- Linha 2 ------------------------------------------------------------
    print("---L2 — Ranking + Scatter agregado ----------------------")
    print(f"  ranking: {len(data.ranking)} produtos")
    for r in data.ranking[:5]:
        delta = (
            f"{r.delta_mom_pp:+.2f}pp" if r.delta_mom_pp is not None else "  n/a"
        )
        print(
            f"    #{r.sigla:<4} {r.nome or '?':<14} | "
            f"VOP R$ {r.vop:>15,.2f} ({r.pct:>5.1f}%) D{delta} | "
            f"taxa={r.taxa_media:>5.2f}% prazo={r.prazo_medio:>5.1f}d "
            f"spread={r.spread_medio:>5.2f}pp n={r.n_operacoes:>4}"
        )
        print(
            f"      MTD mes: VOP R$ {r.vop_mes_corrente:>15,.2f} | "
            f"taxa={r.taxa_media_mes_corrente:.2f}%"
        )
    print(f"  scatter: {len(data.scatter_produtos)} pontos")
    for s in data.scatter_produtos[:3]:
        print(
            f"    {s.sigla:<4} period: ({s.prazo_medio:.1f}d, {s.taxa_media:.2f}%) "
            f"vop=R$ {s.vop:,.0f} | mes: ({s.prazo_medio_mes_corrente:.1f}d, "
            f"{s.taxa_media_mes_corrente:.2f}%) vop=R$ {s.vop_mes_corrente:,.0f}"
        )
    print()

    # -- Linha 3 ------------------------------------------------------------
    print("---L3 — Histogramas --------------------------------------")
    ht = data.histograma_taxas
    print(f"  histograma_taxas: {len(ht.buckets)} buckets (size={ht.bucket_size_pp}pp)")
    print(f"    media_ponderada={ht.media_ponderada:.3f}%  mediana_aprox={ht.mediana:.3f}%")
    for b in ht.buckets[:4]:
        print(
            f"    {b.produto_sigla:<4} {b.bucket_label:<14} "
            f"n={b.count:>4} VOP R$ {b.vop:,.0f}"
        )
    hp = data.histograma_prazos
    print(f"  histograma_prazos: {len(hp.buckets)} buckets")
    for b in hp.buckets[:5]:
        print(
            f"    {b.produto_sigla:<4} {b.bucket_label:<10} "
            f"n={b.count:>4} VOP R$ {b.vop:,.0f}"
        )
    print()

    # -- Provenance ---------------------------------------------------------
    print("---Provenance --------------------------------------------")
    print(f"  last_source_updated_at = {prov.last_source_updated_at}")
    print(f"  last_sync_at           = {prov.last_sync_at}")
    print(f"  row_count              = {prov.row_count}")


if __name__ == "__main__":
    asyncio.run(main())
