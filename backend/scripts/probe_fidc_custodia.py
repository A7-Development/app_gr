"""Probe dos 4 endpoints `/fidc-custodia/report/*` da QiTech.

Objetivo: descobrir schema concreto (JSON? CSV?), volumes, semantica de
periodo vs snapshot — pra calibrar adapter antes de codar mappers/canonicos.

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/probe_fidc_custodia.py \\
        --cnpj 42449234000160 --inicio 2026-01-01 --fim 2026-01-08
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401  (registry)
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
)

A7 = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")
SAMPLES_ROOT = Path(__file__).resolve().parent.parent / "qitech_samples"


def _save_response(
    *, tenant: str, sample_dir: str, name: str, body: bytes | str | dict
) -> Path:
    """Salva a resposta crua em qitech_samples/<tenant>/<sample_dir>/<name>."""
    out_dir = SAMPLES_ROOT / tenant / sample_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(body, dict | list):
        path = out_dir / f"{name}.json"
        path.write_text(
            json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    elif isinstance(body, bytes):
        # heuristica: se parece CSV, salva .csv; senao .bin
        ext = "csv" if b";" in body[:200] or b"," in body[:200] else "bin"
        path = out_dir / f"{name}.{ext}"
        path.write_bytes(body)
    else:
        path = out_dir / f"{name}.txt"
        path.write_text(body, encoding="utf-8")
    return path


async def main(cnpj: str, dt_inicio: str, dt_fim: str) -> int:
    async with AsyncSessionLocal() as db:
        cfg_row = await get_config(
            db, A7, SourceType.ADMIN_QITECH, Environment.PRODUCTION
        )
        if cfg_row is None:
            print("[ERRO] sem config qitech a7-credit")
            return 1
        plain = decrypt_config(cfg_row.config)

    config = QiTechConfig.from_dict(plain)
    print(f"[probe] base_url={config.base_url}")
    print(f"[probe] cnpj={cnpj} periodo={dt_inicio}..{dt_fim}")
    print()

    sample_dir = f"fidc-custodia-{dt_inicio}-{dt_fim}"

    endpoints = [
        (
            "aquisicao-consolidada",
            f"/v2/fidc-custodia/report/aquisicao-consolidada/{cnpj}/{dt_inicio}/{dt_fim}",
        ),
        (
            "liquidados-baixados-v2",
            f"/v2/fidc-custodia/report/liquidados-baixados/v2/{cnpj}/{dt_inicio}/{dt_fim}",
        ),
        (
            "movimento-aberto",
            f"/v2/fidc-custodia/report/movimento-aberto/{cnpj}/",
        ),
        (
            "detalhes-operacoes",
            f"/v2report/fundo/{cnpj}/data/{dt_inicio}",
        ),
    ]

    async with build_async_client(
        tenant_id=A7, environment=Environment.PRODUCTION, config=config
    ) as client:
        for name, path in endpoints:
            print("=" * 70)
            print(f"[{name}]")
            print(f"GET {path}")
            print("=" * 70)
            try:
                resp = await client.get(path)
                ct = resp.headers.get("content-type", "")
                print(f"status={resp.status_code}  content-type={ct}")
                print(f"size={len(resp.content)} bytes")
                # Imprime primeiras linhas e salva
                if "json" in ct.lower():
                    try:
                        body = resp.json()
                        snippet = json.dumps(body, indent=2, ensure_ascii=False)
                        print("preview (primeiros 800 chars):")
                        print(snippet[:800])
                        saved = _save_response(
                            tenant="a7-credit",
                            sample_dir=sample_dir,
                            name=name,
                            body=body,
                        )
                        print(f"saved: {saved}")
                    except ValueError:
                        print(f"response (texto): {resp.text[:500]}")
                else:
                    text = resp.text
                    print("preview (primeiras 5 linhas):")
                    print("\n".join(text.split("\n")[:5]))
                    saved = _save_response(
                        tenant="a7-credit",
                        sample_dir=sample_dir,
                        name=name,
                        body=resp.content,
                    )
                    print(f"saved: {saved}")
            except Exception as e:
                print(f"erro: {type(e).__name__}: {e}")
            print()

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cnpj", default="42449234000160")
    parser.add_argument("--inicio", default="2026-01-01")
    parser.add_argument("--fim", default="2026-01-08")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.cnpj, args.inicio, args.fim)))
