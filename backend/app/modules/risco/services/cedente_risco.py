"""Consolidation of event scores into per-cedente indicator subscores + composite.

Runs after every scoring pass (job or "Pontuar agora"): aggregates
`deteccao_score` per (cedente, indicator), snapshots the subscore into
`cedente_risco_snapshot` (time series) and writes the COMPOSITE row from the
active `cedente_risco_composicao` weights.

Subscore v1 of the liquidation indicator (explainable by design, §14.3):
    base   = 100 * (R$ of events with score >= 0.7 / R$ evaluated)
    floor  = 70 when the cedente has at least one padrao critico (a
             deterministic hit is never diluted by portfolio size)
    subscore = max(base, floor)   [0..100]
The components of the arithmetic are stored in `componentes` so the panel
can always answer "why 73?".
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risco.models import DeteccaoModelo
from app.modules.risco.models.cedente_risco import (
    CedenteRiscoComposicao,
    CedenteRiscoSnapshot,
)
from app.shared.audit_log.decision_log import DecisionLog, DecisionType

logger = logging.getLogger(__name__)

_SCORE_ALTO = 0.7
_PISO_CRITICO = 70.0

_SQL_AGREGADO = text("""
SELECT
    ds.modelo_id,
    o.cedente_documento,
    max(o.cedente_nome) AS cedente_nome,
    count(*) AS n_eventos,
    count(*) FILTER (WHERE ds.regra_dura) AS n_criticos,
    count(*) FILTER (WHERE ds.score >= :score_alto) AS n_alto_risco,
    coalesce(sum(coalesce(l.valor_pago, l.valor_titulo)), 0) AS valor_avaliado,
    coalesce(sum(coalesce(l.valor_pago, l.valor_titulo))
        FILTER (WHERE ds.score >= :score_alto OR ds.regra_dura), 0) AS valor_em_risco
FROM deteccao_score ds
JOIN wh_liquidacao l ON l.id = ds.liquidacao_id
JOIN wh_operacao o
    ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
WHERE ds.tenant_id = :tenant_id
  AND o.cedente_documento IS NOT NULL
