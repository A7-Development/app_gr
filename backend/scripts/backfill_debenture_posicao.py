"""Backfill da posicao de debentures: Bitfin -> bronze + silver diario.

Le `PosicaoHistoricaDebenture` (fechamento MENSAL oficial, ja CDI+spread) do
UNLTD_<X>, grava bronze `wh_bitfin_raw_debenture` (tipo_origem=posicao_mensal,
1 row por competencia) e constroi o silver `wh_posicao_debenture_dia` por
**interpolacao geometrica** entre ancoras mensais consecutivas (a serie e
CDI+spread, curva intra-mes suave -> erro na MEDIA mensal negligivel).

Por que interpolar e nao recomputar CDI: a Bitfin ja faz a conta dela no
fechamento mensal; ancoramos no numero oficial dela. O snapshot diario
going-forward (tipo_origem=valor_atualizado_dia) e responsabilidade de um job
separado -- aqui cobrimos o historico que so existe em granularidade mensal.

Uso:
    python -m scripts.backfill_debenture_posicao              # tenant a7-credit
    python -m scripts.backfill_debenture_posicao --tenant a7-credit
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from calendar import monthrange
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from uuid import UUID

from sqlalchemy import select, text

import app.shared.identity.tenant  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import fetch_rows
from app.modules.integracoes.services.source_config import get_decrypted_config
from app.shared.identity.tenant import Tenant

ADAPTER_VERSION = "debenture_posicao_v1.0.0"

# Posicao mensal oficial por subscricao, com a UA dona da escritura. 1 linha por
# (subscricao, Ano, Mes). Agregamos por (ua, competencia) p/ a ancora.
SQL_POSICAO_MENSAL = """
SELECT p.SubscricaoId       AS subscricao_id,
       esc.UnidadeAdministrativaId AS ua_id,
       p.Ano                AS ano,
       p.Mes                AS mes,
       p.QuantidadeDeDebentures AS quantidade,
       p.Valor              AS valor,
       p.TotalBruto         AS total_bruto,
       p.TotalLiquido       AS total_liquido
