"""CLI: varre todos os endpoints de Relatorio QiTech e grava os responses.

Ferramenta de exploracao — NAO e parte do fluxo de producao. Serve para, com
um tenant + credencial valida + uma data, disparar 1 request autenticada
por tipo-de-mercado do catalogo, persistir cada resposta em um .json
separado e imprimir um resumo legivel no console.

Saida tipica por execucao:

    qitech_samples/<tenant_slug>/<YYYY-MM-DD>/
        outros-fundos.json
        rf.json
        ...
        _summary.json          ← agregado dos 23 (status, latencia, shape)

Com esses arquivos em mao, decidimos:
    - schema de cada tipo (Pydantic models)
    - mapping para modelo canonico (warehouse)
    - quais endpoints valem a pena entrar no sync default

Uso:
    uv run python -m app.modules.integracoes.adapters.admin.qitech.explore_reports \\
        --tenant a7-credit --data 2024-01-15

    # so um subset:
    uv run python -m ... --data 2024-01-15 --tipos outros-fundos,rf,rv

    # parar no primeiro sucesso (smoke test):
    uv run python -m ... --data 2024-01-15 --only-first
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechAdapterError
from app.modules.integracoes.adapters.admin.qitech.reports import (
    TIPOS_DE_MERCADO_CONHECIDOS,
    fetch_market_report,
)
from app.modules.integracoes.services.source_config import get_decrypted_config
from app.shared.identity.tenant import Tenant

# -- utilidades ----------------------------------------------------------------


def _shape(body: Any) -> str:
    """Resume o root do JSON sem vazar conteudo sensivel.

    Exemplos:
        []             -> "list[0]"
        [a, b, c]      -> "list[3]"
        {k1,k2,k3}     -> "dict{k1, k2, k3}"
        {k1..k10}      -> "dict{k1, k2, k3, k4 ...+6}"
        "foo"          -> "str(3)"
        42             -> "int"
        None           -> "null"
    """
    if body is None:
        return "null"
    if isinstance(body, list):
        return f"list[{len(body)}]"
    if isinstance(body, dict):
        keys = list(body.keys())
        head = ", ".join(keys[:4])
        tail = f" ...+{len(keys) - 4}" if len(keys) > 4 else ""
        return f"dict{{{head}{tail}}}"
    if isinstance(body, str):
        return f"str({len(body)})"
    return type(body).__name__


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# -- resolucao de tenant -------------------------------------------------------


async def _resolve_tenant_id(slug: str) -> UUID:
    async with AsyncSessionLocal() as db:
        stmt = select(Tenant).where(Tenant.slug == slug)
        tenant = (await db.execute(stmt)).scalar_one_or_none()
        if tenant is None:
            raise SystemExit(f"Tenant com slug '{slug}' nao encontrado.")
        return tenant.id


# -- exploracao de um endpoint -------------------------------------------------


async def _explore_one(
    *,
    client,
    tipo: str,
    label: str,
    posicao: date,
    out_dir: Path,
) -> dict:
    """Chama 1 endpoint, grava o body em disco, devolve entry de summary."""
    t0 = time.perf_counter()
    try:
        body = await fetch_market_report(
            client=client, tipo_de_mercado=tipo, posicao=posicao
        )
    except QiTechAdapterError as e:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        detail = getattr(e, "detail", None)
        # Persiste o body bruto do erro (util pra descobrir se a QiTech fala
        # "data sem movimento", "tipo nao autorizado", "carteira obrigatoria",
        # etc). Arquivo separado pra nao misturar com sucessos.
        if detail:
            (out_dir / f"{tipo}.error.txt").write_text(detail, encoding="utf-8")
        return {
            "tipo": tipo,
            "label": label,
            "ok": False,
            "latency_ms": elapsed_ms,
            "status_code": getattr(e, "status_code", None),
            "error": f"{type(e).__name__}: {e}",
            "detail": detail,
        }

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    out_path = out_dir / f"{tipo}.json"
    _write_json(out_path, body)
    return {
        "tipo": tipo,
        "label": label,
        "ok": True,
        "latency_ms": elapsed_ms,
        "shape": _shape(body),
        "bytes": out_path.stat().st_size,
        "file": out_path.name,
    }


# -- orquestracao --------------------------------------------------------------


async def explore_all(
    *,
    tenant_id: UUID,
    tenant_slug: str,
    environment: Environment,
    config_dict: dict,
    posicao: date,
    tipos: list[tuple[str, str]],
    output_root: Path,
    only_first: bool = False,
) -> dict:
    """Itera os tipos e gera 1 .json por endpoint + _summary.json agregado."""
    config = QiTechConfig.from_dict(config_dict)
    out_dir = output_root / tenant_slug / posicao.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[explore] tenant={tenant_slug} env={environment.value}")
    print(f"[explore] data={posicao.isoformat()}  tipos={len(tipos)}")
    print(f"[explore] destino={out_dir}")
    print()

    results: list[dict] = []
    async with build_async_client(
        tenant_id=tenant_id,
        environment=environment,
        config=config,
    ) as client:
        for tipo, label in tipos:
            r = await _explore_one(
                client=client,
                tipo=tipo,
                label=label,
                posicao=posicao,
                out_dir=out_dir,
            )
            results.append(r)
            badge = "OK " if r["ok"] else "ERR"
            detail = r.get("shape") or r.get("error", "")
            print(
                f"  [{badge}] {tipo:<38} "
                f"{r['latency_ms']:>7.1f} ms   {detail}"
            )
            if only_first and r["ok"]:
                break

    ok = sum(1 for r in results if r["ok"])
    err = sum(1 for r in results if not r["ok"])
    summary = {
        "tenant": tenant_slug,
        "tenant_id": str(tenant_id),
        "environment": environment.value,
        "data": posicao.isoformat(),
        "tipos_tentados": len(results),
        "ok": ok,
        "err": err,
        "results": results,
    }
    _write_json(out_dir / "_summary.json", summary)

    print()
    print(f"[explore] {ok}/{len(results)} OK · {err} erros")
    print(f"[explore] summary: {out_dir / '_summary.json'}")
    return summary


# -- entrypoint ---------------------------------------------------------------


def _parse_tipos(raw: str | None) -> list[tuple[str, str]]:
    """Retorna [(codigo, label), ...] filtrado pelo raw csv do usuario.

    Se raw vier vazio, usa o catalogo inteiro. Avisa sobre codigos desconhecidos
    ao inves de silenciosamente ignorar.
    """
    full = list(TIPOS_DE_MERCADO_CONHECIDOS)
    if not raw:
        return full

    wanted = [x.strip() for x in raw.split(",") if x.strip()]
    mapping = dict(full)
    unknown = [w for w in wanted if w not in mapping]
    if unknown:
        raise SystemExit(
            f"Tipo(s) desconhecido(s): {unknown}. "
            f"Validos: {sorted(mapping.keys())}"
        )
    return [(w, mapping[w]) for w in wanted]


async def _main(
    tenant_slug: str,
    environment: Environment,
    posicao: date,
    tipos_csv: str | None,
    output_root: Path,
    only_first: bool,
) -> int:
    tipos = _parse_tipos(tipos_csv)
    tenant_id = await _resolve_tenant_id(tenant_slug)

    async with AsyncSessionLocal() as db:
        cfg = await get_decrypted_config(
            db, tenant_id, SourceType.ADMIN_QITECH, environment
        )
    if cfg is None:
        raise SystemExit(
            f"Tenant {tenant_id} sem tenant_source_config para admin:qitech "
            f"({environment.value})."
        )

    summary = await explore_all(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        environment=environment,
        config_dict=cfg,
        posicao=posicao,
        tipos=tipos,
        output_root=output_root,
        only_first=only_first,
    )
    # Exit code = 0 se teve pelo menos 1 OK, 1 se tudo falhou.
    return 0 if summary["ok"] > 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Varre todos os endpoints /v2/netreport/report/market e "
        "persiste os responses em JSON para analise."
    )
    parser.add_argument(
        "--tenant",
        default="a7-credit",
        help="Slug do tenant alvo (default: a7-credit)",
    )
    parser.add_argument(
        "--environment",
        choices=[Environment.SANDBOX.value, Environment.PRODUCTION.value],
        default=Environment.PRODUCTION.value,
    )
    parser.add_argument(
        "--data",
        required=True,
        help="Data de posicao no formato YYYY-MM-DD (path param `data`).",
    )
    parser.add_argument(
        "--tipos",
        default=None,
        help="Subset de codigos separados por virgula (default: todos).",
    )
    parser.add_argument(
        "--output-dir",
        default="qitech_samples",
        help="Diretorio raiz dos samples (default: ./qitech_samples)",
    )
    parser.add_argument(
        "--only-first",
        action="store_true",
        help="Para no primeiro sucesso — util para smoke test.",
    )
    args = parser.parse_args()

    try:
        posicao = date.fromisoformat(args.data)
    except ValueError as e:
        raise SystemExit(f"--data invalida: {e}") from e

    exit_code = asyncio.run(
        _main(
            tenant_slug=args.tenant,
            environment=Environment(args.environment),
            posicao=posicao,
            tipos_csv=args.tipos,
            output_root=Path(args.output_dir),
            only_first=args.only_first,
        )
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
