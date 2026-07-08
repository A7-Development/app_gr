"""Training of the liquidation detection model (sklearn logistic, OOT split).

Labels come EXCLUSIVELY from `curadoria_tag` (latest human verdict per
liquidation — IA opina, humano homologa; nothing is hardcoded here).
Negatives = tagged `ok` + a capped random sample of untagged events
(presumed-good under the low base rate; documented in the version notes).
No SMOTE / synthetic oversampling — `class_weight='balanced'` only
(hard handoff rule).

The trained version is persisted as auditable JSONB coefficients
(intercept + per-feature coef/mean/std) in `deteccao_modelo_versao` and is
born INACTIVE — activation is an explicit human act via the API.

Evaluation is OUT-OF-TIME: train < cutoff, test >= cutoff (default last 60
days), reporting Gini, KS and precision@20 — measured for real, per the
2026-07-08 decision (nao adiar generalizacao por definicao).
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risco.models import DeteccaoModelo, DeteccaoModeloVersao
from app.modules.risco.services.deteccao_features import (
    FEATURE_NAMES,
    FeatureRow,
    montar_features,
)
from app.shared.audit_log.decision_log import DecisionLog, DecisionType

logger = logging.getLogger(__name__)

_MIN_POSITIVOS = 10
_MAX_NEG_POR_POS = 20
_SEED = 42

_SQL_TAGS_VIGENTES = text("""
SELECT DISTINCT ON (liquidacao_id) liquidacao_id, tag
FROM curadoria_tag
WHERE tenant_id = :tenant_id AND modelo_id = :modelo_id
ORDER BY liquidacao_id, created_at DESC
""")


def _sigmoid_inputs(
    rows: list[FeatureRow], names: tuple[str, ...]
) -> list[list[float]]:
    return [[r.features.get(n, 0.0) for n in names] for r in rows]


def _gini_ks(y_true: list[int], y_score: list[float]) -> tuple[float | None, float | None]:
    """Gini (2*AUC-1) + KS. None when one class is absent."""
    if not y_true or len(set(y_true)) < 2:
        return None, None
    from sklearn.metrics import roc_auc_score, roc_curve

    auc = roc_auc_score(y_true, y_score)
    fpr, tpr, _ = roc_curve(y_true, y_score)
    ks = max(abs(t - f) for t, f in zip(tpr, fpr, strict=True))
    return round(2 * auc - 1, 4), round(float(ks), 4)


def _precision_at_k(y_true: list[int], y_score: list[float], k: int = 20) -> float | None:
    if not y_true:
        return None
    ordenado = sorted(zip(y_score, y_true, strict=True), reverse=True)[:k]
    if not ordenado:
        return None
    return round(sum(y for _, y in ordenado) / len(ordenado), 4)


async def treinar(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    modelo_nome: str = "liquidacao_boleto",
    janela_dias: int = 365,
    oot_dias: int = 60,
    trained_by: UUID | None = None,
    triggered_by: str = "user:api",
) -> dict[str, Any]:
    """Train a new INACTIVE version from current curation tags."""
    modelo = (
        await db.execute(select(DeteccaoModelo).where(DeteccaoModelo.nome == modelo_nome))
    ).scalar_one_or_none()
    if modelo is None:
        raise ValueError(f"Modelo '{modelo_nome}' nao existe no catalogo.")

    tags = {
        r["liquidacao_id"]: r["tag"]
        for r in (
            await db.execute(
                _SQL_TAGS_VIGENTES, {"tenant_id": tenant_id, "modelo_id": modelo.id}
            )
        ).mappings()
    }
    n_fraude = sum(1 for t in tags.values() if t == "FRAUDE")
    if n_fraude < _MIN_POSITIVOS:
        raise ValueError(
            f"Rotulos insuficientes para treinar: {n_fraude} liquidacoes marcadas "
            f"como fraude (minimo {_MIN_POSITIVOS}). Homologue candidatos na tela "
            "de curadoria antes de treinar."
        )

    todas = await montar_features(db, tenant_id)
    corte_janela = datetime.now(UTC) - timedelta(days=janela_dias)
    universo = [r for r in todas if r.data_evento and r.data_evento >= corte_janela]

    positivas = [r for r in universo if tags.get(r.liquidacao_id) == "FRAUDE"]
    negativas_tag = [r for r in universo if tags.get(r.liquidacao_id) == "OK"]
    sem_tag = [r for r in universo if r.liquidacao_id not in tags]

    rng = random.Random(_SEED)
    n_amostra_neg = max(0, min(len(sem_tag), len(positivas) * _MAX_NEG_POR_POS - len(negativas_tag)))
    negativas_amostra = rng.sample(sem_tag, n_amostra_neg) if n_amostra_neg else []

    conjunto = (
        [(r, 1) for r in positivas]
        + [(r, 0) for r in negativas_tag]
        + [(r, 0) for r in negativas_amostra]
    )
    if len({y for _, y in conjunto}) < 2:
        raise ValueError("Conjunto de treino sem as duas classes.")

    # Out-of-time: corta pelo tempo, nunca aleatorio.
    corte_oot = max(r.data_evento for r, _ in conjunto) - timedelta(days=oot_dias)
    treino = [(r, y) for r, y in conjunto if r.data_evento < corte_oot]
    teste = [(r, y) for r, y in conjunto if r.data_evento >= corte_oot]
    if len({y for _, y in treino}) < 2:
        raise ValueError(
            "Janela de treino (pre-OOT) sem as duas classes — rotule casos mais "
            "antigos ou reduza oot_dias."
        )

    import numpy as np
    from sklearn.linear_model import LogisticRegression

    x_treino = np.array(_sigmoid_inputs([r for r, _ in treino], FEATURE_NAMES))
    y_treino = [y for _, y in treino]
    medias = x_treino.mean(axis=0)
    desvios = x_treino.std(axis=0)
    desvios[desvios == 0] = 1.0
    xs = (x_treino - medias) / desvios

    clf = LogisticRegression(class_weight="balanced", max_iter=2000)
    clf.fit(xs, y_treino)

    def _prob(rows: list[FeatureRow]) -> list[float]:
        x = np.array(_sigmoid_inputs(rows, FEATURE_NAMES))
        return clf.predict_proba((x - medias) / desvios)[:, 1].tolist()

    y_teste = [y for _, y in teste]
    p_teste = _prob([r for r, _ in teste]) if teste else []
    gini, ks = _gini_ks(y_teste, p_teste)
    p_at_20 = _precision_at_k(y_teste, p_teste)

    coeficientes = {
        "intercept": round(float(clf.intercept_[0]), 6),
        "features": {
            nome: {
                "coef": round(float(c), 6),
                "media": round(float(m), 6),
                "desvio": round(float(d), 6),
            }
            for nome, c, m, d in zip(
                FEATURE_NAMES, clf.coef_[0], medias, desvios, strict=True
            )
        },
        "engine": "sklearn.LogisticRegression(class_weight=balanced)",
    }
    metrics = {
        "gini_oot": gini,
        "ks_oot": ks,
        "precision_at_20_oot": p_at_20,
        "n_treino": len(treino),
        "n_teste": len(teste),
        "n_positivos_teste": sum(y_teste),
        "corte_oot": corte_oot.isoformat(),
        "negativos_presumidos_amostrados": len(negativas_amostra),
    }

    versao_atual = (
        await db.execute(
            select(DeteccaoModeloVersao.versao)
            .where(
                DeteccaoModeloVersao.tenant_id == tenant_id,
                DeteccaoModeloVersao.modelo_id == modelo.id,
            )
            .order_by(DeteccaoModeloVersao.versao.desc())
            .limit(1)
        )
    ).scalar_one_or_none() or 0

    versao = DeteccaoModeloVersao(
        tenant_id=tenant_id,
        modelo_id=modelo.id,
        versao=versao_atual + 1,
        coeficientes=coeficientes,
        metrics=metrics,
        n_amostras=len(conjunto),
        n_positivos=len(positivas),
        trained_by=trained_by,
        notas=(
            f"Treino com {len(positivas)} positivas homologadas, "
            f"{len(negativas_tag)} ok homologadas e {len(negativas_amostra)} "
            "negativas presumidas (amostra de nao-marcadas). Versao nasce INATIVA."
        ),
    )
    db.add(versao)
    await db.flush()

    db.add(
        DecisionLog(
            tenant_id=tenant_id,
            decision_type=DecisionType.CALCULATION,
            inputs_ref={
                "modelo": modelo_nome,
                "janela_dias": janela_dias,
                "oot_dias": oot_dias,
                "n_tags": len(tags),
            },
            rule_or_model=modelo_nome,
            rule_or_model_version=f"{modelo_nome}@v{versao.versao}",
            output={"metrics": metrics, "n_features": len(FEATURE_NAMES)},
            explanation=(
                f"treino do modelo {modelo_nome} v{versao.versao}: "
                f"gini_oot={gini} ks_oot={ks} precision@20={p_at_20}"
            ),
            triggered_by=triggered_by,
        )
    )

    logger.info(
        "deteccao_treino: %s v%d gini_oot=%s ks=%s", modelo_nome, versao.versao, gini, ks
    )
    return {
        "modelo": modelo_nome,
        "versao": versao.versao,
        "versao_id": str(versao.id),
        "metrics": metrics,
        "n_positivos": len(positivas),
        "ativa": False,
    }