GROUP BY ds.modelo_id, o.cedente_documento
""")


def _doc14(documento: str | None) -> str | None:
    if not documento:
        return None
    d = "".join(c for c in documento if c.isdigit())
    return (d[-14:] if len(d) > 14 else d) or None


async def _composicao_ativa(
    db: AsyncSession, tenant_id: UUID
) -> CedenteRiscoComposicao:
    """Active weights (max version); bootstrap v1 = 100% liquidacao_boleto."""
    ativa = (
        await db.execute(
            select(CedenteRiscoComposicao)
            .where(CedenteRiscoComposicao.tenant_id == tenant_id)
            .order_by(CedenteRiscoComposicao.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if ativa is not None:
        return ativa
    ativa = CedenteRiscoComposicao(
        tenant_id=tenant_id,
        version=1,
        pesos={"liquidacao_boleto": 1.0},
        justificativa=(
            "Bootstrap: unico indicador existente. Pesos evoluem conforme "
            "novos indicadores entram no catalogo."
        ),
    )
    db.add(ativa)
    await db.flush()
    return ativa


async def consolidar(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    triggered_by: str = "system:scheduler",
) -> dict[str, Any]:
    """Snapshot per-cedente subscores (per indicator + composite) for today."""
    t0 = time.monotonic()
    data_ref = datetime.now(UTC).date()

    modelos = {
        m.id: m.nome
        for m in (await db.execute(select(DeteccaoModelo))).scalars()
    }
    composicao = await _composicao_ativa(db, tenant_id)

    agregados = (
        await db.execute(_SQL_AGREGADO, {"tenant_id": tenant_id, "score_alto": _SCORE_ALTO})
    ).mappings().all()

    linhas: list[dict[str, Any]] = []
    # (cedente_doc) -> {modelo_nome: subscore} para compor no final
    por_cedente: dict[str, dict[str, float]] = {}
    nomes: dict[str, str | None] = {}

    for a in agregados:
        doc = _doc14(a["cedente_documento"])
        if not doc:
            continue
        valor_avaliado = float(a["valor_avaliado"] or 0)
        valor_em_risco = float(a["valor_em_risco"] or 0)
        base = 100.0 * (valor_em_risco / valor_avaliado) if valor_avaliado > 0 else 0.0
        piso = _PISO_CRITICO if int(a["n_criticos"] or 0) > 0 else 0.0
        subscore = round(min(100.0, max(base, piso)), 2)

        modelo_nome = modelos.get(a["modelo_id"], str(a["modelo_id"]))
        por_cedente.setdefault(doc, {})[modelo_nome] = subscore
        nomes[doc] = a["cedente_nome"]

        linhas.append(
            {
                "tenant_id": tenant_id,
                "cedente_documento": doc,
                "cedente_nome": a["cedente_nome"],
                "modelo_id": a["modelo_id"],
                "data_ref": data_ref,
                "subscore": subscore,
                "valor_avaliado": a["valor_avaliado"],
                "valor_em_risco": a["valor_em_risco"],
                "n_eventos": a["n_eventos"],
                "n_criticos": a["n_criticos"],
                "n_alto_risco": a["n_alto_risco"],
                "componentes": {
                    "formula": "max(100*valor_em_risco/valor_avaliado, piso_critico)",
                    "base_pct_valor": round(base, 2),
                    "piso_critico_aplicado": piso > 0 and base < piso,
                },
            }
        )

    # Linha do COMPOSTO por cedente (media ponderada pelos pesos ativos).
    for doc, subscores in por_cedente.items():
        peso_total = sum(
            float(composicao.pesos.get(nome, 0.0)) for nome in subscores
        )
        if peso_total <= 0:
            continue
        composto = round(
            sum(
                s * float(composicao.pesos.get(nome, 0.0))
                for nome, s in subscores.items()
            )
            / peso_total,
            2,
        )
        linhas.append(
            {
                "tenant_id": tenant_id,
                "cedente_documento": doc,
                "cedente_nome": nomes.get(doc),
                "modelo_id": None,
                "data_ref": data_ref,
                "subscore": composto,
                "valor_avaliado": None,
                "valor_em_risco": None,
                "n_eventos": None,
                "n_criticos": None,
                "n_alto_risco": None,
                "componentes": {
                    "composicao_version": composicao.version,
                    "pesos": composicao.pesos,
                    "subscores": subscores,
                },
            }
        )

    for i in range(0, len(linhas), 2000):
        chunk = linhas[i : i + 2000]
        stmt = pg_insert(CedenteRiscoSnapshot).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_cedente_risco_snapshot",
            set_={
                "cedente_nome": stmt.excluded.cedente_nome,
                "subscore": stmt.excluded.subscore,
                "valor_avaliado": stmt.excluded.valor_avaliado,
                "valor_em_risco": stmt.excluded.valor_em_risco,
                "n_eventos": stmt.excluded.n_eventos,
                "n_criticos": stmt.excluded.n_criticos,
                "n_alto_risco": stmt.excluded.n_alto_risco,
                "componentes": stmt.excluded.componentes,
                "computed_at": stmt.excluded.computed_at,
            },
        )
        await db.execute(stmt)

    summary = {
        "data_ref": data_ref.isoformat(),
        "cedentes": len(por_cedente),
        "linhas": len(linhas),
        "composicao_version": composicao.version,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }
    db.add(
        DecisionLog(
            tenant_id=tenant_id,
            decision_type=DecisionType.CALCULATION,
            inputs_ref={"data_ref": data_ref.isoformat()},
            rule_or_model="cedente_risco",
            rule_or_model_version=f"composicao@v{composicao.version}",
            output=summary,
            explanation=(
                f"consolidacao de risco por cedente: {len(por_cedente)} cedentes, "
                f"composicao v{composicao.version}"
            ),
            triggered_by=triggered_by,
        )
    )
    logger.info("cedente_risco: %s", summary)
    return summary


# Carteira ATUAL por cedente (posicao vendor-computed do Bitfin, wh_posicao_
# cedente): exposicao em aberto — natureza diferente do valor liquidado
# suspeito, que e retrospectivo. Documento normalizado para casar com o
# cedente_documento (14 digitos) do snapshot.
_SQL_CARTEIRA = text("""
SELECT e.documento, sum(p.risco_total_valor) AS carteira_atual
FROM wh_posicao_cedente p
JOIN wh_entidade e ON e.id = p.entidade_id AND e.tenant_id = p.tenant_id
WHERE p.tenant_id = :tenant_id AND p.risco_total_valor IS NOT NULL
GROUP BY e.documento
""")


_SQL_PAINEL = text("""
WITH ultimo AS (
    SELECT DISTINCT ON (cedente_documento, modelo_id)
        cedente_documento, cedente_nome, modelo_id, data_ref, subscore,
        valor_avaliado, valor_em_risco, n_eventos, n_criticos, n_alto_risco,
        componentes
    FROM cedente_risco_snapshot
    WHERE tenant_id = :tenant_id
    ORDER BY cedente_documento, modelo_id, data_ref DESC
),
anterior AS (
    -- snapshot composto mais antigo dentro da janela de tendencia
    SELECT DISTINCT ON (cedente_documento)
        cedente_documento, subscore AS subscore_anterior, data_ref
    FROM cedente_risco_snapshot
    WHERE tenant_id = :tenant_id AND modelo_id IS NULL
      AND data_ref >= (current_date - CAST(:tendencia_dias AS integer))
    ORDER BY cedente_documento, data_ref ASC
)
SELECT u.*, a.subscore_anterior
FROM ultimo u
LEFT JOIN anterior a ON a.cedente_documento = u.cedente_documento
""")


async def painel(
    db: AsyncSession, tenant_id: UUID, *, tendencia_dias: int = 30
) -> list[dict[str, Any]]:
    """Latest snapshot per cedente: composite + per-indicator + trend."""
    modelos = {
        m.id: m.nome for m in (await db.execute(select(DeteccaoModelo))).scalars()
    }
    rows = (
        await db.execute(
            _SQL_PAINEL, {"tenant_id": tenant_id, "tendencia_dias": tendencia_dias}
        )
    ).mappings().all()

    carteira_por_doc: dict[str, float] = {}
    for r in (await db.execute(_SQL_CARTEIRA, {"tenant_id": tenant_id})).mappings():
        doc = _doc14(r["documento"])
        if doc:
            carteira_por_doc[doc] = carteira_por_doc.get(doc, 0.0) + float(
                r["carteira_atual"] or 0
            )

    por_cedente: dict[str, dict[str, Any]] = {}
    for r in rows:
        doc = r["cedente_documento"]
        c = por_cedente.setdefault(
            doc,
            {
                "cedente_documento": doc,
                "cedente_nome": r["cedente_nome"],
                "risco": None,
                "tendencia": None,
                "data_ref": None,
                "indicadores": [],
                "valor_avaliado": 0.0,
                "valor_em_risco": 0.0,
                "carteira_atual": carteira_por_doc.get(doc),
                "n_criticos": 0,
                "n_alto_risco": 0,
                "n_eventos": 0,
            },
        )
        if r["modelo_id"] is None:
            c["risco"] = float(r["subscore"])
            c["data_ref"] = r["data_ref"]
            c["componentes"] = r["componentes"]
            if r["subscore_anterior"] is not None:
                c["tendencia"] = round(
                    float(r["subscore"]) - float(r["subscore_anterior"]), 2
                )
        else:
            c["indicadores"].append(
                {
                    "indicador": modelos.get(r["modelo_id"], "?"),
                    "subscore": float(r["subscore"]),
                    "valor_avaliado": float(r["valor_avaliado"] or 0),
                    "valor_em_risco": float(r["valor_em_risco"] or 0),
                    "n_eventos": r["n_eventos"],
                    "n_criticos": r["n_criticos"],
                    "n_alto_risco": r["n_alto_risco"],
                    "componentes": r["componentes"],
                }
            )
            c["valor_avaliado"] += float(r["valor_avaliado"] or 0)
            c["valor_em_risco"] += float(r["valor_em_risco"] or 0)
            c["n_criticos"] += int(r["n_criticos"] or 0)
            c["n_alto_risco"] += int(r["n_alto_risco"] or 0)
            c["n_eventos"] += int(r["n_eventos"] or 0)

    saida = [c for c in por_cedente.values() if c["risco"] is not None]
    saida.sort(key=lambda c: (-(c["risco"] or 0), -c["valor_em_risco"]))
    return saida
