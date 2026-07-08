"""One-time backfill of wh_bcb_agencia from the BCB historical series.

Source: BigQuery `basedosdados.br_bcb_agencia.agencia` (BCB monthly informes
stacked 2007-2026, public re-host by Base dos Dados). Deduplicated to the
LAST known state of each (banco_compe, agencia) — includes extinct branches.

Extinct agencies never come back, so this runs ONCE (no permanent BQ
dependency). The live Olinda API keeps the current month fresh elsewhere.

Usage (needs a GCP key with BigQuery Job User):
    GOOGLE_APPLICATION_CREDENTIALS=/path/key.json \
    python -m scripts.backfill_bcb_agencia [--gcp-project <id>]

Loads into gr_db for every tenant that has liquidation data (reuses the
tenant of wh_liquidacao). Idempotent: upsert by (tenant_id, source_id).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import UTC, date, datetime

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType
from app.modules.integracoes.adapters.erp.bitfin.etl import _bulk_upsert
from app.warehouse.bcb_agencia import WhBcbAgencia

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_bcb_agencia")

_ADAPTER_VERSION = "bcb_agencia_backfill_v1.0.0"

# Dedup to last state per (cnpj_base, agencia 5d); derive banco COMPE from any
# sibling row of the same cnpj_base that carries it; resolve municipio name
# via the public municipality directory (IBGE 7).
_BQ = """
WITH base AS (
  SELECT
    substr(cnpj, 1, 8) AS cnpj_base,
    lpad(id_compe_bcb_agencia, 5, '0') AS agencia,
    cnpj, endereco, bairro, cep, complemento, id_municipio, sigla_uf,
    nome_agencia, instituicao, data_inicio, ddd, fone, segmento,
    ano * 100 + mes AS comp,
    id_compe_bcb_instituicao
  FROM `basedosdados.br_bcb_agencia.agencia`
  WHERE id_compe_bcb_agencia IS NOT NULL AND cnpj IS NOT NULL
),
banco AS (
  SELECT cnpj_base, MAX(lpad(id_compe_bcb_instituicao, 3, '0')) AS banco_compe
  FROM base WHERE id_compe_bcb_instituicao IS NOT NULL GROUP BY cnpj_base
),
janela AS (
  SELECT cnpj_base, agencia, MIN(comp) AS primeira, MAX(comp) AS ultima
  FROM base GROUP BY cnpj_base, agencia
),
dedup AS (
  SELECT *, ROW_NUMBER() OVER (
    PARTITION BY cnpj_base, agencia ORDER BY comp DESC
  ) AS rn
  FROM base
),
maxcomp AS (SELECT MAX(comp) AS m FROM base)
SELECT
  bk.banco_compe, d.agencia, d.cnpj, d.instituicao, d.nome_agencia,
  d.endereco, d.complemento, d.bairro, d.cep, d.sigla_uf,
  SAFE_CAST(d.id_municipio AS INT64) AS municipio_ibge, mun.nome AS municipio,
  d.ddd, d.fone, d.segmento, d.data_inicio,
  j.primeira, j.ultima, (j.ultima = mc.m) AS ativa
FROM dedup d
JOIN janela j USING (cnpj_base, agencia)
LEFT JOIN banco bk USING (cnpj_base)
LEFT JOIN `basedosdados.br_bd_diretorios_brasil.municipio` mun
  ON mun.id_municipio = d.id_municipio
CROSS JOIN maxcomp mc
WHERE d.rn = 1
"""


def _fetch_bq_rows(gcp_project: str) -> list[dict]:
    from google.cloud import bigquery

    client = bigquery.Client(project=gcp_project)
    logger.info("querying BigQuery basedosdados.br_bcb_agencia.agencia ...")
    rows = [dict(r) for r in client.query(_BQ).result()]
    logger.info("BigQuery returned %d deduplicated agencies", len(rows))
    return rows


def _parse_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


async def _tenant_id() -> str | None:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(text("SELECT DISTINCT tenant_id FROM wh_liquidacao LIMIT 1"))
        ).scalar_one_or_none()


async def run(gcp_project: str) -> None:
    tenant_id = await _tenant_id()
    if tenant_id is None:
        logger.error("nenhum tenant com wh_liquidacao — nada a carregar")
        return

    bq_rows = await asyncio.to_thread(_fetch_bq_rows, gcp_project)

    def _map(r: dict) -> dict:
        cnpj = (r.get("cnpj") or "").strip() or None
        return {
            "tenant_id": tenant_id,
            "banco_compe": (r.get("banco_compe") or "").strip() or None,
            "agencia_codigo": r["agencia"],
            "cnpj": cnpj[:14] if cnpj else None,
            "instituicao": (r.get("instituicao") or None),
            "nome_agencia": (r.get("nome_agencia") or None),
            "endereco": (r.get("endereco") or None),
            "complemento": (r.get("complemento") or None),
            "bairro": (r.get("bairro") or None),
            "cep": (str(r.get("cep")).strip()[:9] if r.get("cep") else None),
            "municipio": (r.get("municipio") or None),
            "municipio_ibge": r.get("municipio_ibge"),
            "uf": (str(r.get("sigla_uf")).strip()[:2] if r.get("sigla_uf") else None),
            "ddd": (str(r.get("ddd")).strip()[:3] if r.get("ddd") else None),
            "fone": (str(r.get("fone")).strip()[:20] if r.get("fone") else None),
            "segmento": (str(r.get("segmento")).strip()[:64] if r.get("segmento") else None),
            "data_inicio": _parse_date(r.get("data_inicio")),
            "primeira_competencia": r.get("primeira"),
            "ultima_competencia": r.get("ultima"),
            "ativa": bool(r.get("ativa")),
            # Auditable: source_id por (banco, agencia, cnpj) — unico e estavel.
            "source_type": SourceType.PUBLIC_BCB_AGENCIA,
            "source_id": f"{r.get('banco_compe') or '?'}:{r['agencia']}:{cnpj or '?'}",
            "source_updated_at": None,
            "ingested_at": datetime.now(UTC),
            "hash_origem": None,
            "ingested_by_version": _ADAPTER_VERSION,
            "trust_level": "high",
            "collected_by": None,
        }

    linhas = [_map(r) for r in bq_rows]
    async with AsyncSessionLocal() as db:
        n = await _bulk_upsert(db, WhBcbAgencia, linhas, ["tenant_id", "source_id"])
        await db.commit()
    logger.info("wh_bcb_agencia: %d agencias carregadas (tenant=%s)", n, tenant_id)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--gcp-project",
        default=os.environ.get("GCP_PROJECT", "agencias-501822"),
        help="Projeto GCP faturador da query BigQuery",
    )
    args = ap.parse_args()
    asyncio.run(run(args.gcp_project))


if __name__ == "__main__":
    main()