FROM dbo.PosicaoHistoricaDebenture p
JOIN dbo.DebentureSubscricao s ON s.SubscricaoId = p.SubscricaoId
JOIN dbo.DebentureSerie se     ON se.SerieId = s.SerieId
JOIN dbo.DebentureEscritura esc ON esc.EscrituraId = se.EscrituraId
ORDER BY esc.UnidadeAdministrativaId, p.Ano, p.Mes, p.SubscricaoId
"""


def _d(v: object) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal("0")


def _last_day_of_month(ano: int, mes: int) -> date:
    return date(ano, mes, monthrange(ano, mes)[1])


async def _resolve_tenant_id(slug: str) -> UUID:
    async with AsyncSessionLocal() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        if tenant is None:
            raise SystemExit(f"Tenant '{slug}' nao encontrado.")
        return tenant.id


async def _load_config(tenant_id: UUID) -> BitfinConfig:
    async with AsyncSessionLocal() as db:
        cfg_dict = await get_decrypted_config(db, tenant_id, SourceType.ERP_BITFIN)
    if cfg_dict is None:
        raise SystemExit(f"Tenant {tenant_id} sem tenant_source_config erp:bitfin.")
    return BitfinConfig.from_dict(cfg_dict)


async def _write_bronze(
    db, tenant_id: UUID, by_competencia: dict[date, list[dict]], fetched_at: datetime
) -> int:
    """1 row de bronze por competencia (payload = array de subscricoes)."""
    n = 0
    for competencia, subs in sorted(by_competencia.items()):
        # Decimals -> str para serializar/hashear de forma estavel.
        payload = json.loads(json.dumps(subs, default=str, sort_keys=True))
        sha = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        await db.execute(
            text(
                """
                INSERT INTO wh_bitfin_raw_debenture
                    (id, tenant_id, tipo_origem, data_referencia, payload,
                     row_count, payload_sha256, fetched_at, fetched_by_version)
                VALUES
                    (gen_random_uuid(), :t, 'posicao_mensal', :d, CAST(:p AS jsonb),
                     :rc, :sha, :fa, :ver)
                ON CONFLICT (tenant_id, tipo_origem, data_referencia, payload_sha256)
                DO NOTHING
                """
            ),
            {
                "t": str(tenant_id),
                "d": competencia,
                "p": json.dumps(payload, ensure_ascii=False),
                "rc": len(subs),
                "sha": sha,
                "fa": fetched_at,
                "ver": ADAPTER_VERSION,
            },
        )
        n += 1
    return n


def _build_daily_series(
    anchors: dict[int, list[tuple[date, dict]]],
) -> list[dict]:
    """Interpola diariamente entre ancoras mensais por UA.

    `anchors[ua]` = lista ordenada de (anchor_date, agregado). Retorna rows do
    silver (1 por ua/dia) com origem ancora_mensal|interpolado.
    """
    rows: list[dict] = []
    for ua_id, seq in anchors.items():
        seq = sorted(seq, key=lambda x: x[0])
        # Primeira ancora: o proprio dia, exato.
        d0, a0 = seq[0]
        rows.append(_silver_row(ua_id, d0, a0, "ancora_mensal"))
        for (da, aa), (dbnd, ab) in pairwise(seq):
            span = (dbnd - da).days
            if span <= 0:
                continue
            va_bruto, vb_bruto = _d(aa["bruto"]), _d(ab["bruto"])
            va_valor, vb_valor = _d(aa["valor"]), _d(ab["valor"])
            va_liq, vb_liq = _d(aa["liquido"]), _d(ab["liquido"])
            d = da + timedelta(days=1)
            while d <= dbnd:
                if d == dbnd:
                    rows.append(_silver_row(ua_id, d, ab, "ancora_mensal"))
                else:
                    frac = Decimal((d - da).days) / Decimal(span)
                    rows.append(
                        {
                            "ua_id": ua_id,
                            "data": d,
                            "bruto": _geo(va_bruto, vb_bruto, frac),
                            "valor": _geo(va_valor, vb_valor, frac),
                            "liquido": _geo(va_liq, vb_liq, frac),
                            # qtd / n_subs sao stepwise -> carrega a ancora alvo.
                            "qtd": _d(ab["qtd"]),
                            "n_subs": ab["n_subs"],
                            "origem": "interpolado",
                        }
                    )
                d += timedelta(days=1)
    return rows


def _geo(va: Decimal, vb: Decimal, frac: Decimal) -> Decimal:
    """Interpolacao geometrica va*(vb/va)^frac. Fallback linear se va<=0."""
    if va <= 0 or vb <= 0:
        return (va + (vb - va) * frac).quantize(Decimal("0.01"))
    ratio = float(vb) / float(va)
    val = float(va) * (ratio ** float(frac))
    return Decimal(str(val)).quantize(Decimal("0.01"))


def _silver_row(ua_id: int, d: date, agg: dict, origem: str) -> dict:
    return {
        "ua_id": ua_id,
        "data": d,
        "bruto": _d(agg["bruto"]).quantize(Decimal("0.01")),
        "valor": _d(agg["valor"]).quantize(Decimal("0.01")),
        "liquido": _d(agg["liquido"]).quantize(Decimal("0.01")),
        "qtd": _d(agg["qtd"]),
        "n_subs": agg["n_subs"],
        "origem": origem,
    }


async def _upsert_silver(db, tenant_id: UUID, rows: list[dict]) -> int:
    for r in rows:
        source_id = f"{r['ua_id']}|{r['data'].isoformat()}"
        hash_origem = hashlib.sha256(
            f"{source_id}|{r['bruto']}|{r['origem']}".encode()
        ).hexdigest()
        await db.execute(
            text(
                """
                INSERT INTO wh_posicao_debenture_dia
                    (id, tenant_id, unidade_administrativa_id, data_posicao,
                     pl_bruto, pl_valor, pl_liquido, quantidade_debentures,
                     n_subscricoes, origem,
                     source_type, source_id, ingested_by_version, trust_level)
                VALUES
                    (gen_random_uuid(), :t, :ua, :d,
                     :bruto, :valor, :liquido, :qtd, :nsubs, :origem,
                     'ERP_BITFIN', :sid, :ver, 'HIGH')
                ON CONFLICT (tenant_id, unidade_administrativa_id, data_posicao)
                DO UPDATE SET
                    pl_bruto = EXCLUDED.pl_bruto,
                    pl_valor = EXCLUDED.pl_valor,
                    pl_liquido = EXCLUDED.pl_liquido,
                    quantidade_debentures = EXCLUDED.quantidade_debentures,
                    n_subscricoes = EXCLUDED.n_subscricoes,
                    origem = EXCLUDED.origem,
                    hash_origem = EXCLUDED.hash_origem,
                    ingested_at = now()
                """
            ),
            {
                "t": str(tenant_id),
                "ua": r["ua_id"],
                "d": r["data"],
                "bruto": r["bruto"],
                "valor": r["valor"],
                "liquido": r["liquido"],
                "qtd": r["qtd"],
                "nsubs": r["n_subs"],
                "origem": r["origem"],
                "sid": source_id,
                "ver": ADAPTER_VERSION,
            },
        )
        # hash_origem nao tem placeholder no INSERT acima -> seta no UPDATE via
        # segundo statement leve (mantem o INSERT simples).
        await db.execute(
            text(
                "UPDATE wh_posicao_debenture_dia SET hash_origem = :h "
                "WHERE tenant_id = :t AND unidade_administrativa_id = :ua "
                "AND data_posicao = :d"
            ),
            {"h": hash_origem, "t": str(tenant_id), "ua": r["ua_id"], "d": r["data"]},
        )
    return len(rows)


async def _main(tenant_slug: str) -> None:
    tenant_id = await _resolve_tenant_id(tenant_slug)
    config = await _load_config(tenant_id)
    print(f"[debenture] tenant={tenant_slug} ({tenant_id}) db={config.database_bitfin}")

    raw = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, SQL_POSICAO_MENSAL
    )
    print(f"[debenture] {len(raw)} linhas mensais (subscricao x competencia)")
    if not raw:
        raise SystemExit("Nenhuma posicao mensal retornada pelo Bitfin.")

    # Agrupa para bronze (por competencia) e ancoras (por ua x competencia).
    by_competencia: dict[date, list[dict]] = defaultdict(list)
    anchor_acc: dict[tuple[int, date], dict] = {}
    for row in raw:
        ano, mes = int(row["ano"]), int(row["mes"])
        competencia = date(ano, mes, 1)
        anchor_date = _last_day_of_month(ano, mes)
        by_competencia[competencia].append(row)
        key = (int(row["ua_id"]), anchor_date)
        acc = anchor_acc.setdefault(
            key,
            {"bruto": Decimal("0"), "valor": Decimal("0"), "liquido": Decimal("0"),
             "qtd": Decimal("0"), "n_subs": 0},
        )
        acc["bruto"] += _d(row["total_bruto"])
        acc["valor"] += _d(row["valor"])
        acc["liquido"] += _d(row["total_liquido"])
        acc["qtd"] += _d(row["quantidade"])
        acc["n_subs"] += 1

    anchors: dict[int, list[tuple[date, dict]]] = defaultdict(list)
    for (ua_id, anchor_date), acc in anchor_acc.items():
        anchors[ua_id].append((anchor_date, acc))

    daily = _build_daily_series(anchors)

    fetched_at = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        n_bronze = await _write_bronze(db, tenant_id, by_competencia, fetched_at)
        n_silver = await _upsert_silver(db, tenant_id, daily)
        await db.commit()

    print(f"[debenture] bronze competencias={n_bronze} silver dias={n_silver}")
    for ua_id, seq in sorted(anchors.items()):
        seq = sorted(seq, key=lambda x: x[0])
        rng = f"{seq[0][0]} -> {seq[-1][0]}"
        print(
            f"  UA {ua_id}: {len(seq)} ancoras ({rng}), "
            f"ultima PL_bruto={seq[-1][1]['bruto']:.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill posicao de debentures")
    parser.add_argument("--tenant", default="a7-credit")
    args = parser.parse_args()
    asyncio.run(_main(args.tenant))


if __name__ == "__main__":
    main()
