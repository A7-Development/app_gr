"""Backfill: parseia o bronze CNAB (arquivo) -> wh_cnab_raw_ocorrencia.

Os arquivos de BMP (274) e Vortx (310) foram ingeridos como bronze-only ("sem
parser"), entao seus registros de detalhe nunca viraram `wh_cnab_raw_ocorrencia`
-- e por isso o pipeline de evento/vigente nunca os enxergou (boletos invisiveis
-> titulos como "Só BITFIN" falso). BMP/Vortx usam o MESMO CNAB400-padrao do
Bradesco (validado 2026-06-06: 100% dos detalhes cruzam wh_titulo), entao o
parser Bradesco (registrado em etl._LAYOUTS p/ cnab400_bmp/cnab400_vortx)
parseia direto.

Este oneshot re-parseia os arquivos de retorno desses bancos e persiste as
ocorrencias. Idempotente por SKIP: arquivo que ja tem ocorrencias e pulado
(evita duplicata e preserva a linhagem ocorrencia_id -> wh_boleto_evento).
Depois rode backfill_boleto_evento.py + project_boleto_vigente.py.

Uso (de backend/):
    .venv/bin/python scripts/backfill_cnab_ocorrencia.py            # bmp + vortx
    .venv/bin/python scripts/backfill_cnab_ocorrencia.py bmp vortx  # explicito
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

import app.shared.identity.tenant  # noqa: F401  -- registry SQLAlchemy completo
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.cobranca.etl import _LAYOUTS
from app.modules.integracoes.adapters.cobranca.persist import persist_ocorrencias
from app.warehouse.cnab_raw_arquivo import TIPO_ARQUIVO_RETORNO, CnabRawArquivo
from app.warehouse.cnab_raw_ocorrencia import CnabRawOcorrencia

_BANCOS_DEFAULT = ["bmp", "vortx"]


async def main() -> None:
    bancos = sys.argv[1:] or _BANCOS_DEFAULT

    async with AsyncSessionLocal() as db:
        arquivos = (
            await db.execute(
                select(CnabRawArquivo).where(
                    CnabRawArquivo.tipo_arquivo == TIPO_ARQUIVO_RETORNO,
                    CnabRawArquivo.banco.in_(bancos),
                )
            )
        ).scalars().all()

        # Arquivos que JA tem ocorrencias (pular -- idempotencia + linhagem).
        ja_parseados = set(
            (
                await db.execute(
                    select(CnabRawOcorrencia.arquivo_id).distinct()
                )
            ).scalars().all()
        )

        print(f"arquivos retorno {bancos}: {len(arquivos)}")
        n_arq = n_oc = n_skip = n_sem_layout = 0
        for arq in arquivos:
            if arq.id in ja_parseados:
                n_skip += 1
                continue
            spec = _LAYOUTS.get(arq.layout)
            if spec is None:
                n_sem_layout += 1
                continue
            parsed = spec["parse_retorno"](arq.conteudo)
            n_oc += await persist_ocorrencias(
                db, arquivo=arq, ocorrencias=parsed.ocorrencias
            )
            n_arq += 1
        await db.commit()

        print(
            f"parseados={n_arq} ocorrencias={n_oc} "
            f"pulados(ja tinham)={n_skip} sem_layout={n_sem_layout}"
        )


if __name__ == "__main__":
    asyncio.run(main())
