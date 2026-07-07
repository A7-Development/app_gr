"""Seed/atualiza o `tenant_source_config` da INBOX de cobranca (CNAB).

A pasta de retornos tem arquivos de varios bancos misturados; o banco se
descobre lendo o header de cada arquivo (nao a config). Por isso ha UMA fonte
generica `cobranca` (source_type COBRANCA) apontando o FileSource para a
pasta. O `config` e cifrado (envelope Fernet) via `upsert_config`. Re-rodar
atualiza a linha (idempotente por tenant+ambiente+UA).

Uso:
    uv run python scripts/seed_cobranca_source.py \
        --tenant a7-credit \
        --path "/mnt/bitfin-arquivos/Banco/Cobranca/Retorno/Processado" \
        --remessa-path "/mnt/bitfin-arquivos/Banco/Cobranca/Remessa/Enviado" \
        --glob "*"

`--remessa-path` (opcional) liga a coleta de remessa junto da de retorno (a
inbox vira multi-root). Para upload manual: `--mode upload --staging-path <dir>`.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.services.source_config import upsert_config
from app.shared.identity.tenant import Tenant
from app.warehouse.cnab_raw_arquivo import (
    FILE_SOURCE_LANDING,
    FILE_SOURCE_LOCAL_PATH,
    FILE_SOURCE_UPLOAD,
)


async def _resolve_tenant_id(db, slug: str):
    tenant = (
        await db.execute(select(Tenant).where(Tenant.slug == slug))
    ).scalar_one_or_none()
    if tenant is None:
        raise SystemExit(f"Tenant com slug {slug!r} nao encontrado.")
    return tenant.id


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant", required=True, help="slug do tenant (ex.: a7-credit)")
    ap.add_argument(
        "--mode",
        default=FILE_SOURCE_LOCAL_PATH,
        choices=[FILE_SOURCE_LOCAL_PATH, FILE_SOURCE_UPLOAD, FILE_SOURCE_LANDING],
    )
    ap.add_argument("--path", help="diretorio de RETORNO (mode local_path)")
    ap.add_argument(
        "--remessa-path",
        help="diretorio de REMESSA (mode local_path). Quando dado, a inbox vira "
        "multi-root [retorno, remessa] e o sync coleta os dois.",
    )
    ap.add_argument("--staging-path", help="diretorio de upload (mode upload)")
    ap.add_argument(
        "--source-labels",
        default="cobranca_cnab,cobranca_cnab_remessa",
        help="mode landing: labels da landing zone a drenar, separados por "
        "virgula (default: cobranca_cnab,cobranca_cnab_remessa)",
    )
    ap.add_argument("--glob", default="*", help="padrao de arquivo (default *)")
    ap.add_argument("--disabled", action="store_true", help="cria a fonte desabilitada")
    args = ap.parse_args()

    if args.mode == FILE_SOURCE_LOCAL_PATH:
        if not args.path:
            raise SystemExit("--path e obrigatorio no mode local_path")
        if args.remessa_path:
            # Multi-root: retorno + remessa na mesma inbox. O sync classifica
            # cada arquivo pelo header (nao pela pasta).
            file_source = {
                "mode": args.mode,
                "roots": [
                    {"path": args.path, "glob": args.glob},
                    {"path": args.remessa_path, "glob": args.glob},
                ],
            }
        else:
            file_source = {"mode": args.mode, "path": args.path, "glob": args.glob}
    elif args.mode == FILE_SOURCE_UPLOAD:
        if not args.staging_path:
            raise SystemExit("--staging-path e obrigatorio no mode upload")
        file_source = {
            "mode": args.mode,
            "staging_path": args.staging_path,
            "glob": args.glob,
        }
    else:  # landing (Strata Collector -> file_landing + storage)
        labels = [s.strip() for s in args.source_labels.split(",") if s.strip()]
        if not labels:
            raise SystemExit("--source-labels vazio no mode landing")
        file_source = {"mode": args.mode, "source_labels": labels}

    # Sem `layout`: o banco/layout sao detectados por arquivo (header CNAB).
    # `api` aceito como cadastro mas inerte: bloco preparado.
    config = {
        "file_source": file_source,
        "api": {"base_url": None, "credential_ref": None},
    }

    async with AsyncSessionLocal() as db:
        tenant_id = await _resolve_tenant_id(db, args.tenant)
        await upsert_config(
            db,
            tenant_id,
            SourceType.COBRANCA,
            config,
            environment=Environment.PRODUCTION,
            enabled=not args.disabled,
        )
    print(
        f"OK: fonte 'cobranca' (inbox) configurada para tenant {args.tenant} "
        f"(mode={args.mode})."
    )


if __name__ == "__main__":
    asyncio.run(main())
