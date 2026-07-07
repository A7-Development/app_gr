"""Re-parse do bronze CNAB: atualiza o payload de wh_cnab_raw_ocorrencia in-place.

Quando o parser ganha campos novos (ex.: v1.3.0 -- banco_pagador/agencia_pagadora/
data_credito das posicoes 166-173/296-301 do retorno; sacado_documento/nome das
posicoes 219-274 da remessa), o payload das ocorrencias ja pousadas fica
defasado. Este oneshot re-parseia o `conteudo` (o raw imutavel de verdade) de
cada arquivo (retorno E remessa) e ATUALIZA o payload das ocorrencias
existentes casando por (arquivo_id, linha_num) -- preservando `id` e, portanto,
a linhagem ocorrencia_id -> wh_boleto_evento.

NAO insere nem apaga ocorrencias: linha parseada sem row correspondente (ou
vice-versa) e reportada como mismatch e deixada intacta (investigar manualmente).

Depois rode o re-decode (decode_tenant_eventos, ex. via backfill_boleto_evento.py)
para propagar os campos novos ao silver.

Uso (de backend/):
    .venv/bin/python scripts/reparse_cnab_ocorrencias.py             # todos os bancos com parser
    .venv/bin/python scripts/reparse_cnab_ocorrencias.py bradesco    # so um banco
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

import app.shared.identity.tenant  # noqa: F401  -- registry SQLAlchemy completo
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.cobranca.etl import _LAYOUTS
from app.warehouse.cnab_raw_arquivo import (
    TIPO_ARQUIVO_REMESSA,
    TIPO_ARQUIVO_RETORNO,
    CnabRawArquivo,
)
from app.warehouse.cnab_raw_ocorrencia import CnabRawOcorrencia

_COMMIT_EVERY = 50  # arquivos por commit (transacoes curtas na VPN)


async def main() -> None:
    bancos = sys.argv[1:] or None

    async with AsyncSessionLocal() as db:
        stmt = select(CnabRawArquivo.id).where(
            CnabRawArquivo.tipo_arquivo.in_(
                [TIPO_ARQUIVO_RETORNO, TIPO_ARQUIVO_REMESSA]
            )
        )
        if bancos:
            stmt = stmt.where(CnabRawArquivo.banco.in_(bancos))
        arquivo_ids = (await db.execute(stmt)).scalars().all()
        print(f"arquivos de retorno a re-parsear: {len(arquivo_ids)}")

        n_arq = n_upd = n_mismatch = n_sem_layout = 0
        for i, arq_id in enumerate(arquivo_ids, start=1):
            arq = (
                await db.execute(
                    select(CnabRawArquivo).where(CnabRawArquivo.id == arq_id)
                )
            ).scalar_one()
            spec = _LAYOUTS.get(arq.layout)
            if spec is None:
                n_sem_layout += 1
                continue
            parser = (
                spec["parse_retorno"]
                if arq.tipo_arquivo == TIPO_ARQUIVO_RETORNO
                else spec["parse_remessa"]
            )
            parsed = parser(arq.conteudo)
            por_linha = {o.linha_num: o.payload for o in parsed.ocorrencias}

            rows = (
                await db.execute(
                    select(CnabRawOcorrencia).where(
                        CnabRawOcorrencia.arquivo_id == arq.id
                    )
                )
            ).scalars().all()
            for row in rows:
                novo = por_linha.pop(row.linha_num, None)
                if novo is None:
                    n_mismatch += 1  # row sem linha parseada correspondente
                    continue
                if row.payload != novo:
                    row.payload = novo
                    n_upd += 1
            n_mismatch += len(por_linha)  # linhas parseadas sem row no bronze
            n_arq += 1
            if i % _COMMIT_EVERY == 0:
                await db.commit()
                print(f"  ...{i}/{len(arquivo_ids)} arquivos ({n_upd} payloads)")
        await db.commit()

        print(
            f"re-parseados={n_arq} payloads_atualizados={n_upd} "
            f"mismatches={n_mismatch} sem_layout={n_sem_layout}"
        )


if __name__ == "__main__":
    asyncio.run(main())
