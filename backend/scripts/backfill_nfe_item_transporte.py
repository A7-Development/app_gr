"""Backfill wh_nfe_item (produtos) + colunas de transporte em wh_nfe.

One-shot, rodar APOS a migration b6d2f8a1c3e9. Le o raw imutavel
(wh_nfe_raw_documento), re-parseia itens + transporte (parse_nfe) e popula
o silver das notas ja ingeridas. Idempotente (delete-then-insert de itens por
nota); re-execucao e inofensiva. Paginado para nao carregar 20k JSONB de uma vez.

    python -m scripts.backfill_nfe_item_transporte
"""

from __future__ import annotations

import asyncio
import logging

import sqlalchemy as sa

# Side-effect import: registra tenants/users no metadata — sem isso o FK
# wh_nfe.tenant_id -> tenants.id nao resolve (NoReferencedTableError).
import app.shared.identity  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.fiscal.parsers import parse_nfe
from app.warehouse.fiscal_nfe import Nfe, NfeItem, NfeRawDocumento

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill_nfe_item")

_BATCH = 500


async def main() -> None:
    total_notas = 0
    total_itens = 0
    offset = 0
    async with AsyncSessionLocal() as db:
        while True:
            rows = (
                await db.execute(
                    sa.select(
                        NfeRawDocumento.tenant_id,
                        NfeRawDocumento.chave_acesso,
                        NfeRawDocumento.documento,
                    )
                    .order_by(NfeRawDocumento.id)
                    .limit(_BATCH)
                    .offset(offset)
                )
            ).all()
            if not rows:
                break
            for r in rows:
                parsed = parse_nfe(r.documento)
                if parsed is None:
                    continue
                nfe = (
                    await db.execute(
                        sa.select(Nfe).where(
                            Nfe.tenant_id == r.tenant_id,
                            Nfe.chave_acesso == r.chave_acesso,
                        )
                    )
                ).scalar_one_or_none()
                if nfe is None:
                    continue
                nfe.transportadora_documento = parsed.transportadora_documento
                nfe.transportadora_nome = parsed.transportadora_nome
                nfe.veiculo_placa = parsed.veiculo_placa
                nfe.veiculo_uf = parsed.veiculo_uf
                await db.execute(sa.delete(NfeItem).where(NfeItem.nfe_id == nfe.id))
                for item in parsed.itens:
                    db.add(
                        NfeItem(
                            tenant_id=r.tenant_id,
                            nfe_id=nfe.id,
                            n_item=item.n_item,
                            codigo=item.codigo,
                            descricao=item.descricao,
                            ncm=item.ncm,
                            cfop=item.cfop,
                            ean=item.ean,
                            quantidade=item.quantidade,
                            unidade=item.unidade,
                            valor_unitario=item.valor_unitario,
                            valor_total=item.valor_total,
                        )
                    )
                    total_itens += 1
                total_notas += 1
            await db.commit()
            offset += _BATCH
            logger.info("... %d notas processadas (%d itens)", total_notas, total_itens)
    logger.info("backfill concluido: %d notas, %d itens", total_notas, total_itens)


if __name__ == "__main__":
    asyncio.run(main())
