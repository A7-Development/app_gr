"""Smoke test: consulta Serasa PJ real e persiste raw + silver.

Uso (do diretorio backend/):

    .venv\\Scripts\\python.exe scripts/serasa_pj_query.py \\
        --tenant a7-credit \\
        --cnpj 12.345.678/0001-99 \\
        [--env production|sandbox] \\
        [--triggered-by user:ricardo] \\
        [--cost-center smoke-test] \\
        [--dump-payload payload.json]

Tenant pode ser slug (`a7-credit`) ou UUID. CNPJ aceita com ou sem mascara.

NAO use em producao automaticamente. Bypass do gating REST, util pra validar
o pipeline ponta-a-ponta (auth -> bronze -> mapper -> silver -> decision_log)
com credenciais reais e capturar o JSON cru pra estudo.

Output:
    1. Summary do `execute_pj_query`.
    2. Linhas geradas em cada tabela silver.
    3. (opcional) Salva payload bruto em arquivo JSON.
    4. Comandos SQL prontos pra inspecionar o dado gravado.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

# Side-effect imports — registram tabelas no metadata do SQLAlchemy.
import app.shared.identity.tenant  # noqa: F401
import app.warehouse  # noqa: F401  (registra wh_serasa_pj_*)
from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.services.serasa_pj_query import execute_pj_query
from app.shared.identity.tenant import Tenant
from app.warehouse.serasa_pj_consulta import SerasaPjConsulta
from app.warehouse.serasa_pj_endereco import SerasaPjEndereco
from app.warehouse.serasa_pj_participacao import SerasaPjParticipacao
from app.warehouse.serasa_pj_raw_relatorio import SerasaPjRawRelatorio
from app.warehouse.serasa_pj_restricao import SerasaPjRestricao
from app.warehouse.serasa_pj_socio import SerasaPjSocio


def _strip_non_digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


async def _resolve_tenant(tenant_arg: str) -> UUID:
    """Aceita UUID literal ou slug. Levanta ValueError se nao encontra."""
    try:
        return UUID(tenant_arg)
    except ValueError:
        pass
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(Tenant.id).where(Tenant.slug == tenant_arg)
            )
        ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"tenant slug='{tenant_arg}' nao encontrado")
    return row


async def _dump_raw_payload(raw_id: UUID, path: Path) -> None:
    """Le payload bronze gravado e salva em arquivo JSON."""
    async with AsyncSessionLocal() as db:
        row = await db.get(SerasaPjRawRelatorio, raw_id)
    if row is None:
        print(f"[warn] raw_id={raw_id} nao encontrado pra dump")
        return
    path.write_text(
        json.dumps(row.payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[dump] payload bruto salvo em {path} ({path.stat().st_size:,} bytes)")


async def _print_silver_counts(consulta_id: UUID) -> None:
    """Conta linhas em cada tabela silver pra esta consulta."""
    async with AsyncSessionLocal() as db:
        counts = {
            "consulta": (
                await db.execute(
                    select(SerasaPjConsulta).where(
                        SerasaPjConsulta.id == consulta_id
                    )
                )
            ).scalars().all(),
            "socios": (
                await db.execute(
                    select(SerasaPjSocio).where(
                        SerasaPjSocio.consulta_id == consulta_id
                    )
                )
            ).scalars().all(),
            "restricoes": (
                await db.execute(
                    select(SerasaPjRestricao).where(
                        SerasaPjRestricao.consulta_id == consulta_id
                    )
                )
            ).scalars().all(),
            "participacoes": (
                await db.execute(
                    select(SerasaPjParticipacao).where(
                        SerasaPjParticipacao.consulta_id == consulta_id
                    )
                )
            ).scalars().all(),
            "enderecos": (
                await db.execute(
                    select(SerasaPjEndereco).where(
                        SerasaPjEndereco.consulta_id == consulta_id
                    )
                )
            ).scalars().all(),
        }

    print("\n[silver] linhas geradas por tabela:")
    print(f"  wh_serasa_pj_consulta:      {len(counts['consulta'])}")
    print(f"  wh_serasa_pj_socio:         {len(counts['socios'])}")
    print(f"  wh_serasa_pj_restricao:     {len(counts['restricoes'])}")
    print(f"  wh_serasa_pj_participacao:  {len(counts['participacoes'])}")
    print(f"  wh_serasa_pj_endereco:      {len(counts['enderecos'])}")

    if counts["consulta"]:
        c = counts["consulta"][0]
        print("\n[silver] header da consulta:")
        print(f"  razao_social:           {c.razao_social}")
        print(f"  situacao_cadastral:     {c.situacao_cadastral}")
        print(f"  data_constituicao:      {c.data_constituicao}")
        print(f"  capital_social:         {c.capital_social}")
        print(f"  faturamento_presumido:  {c.faturamento_presumido}")
        print(f"  score_h4pj:             {c.score_h4pj}")
        print(f"  score_classe:           {c.score_classe}")
        print(
            f"  has_refin/pefin/protesto/cheque: "
            f"{c.has_refin}/{c.has_pefin}/{c.has_protesto}/{c.has_cheque}"
        )
        print(
            f"  count_refin/pefin/protesto/cheque: "
            f"{c.count_refin}/{c.count_pefin}/"
            f"{c.count_protesto}/{c.count_cheque}"
        )
        print(f"  valor_total_restricoes: {c.valor_total_restricoes}")
        print(f"  reciprocity_downgrade:  {c.reciprocity_downgrade}")


def _print_inspection_sql(raw_id: UUID, consulta_id: UUID | None) -> None:
    print("\n[sql] queries pra inspecionar:")
    print(
        f"  SELECT cnpj, requested_report, actual_report_returned, "
        f"status_code, latency_ms, jsonb_pretty(payload) "
        f"FROM wh_serasa_pj_raw_relatorio WHERE id = '{raw_id}';"
    )
    if consulta_id:
        print(
            f"  SELECT * FROM wh_serasa_pj_consulta WHERE id = '{consulta_id}';"
        )
        print(
            f"  SELECT documento, documento_tipo, nome, qualificacao, percentual "
            f"FROM wh_serasa_pj_socio WHERE consulta_id = '{consulta_id}';"
        )
        print(
            f"  SELECT tipo, valor, credor, data_ocorrencia, data_baixa "
            f"FROM wh_serasa_pj_restricao WHERE consulta_id = '{consulta_id}' "
            f"ORDER BY tipo, data_ocorrencia DESC;"
        )
        print(
            f"  SELECT documento_empresa, razao_social, percentual "
            f"FROM wh_serasa_pj_participacao WHERE consulta_id = '{consulta_id}';"
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True, help="slug ou UUID do tenant")
    parser.add_argument("--cnpj", required=True, help="CNPJ (com ou sem mascara)")
    parser.add_argument(
        "--env",
        choices=["production", "sandbox"],
        default="production",
        help="ambiente do tenant_source_config (default: production)",
    )
    parser.add_argument(
        "--triggered-by",
        default="user:cli",
        help="rastreio livre (default: user:cli)",
    )
    parser.add_argument(
        "--cost-center",
        default=None,
        help="X-Cost-Center pra Serasa (max 12 chars; opcional)",
    )
    parser.add_argument(
        "--report-type",
        default=None,
        help="override do tipo de relatorio (default: do config)",
    )
    parser.add_argument(
        "--dump-payload",
        default=None,
        help="path pra salvar payload bruto em JSON",
    )
    args = parser.parse_args()

    cnpj_clean = _strip_non_digits(args.cnpj)
    if len(cnpj_clean) != 14:
        print(
            f"[erro] CNPJ invalido: '{args.cnpj}' "
            f"(precisa ter 14 digitos, tem {len(cnpj_clean)})",
            file=sys.stderr,
        )
        return 2

    try:
        tenant_id = await _resolve_tenant(args.tenant)
    except ValueError as e:
        print(f"[erro] {e}", file=sys.stderr)
        return 2

    print(f"[smoke] tenant_id={tenant_id} cnpj={cnpj_clean} env={args.env}")
    print(f"[smoke] disparando execute_pj_query...")

    summary = await execute_pj_query(
        tenant_id=tenant_id,
        cnpj=cnpj_clean,
        triggered_by=args.triggered_by,
        environment=Environment(args.env),
        report_type=args.report_type,
        cost_center=args.cost_center,
    )

    print("\n[summary]")
    print(f"  ok:                     {summary['ok']}")
    print(f"  raw_id:                 {summary['raw_id']}")
    print(f"  consulta_id:            {summary['consulta_id']}")
    print(f"  requested_report:       {summary['requested_report']}")
    print(f"  actual_report_returned: {summary['actual_report_returned']}")
    print(f"  reciprocity_downgrade:  {summary['reciprocity_downgrade']}")
    print(f"  latency_ms:             {summary['latency_ms']}")
    print(f"  adapter_version:        {summary['adapter_version']}")
    if summary["errors"]:
        print(f"  errors:")
        for e in summary["errors"]:
            print(f"    - {e}")

    if not summary["ok"]:
        print("\n[fail] consulta nao concluiu — silver nao foi populada")
        return 1

    raw_id: UUID = summary["raw_id"]
    consulta_id: UUID | None = summary["consulta_id"]

    if consulta_id:
        await _print_silver_counts(consulta_id)

    if args.dump_payload:
        await _dump_raw_payload(raw_id, Path(args.dump_payload))

    _print_inspection_sql(raw_id, consulta_id)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
