"""Scoring agendado do modelo de deteccao de liquidacao — job APScheduler.

Roda a cada 6h (mesma cadencia do endpoint `bitfin.liquidacoes` que alimenta
`wh_liquidacao`): para cada tenant com eventos de liquidacao, aplica a versao
ATIVA do modelo `liquidacao_boleto` (ou apenas as regras duras, quando nenhum
treino foi ativado) e grava `deteccao_score` + decision_log (§14.5).

A tela /risco/curadoria-liquidacoes le os scores daqui — o backend longo e
visivel via decision_log e `computed_at` nas linhas (§7.3).
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.modules.risco.services.cedente_risco import consolidar
from app.modules.risco.services.deteccao_scoring import pontuar

logger = logging.getLogger(__name__)

INTERVAL_MINUTES = 360


async def run() -> None:
    """Um tick: pontua cada tenant que possui eventos de liquidacao."""
    async with AsyncSessionLocal() as db:
        tenant_ids = [
            r[0]
            for r in await db.execute(
                text("SELECT DISTINCT tenant_id FROM wh_liquidacao")
            )
        ]

    for tenant_id in tenant_ids:
        try:
            async with AsyncSessionLocal() as db:
                summary = await pontuar(
                    db,
                    tenant_id,
                    triggered_by="scheduler:deteccao_scoring",
                )
                # Consolida o risco por cedente (painel) na mesma transacao.
                await consolidar(
                    db, tenant_id, triggered_by="scheduler:deteccao_scoring"
                )
                await db.commit()
            logger.info(
                "deteccao_scoring tenant=%s: %d scores (%d regras duras)",
                tenant_id,
                summary["scores_gravados"],
                summary["regra_dura"],
            )
        except Exception:
            logger.exception("deteccao_scoring falhou para tenant=%s", tenant_id)
