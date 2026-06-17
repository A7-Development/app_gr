"""Captura fixtures reais do BigDataCorp para um CNPJ + lista de datasets.

Uso 3 do BDC (CLAUDE.md / decisao 2026-06-16): "descoberta e fixture". Este
script roda no CAMINHO DE PRODUCAO (resolve credencial BDC ativa em
`provedor_dados_credencial`, decifra o envelope, chama `query_entity` do
adapter) e despeja o envelope cru de cada dataset num arquivo de fixture.
NAO usa o MCP do Claude (aquele e autenticado na sessao claude.ai, morre em
headless) e NAO grava bronze/silver — so captura material pra desenvolver
mappers + semear contratos dos pacotes novos (Quadro Societario, Restritivos).

Cada chamada a `query_entity` e PAGA conforme a faixa do dataset. Rode com
parcimonia — a ideia e capturar 1 CNPJ-cobaia por pacote, nao varrer base.

Exemplo (datasets baratos do Quadro Societario):

    python -m scripts.capture_bdc_fixtures 26239451000170 \
        dynamic_qsa_data,economic_group_first_level,relationships

Saida: backend/tests/modules/integracoes/adapters/data/bigdatacorp/fixtures/
       <dataset>.<cnpj>.json   (envelope {_meta, payload})
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.data.bigdatacorp.client import query_entity
from app.modules.integracoes.adapters.data.bigdatacorp.config import (
    BigDataCorpConfig,
)
from app.modules.integracoes.adapters.data.bigdatacorp.version import (
    ADAPTER_VERSION,
)
from app.shared.crypto.envelope import decrypt_envelope
from app.shared.data_providers.enums import DataProviderSlug
from app.shared.data_providers.models.credential import DataProviderCredential
from app.shared.data_providers.models.provider import DataProvider

_FIXTURE_DIR = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "modules"
    / "integracoes"
    / "adapters"
    / "data"
    / "bigdatacorp"
    / "fixtures"
)


async def _resolve_bdc() -> tuple[str, BigDataCorpConfig]:
    """Devolve (base_url, config decifrada) do provider BDC ativo."""
    async with AsyncSessionLocal() as db:
        provider = (
            await db.execute(
                select(DataProvider).where(
                    DataProvider.slug == DataProviderSlug.BIGDATACORP
                )
            )
        ).scalar_one_or_none()
        if provider is None:
            raise SystemExit("provedor_dados BigDataCorp nao cadastrado")
        if not provider.enabled:
            raise SystemExit("provider BigDataCorp esta desligado (enabled=false)")

        credential = (
            await db.execute(
                select(DataProviderCredential)
                .where(DataProviderCredential.provider_id == provider.id)
                .where(DataProviderCredential.active.is_(True))
                .order_by(DataProviderCredential.updated_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if credential is None:
            raise SystemExit("BigDataCorp sem credencial ativa")

        config = BigDataCorpConfig.from_dict(decrypt_envelope(credential.encrypted_payload))
        return provider.base_url, config


async def _capture(cnpj: str, datasets: list[str]) -> None:
    digits = "".join(ch for ch in cnpj if ch.isdigit())
    base_url, config = await _resolve_bdc()
    _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    for dataset in datasets:
        result = await query_entity(
            config=config, base_url=base_url, doc=digits, datasets=dataset, limit=1
        )
        found = bool(result.payload.get("Result") or [])
        out = _FIXTURE_DIR / f"{dataset}.{digits}.json"
        out.write_text(
            json.dumps(
                {
                    "_meta": {
                        "cnpj": digits,
                        "dataset": dataset,
                        "provider_api": "Companies",
                        "adapter_version": ADAPTER_VERSION,
                        "status_code": result.status_code,
                        "latency_ms": result.latency_ms,
                        "found": found,
                        "captured_at": datetime.now(UTC).isoformat(),
                        "source": "capture_bdc_fixtures (prod path)",
                    },
                    "payload": result.payload,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(f"  {dataset:<32} found={found!s:<5} -> {out.name}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "uso: python -m scripts.capture_bdc_fixtures <cnpj> "
            "<dataset1,dataset2,...>"
        )
    cnpj = sys.argv[1]
    datasets = [d.strip() for d in sys.argv[2].split(",") if d.strip()]
    print(f"Capturando {len(datasets)} dataset(s) para CNPJ {cnpj}...")
    asyncio.run(_capture(cnpj, datasets))
    print("OK.")


if __name__ == "__main__":
    main()
