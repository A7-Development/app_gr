"""Re-mapeia silver a partir de uma linha bronze ja persistida.

Uso (do diretorio backend/):

    .venv\\Scripts\\python.exe scripts/serasa_pj_remap.py --raw-id <UUID>

Exemplo:

    .venv\\Scripts\\python.exe scripts/serasa_pj_remap.py \\
        --raw-id 91795324-20ad-4d57-832f-c8b3e43d7702

Util pra iterar no mapper sem pagar consulta nova na Serasa. UPSERT
idempotente em silver (consulta + filhas) — re-rodar substitui linhas
existentes pelo source_id determinista.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

import app.shared.identity.tenant
import app.warehouse  # noqa: F401
from app.modules.integracoes.services.serasa_pj_query import remap_from_raw


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-id",
        required=True,
        help="UUID da linha em wh_serasa_pj_raw_relatorio",
    )
    args = parser.parse_args()

    try:
        raw_id = UUID(args.raw_id)
    except ValueError as e:
        print(f"[erro] raw-id invalido: {e}", file=sys.stderr)
        return 2

    print(f"[remap] raw_id={raw_id}")
    summary = await remap_from_raw(raw_id=raw_id)

    print("\n[summary]")
    print(f"  ok:                     {summary['ok']}")
    print(f"  cnpj:                   {summary['cnpj']}")
    print(f"  consulta_id:            {summary['consulta_id']}")
    print(f"  reciprocity_downgrade:  {summary['reciprocity_downgrade']}")
    if summary["errors"]:
        print("  errors:")
        for e in summary["errors"]:
            print(f"    - {e}")

    print("\n[silver] linhas geradas por tabela:")
    counts = summary["counts"]
    print("  consulta:                1")
    print(f"  socios:                  {counts.get('socios', 0)}")
    print(f"  restricoes:              {counts.get('restricoes', 0)}")
    print(
        f"  restricao_summaries:     "
        f"{counts.get('restricao_summaries', 0)}"
    )
    print(f"  participacoes:           {counts.get('participacoes', 0)}")
    print(f"  enderecos:               {counts.get('enderecos', 0)}")
    print(
        f"  pagamento_buckets:       "
        f"{counts.get('pagamento_buckets', 0)}"
    )
    print(
        f"  inquiries_anteriores:    "
        f"{counts.get('inquiries_anteriores', 0)}"
    )
    print(f"  predecessores:           {counts.get('predecessores', 0)}")
    print(
        f"  inquiries_mensais:       "
        f"{counts.get('inquiries_mensais', 0)}"
    )
    print(
        f"  business_references:     "
        f"{counts.get('business_references', 0)}"
    )
    print(
        f"  pagamento_evolucao:      "
        f"{counts.get('pagamento_evolucao_mensal', 0)}"
    )
    print(
        f"  atraso_medio_mensal:     "
        f"{counts.get('atraso_medio_mensal', 0)}"
    )
    print(
        f"  payment_comparatives:    "
        f"{counts.get('payment_comparatives', 0)}"
    )

    if not summary["ok"]:
        return 1

    # Re-le header pra mostrar os campos populados.
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.warehouse.serasa_pj_consulta import SerasaPjConsulta

    async with AsyncSessionLocal() as db:
        consulta = (
            await db.execute(
                select(SerasaPjConsulta).where(
                    SerasaPjConsulta.id == UUID(summary["consulta_id"])
                )
            )
        ).scalar_one_or_none()

    if consulta:
        print("\n[silver] header da consulta:")
        print(f"  razao_social:           {consulta.razao_social}")
        print(f"  situacao_cadastral:     {consulta.situacao_cadastral}")
        print(f"  data_constituicao:      {consulta.data_constituicao}")
        print(f"  cnae:                   {consulta.atividade_principal_cnae}")
        print(f"  atividade:              {consulta.atividade_principal_descricao}")
        print(f"  capital_social:         {consulta.capital_social}")
        print(f"  faturamento_presumido:  {consulta.faturamento_presumido}")
        print(f"  score_h4pj:             {consulta.score_h4pj}")
        print(
            f"  has refin/pefin/protesto/cheque: "
            f"{consulta.has_refin}/{consulta.has_pefin}/"
            f"{consulta.has_protesto}/{consulta.has_cheque}"
        )
        print(
            f"  count refin/pefin/protesto/cheque: "
            f"{consulta.count_refin}/{consulta.count_pefin}/"
            f"{consulta.count_protesto}/{consulta.count_cheque}"
        )
        print(f"  valor_total_restricoes: {consulta.valor_total_restricoes}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
