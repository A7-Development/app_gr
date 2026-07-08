"""Scoring pass of the liquidation detection model.

Applies the ACTIVE version's coefficients to every scorable event — pure
arithmetic from the JSONB payload (sigmoid of the standardized linear
combination); sklearn is a TRAINING dependency only, scoring is
self-contained and reproducible from the version row.

Deterministic hard rules NEVER wait for a trained version: with no active
version, rows that fired `regra_dura` are still persisted (score NULL) so
the curation screen surfaces them from day one.

Every run writes one decision_log (type SCORE) with
rule_or_model_version = '<modelo>@v<versao>' (§14.5).
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risco.models import (
    DeteccaoModelo,
    DeteccaoModeloAtivo,
    DeteccaoModeloVersao,
    DeteccaoScore,
)
from app.modules.risco.services.deteccao_features import FeatureRow, montar_features
from app.shared.audit_log.decision_log import DecisionLog, DecisionType

logger = logging.getLogger(__name__)

_CHUNK = 2000
_TOP_FATORES = 5


def _score_row(row: FeatureRow, coef: dict[str, Any]) -> tuple[float, list[dict]]:
    """Probability + top explanatory contributions (§14.3)."""
    z = float(coef["intercept"])
    contribs: list[tuple[str, float]] = []
    for nome, spec in coef["features"].items():
        x = row.features.get(nome, 0.0)
        desvio = float(spec["desvio"]) or 1.0
        c = float(spec["coef"]) * ((x - float(spec["media"])) / desvio)
        z += c
        contribs.append((nome, c))
    prob = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
    top = sorted(contribs, key=lambda t: abs(t[1]), reverse=True)[:_TOP_FATORES]
    fatores = [
        {"feature": nome, "contrib": round(c, 4), "valor": row.features.get(nome, 0.0)}
        for nome, c in top
        if abs(c) > 1e-9
    ]
    return prob, fatores


async def pontuar(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    modelo_nome: str = "liquidacao_boleto",
    triggered_by: str = "system:scheduler",
) -> dict[str, Any]:
    """Score all events with the active version (or hard rules only)."""
    t0 = time.monotonic()
    modelo = (
        await db.execute(select(DeteccaoModelo).where(DeteccaoModelo.nome == modelo_nome))
    ).scalar_one_or_none()
    if modelo is None:
        raise ValueError(f"Modelo '{modelo_nome}' nao existe no catalogo.")

    ativo = (
        await db.execute(
            select(DeteccaoModeloVersao)
            .join(
                DeteccaoModeloAtivo,
                DeteccaoModeloAtivo.versao_id == DeteccaoModeloVersao.id,
            )
            .where(
                DeteccaoModeloAtivo.tenant_id == tenant_id,
                DeteccaoModeloAtivo.modelo_id == modelo.id,
            )
        )
    ).scalar_one_or_none()

    rows = await montar_features(db, tenant_id)

    registros: list[dict[str, Any]] = []
    n_regra = 0
    for r in rows:
        if ativo is not None:
            prob, fatores = _score_row(r, ativo.coeficientes)
            registros.append(
                {
                    "tenant_id": tenant_id,
                    "modelo_id": modelo.id,
                    "versao_id": ativo.id,
                    "liquidacao_id": r.liquidacao_id,
                    "score": round(prob, 5),
                    "fatores": fatores,
                    "features": r.features,
                    "regra_dura": r.regra_dura,
                    "regra_dura_motivo": r.regra_dura_motivo,
                }
            )
        elif r.regra_dura:
            # Regras nao esperam treino: persiste o disparo com score NULL.
            registros.append(
                {
                    "tenant_id": tenant_id,
                    "modelo_id": modelo.id,
                    "versao_id": None,
                    "liquidacao_id": r.liquidacao_id,
                    "score": None,
                    "fatores": None,
                    "features": r.features,
                    "regra_dura": True,
                    "regra_dura_motivo": r.regra_dura_motivo,
                }
            )
        if r.regra_dura:
            n_regra += 1

    for i in range(0, len(registros), _CHUNK):
        chunk = registros[i : i + _CHUNK]
        stmt = pg_insert(DeteccaoScore).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_deteccao_score_unidade",
            set_={
                "versao_id": stmt.excluded.versao_id,
                "score": stmt.excluded.score,
                "fatores": stmt.excluded.fatores,
                "features": stmt.excluded.features,
                "regra_dura": stmt.excluded.regra_dura,
                "regra_dura_motivo": stmt.excluded.regra_dura_motivo,
                "computed_at": stmt.excluded.computed_at,
            },
        )
        await db.execute(stmt)

    versao_label = f"{modelo_nome}@v{ativo.versao}" if ativo else f"{modelo_nome}@regras"
    summary = {
        "modelo": modelo_nome,
        "versao": ativo.versao if ativo else None,
        "eventos_avaliados": len(rows),
        "scores_gravados": len(registros),
        "regra_dura": n_regra,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }
    db.add(
        DecisionLog(
            tenant_id=tenant_id,
            decision_type=DecisionType.SCORE,
            inputs_ref={"modelo": modelo_nome},
            rule_or_model=modelo_nome,
            rule_or_model_version=versao_label,
            output=summary,
            explanation=(
                f"scoring {versao_label}: {len(registros)} scores gravados, "
                f"{n_regra} regras duras disparadas"
            ),
            triggered_by=triggered_by,
        )
    )
    logger.info("deteccao_scoring: %s — %s", versao_label, summary)
    return summary
