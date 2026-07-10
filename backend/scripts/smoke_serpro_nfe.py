"""Smoke da API SERPRO Consulta NF-e.

Dois modos:

TRIAL (default — mock publico do SERPRO, custo ZERO):
    .venv\\Scripts\\python.exe scripts/smoke_serpro_nfe.py

    Consulta chaves ficticias documentadas (casos: autorizada, com eventos,
    cancelada, cStat 150, denegada 302) contra consulta-nfe-df-trial com o
    bearer publico de demonstracao.

PRODUCAO (consome credito do contrato — so rodar com aval):
    .venv\\Scripts\\python.exe scripts/smoke_serpro_nfe.py \\
        --prod --chave <44 digitos> [--chave ...]

    Le a credencial de `tenant_source_config` (DATA_SERPRO_NFE / a7-credit /
    production) — exige o registro previo via register_serpro_source_config.py.
    Cada 200 e cobrado. Nao persiste nada (bronze chega na F1) — o payload
    integral e salvo em scripts/_out/serpro_nfe_<chave>.json pra analise.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from app.modules.integracoes.adapters.data.serpro.client import (
    SerproClient,
    SerproNfeResponse,
)
from app.modules.integracoes.adapters.data.serpro.config import (
    TRIAL_BASE_URL,
    TRIAL_BEARER_TOKEN,
    SerproConfig,
)
from app.modules.integracoes.adapters.data.serpro.errors import SerproError

A7_CREDIT_TENANT_ID = UUID("7f00cc2b-8bb4-483f-87b7-b1db24d20902")

# Chaves ficticias do ambiente de demonstracao (doc quick_start do SERPRO).
TRIAL_KEYS = [
    "53131205035672000156550010000004991543410167",
    # NF-e com evento de cancelamento
    "35220241522703000167550010000001211000225472",
    # NF-e autorizada fora do prazo (cStat 150)
    "22210841816302000110550000000000012824578529",
    # NF-e com uso denegado (cStat 302)
    "41220211436073000147550010013215511002385213",
    # NF-e comum autorizada
    "35170608530528000184550000000154301000771561",
]

_OUT_DIR = Path(__file__).parent / "_out"


def _describe(resp: SerproNfeResponse) -> None:
    prot = resp.prot_nfe
    print(
        f"  cStat={resp.cstat} xMotivo={prot.get('xMotivo')!r} "
        f"nProt={prot.get('nProt')} latency={resp.latency_ms}ms"
    )
    eventos = resp.eventos
    print(f"  eventos: {len(eventos)}")
    for ev in eventos:
        inf = (ev.get("evento") or {}).get("infEvento") or {}
        print(
            f"    - tpEvento={inf.get('tpEvento')} dhEvento={inf.get('dhEvento')}"
        )


async def _run(chaves: list[str], config: SerproConfig, *, static_token: str | None) -> int:
    failures = 0
    _OUT_DIR.mkdir(exist_ok=True)
    async with SerproClient(config=config, static_token=static_token) as client:
        for i, chave in enumerate(chaves):
            if i:
                # Trial tem throttling agressivo (429 em burst de ~4).
                await asyncio.sleep(2.0)
            print(f"\n[{chave}]")
            try:
                resp = await client.consulta_nfe(chave, request_tag="smoke")
            except SerproError as e:
                print(f"  ERRO {type(e).__name__}: {e}")
                failures += 1
                continue
            _describe(resp)
            out = _OUT_DIR / f"serpro_nfe_{chave}.json"
            out.write_text(
                json.dumps(resp.raw, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            print(f"  payload salvo em {out}")
    return failures


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prod",
        action="store_true",
        help="usa a credencial real de tenant_source_config (CONSOME CREDITO)",
    )
    parser.add_argument(
        "--chave",
        action="append",
        default=None,
        help="chave de acesso (repetivel); default = chaves do trial",
    )
    args = parser.parse_args()

    if args.prod:
        # Import tardio: o modo trial nao exige .env/DB configurados.
        from app.core.database import AsyncSessionLocal
        from app.core.enums import Environment, SourceType
        from app.modules.integracoes.services.source_config import (
            get_decrypted_config,
        )

        if not args.chave:
            print("[ERRO] --prod exige ao menos um --chave (cada 200 custa).")
            return 1
        async with AsyncSessionLocal() as db:
            plain = await get_decrypted_config(
                db,
                A7_CREDIT_TENANT_ID,
                SourceType.DATA_SERPRO_NFE,
                Environment.PRODUCTION,
            )
        if plain is None:
            print(
                "[ERRO] sem config DATA_SERPRO_NFE para a7-credit/production — "
                "rode register_serpro_source_config.py antes."
            )
            return 1
        config = SerproConfig.from_dict(plain)
        static_token = None
        print(f"[smoke PROD] base={config.base_url}")
    else:
        config = SerproConfig(
            consumer_key="trial",
            consumer_secret="trial",
            base_url=TRIAL_BASE_URL,
        )
        static_token = TRIAL_BEARER_TOKEN
        print(f"[smoke TRIAL] base={config.base_url} (custo zero)")

    chaves = args.chave or TRIAL_KEYS
    failures = await _run(chaves, config, static_token=static_token)
    print(f"\n{len(chaves) - failures}/{len(chaves)} consultas OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
