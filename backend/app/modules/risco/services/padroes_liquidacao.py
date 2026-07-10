"""Perfil DETERMINISTICO das liquidacoes (painel /risco/padroes-liquidacao).

Diferente de `cedente_risco` (que consome o SCORE do modelo), este servico e
100% factual: le apenas os fatos ja materializados em `deteccao_score.features`
(o vetor de entrada + descritores de segmento) + `regra_dura`/`regra_dura_motivo`
(as conclusoes DETERMINISTICAS). O `score` do modelo e IGNORADO aqui.

Conjunto de indicadores (travado com Ricardo 2026-07-09), todos INTRINSECOS ao
cedente, escopados por uma janela sobre `wh_liquidacao.data_evento`:

  Red flags de captura & descolamento:
    - Conta do cedente  -> pagamento bate com o cadastro de conta do cedente
                           (o MAIOR red flag; coluna fixa, peso maximo).
    - Praca do cedente  -> pago na cidade do cedente E FORA da do sacado
                           (CONDICIONADO: mesma praca = sem forca, zera).
    - Fora da praca do sacado -> pago em cidade != do sacado.
    - Fora do padrao do sacado -> sacado pagou fora do banco/agencia habitual.
    - Agencia multi-sacado -> muitos sacados na mesma agencia, CONDICIONADO a
                              cidades divergentes (concentracao regional inocente
                              nao conta).

  Canal por segmento oficial Bacen (descritor de para onde foi o pagamento):
    - Banco digital / Cooperativa / IP / SCD / Financeira.

  Alerta (regra dura): conta+cidade OU agencia multi-cedente (ex-"anel").

Temporalidade: a janela filtra 100% dos agregados (§7.2); cada metrica traz o
Delta vs a janela anterior; a recencia (ultima `data_evento`) evita alerta velho
parecendo atual. Silver-only, tenant-scoped, read puro.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Janela -> dias (None = "tudo", sem limite inferior).
JANELAS: dict[str, int | None] = {
    "7d": 7,
    "15d": 15,
    "30d": 30,
    "90d": 90,
    "12m": 365,
    "tudo": None,
}
JANELA_PADRAO = "30d"

# Agregado deterministico por cedente numa janela [inicio, fim). Le SO
# deteccao_score.features (fatos + segmento) + regra_dura (alertas).
_SQL_PERFIL = text("""
SELECT
    o.cedente_documento,
    max(o.cedente_nome) AS cedente_nome,
    count(*) AS n_liq,
    coalesce(sum(coalesce(l.valor_pago, l.valor_titulo)), 0) AS valor,
    max(l.data_evento) AS ultima_liq,
    -- alertas deterministicos (regra dura), separados por regra
    count(*) FILTER (WHERE ds.regra_dura) AS n_alerta,
    count(*) FILTER (
        WHERE ds.regra_dura AND ds.regra_dura_motivo ILIKE 'sacado de outra cidade%'
    ) AS n_alerta_conta,
    count(*) FILTER (
        WHERE ds.regra_dura AND ds.regra_dura_motivo ILIKE 'agencia compartilhada%'
    ) AS n_alerta_multicedente,
    -- red flags (intrinsecos ao cedente)
    count(*) FILTER (
        WHERE coalesce((ds.features->>'match_agencia_conta_cedente')::numeric, 0) >= 0.5
    ) AS conta_cedente,
    -- praca do cedente CONDICIONADA: pago na cidade do cedente E fora da do sacado
    count(*) FILTER (
        WHERE coalesce((ds.features->>'cidade_pgto_eq_cedente')::numeric, 0) >= 0.5
          AND coalesce((ds.features->>'cidade_pgto_neq_sacado')::numeric, 0) >= 0.5
    ) AS praca_cedente,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'cidade_pgto_neq_sacado')::numeric, 0) >= 0.5
    ) AS fora_praca,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'quebra_fingerprint')::numeric, 0) > 0
    ) AS fora_padrao,
    -- agencia multi-sacado CONDICIONADA a cidades divergentes
    count(*) FILTER (
        WHERE coalesce((ds.features->>'agencia_compartilhada')::numeric, 0) > 0
          AND coalesce((ds.features->>'cidade_pgto_neq_sacado')::numeric, 0) >= 0.5
    ) AS multi_sacado,
    -- canal por segmento oficial Bacen (mutuamente exclusivos)
    count(*) FILTER (
        WHERE coalesce((ds.features->>'seg_banco_digital')::numeric, 0) >= 0.5
    ) AS seg_banco_digital,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'seg_cooperativa')::numeric, 0) >= 0.5
    ) AS seg_cooperativa,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'seg_ip')::numeric, 0) >= 0.5
    ) AS seg_ip,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'seg_scd')::numeric, 0) >= 0.5
    ) AS seg_scd,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'seg_financeira')::numeric, 0) >= 0.5
    ) AS seg_financeira
FROM deteccao_score ds
JOIN wh_liquidacao l ON l.id = ds.liquidacao_id
JOIN wh_operacao o
    ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
WHERE ds.tenant_id = :tenant_id
  AND o.cedente_documento IS NOT NULL
  AND (CAST(:inicio AS timestamptz) IS NULL OR l.data_evento >= :inicio)
  AND l.data_evento < :fim
GROUP BY o.cedente_documento
""")

# Red flags (contagem de ocorrencia) — ordem canonica da matriz.
_SINAIS = (
    "conta_cedente",
    "praca_cedente",
    "fora_praca",
    "fora_padrao",
    "multi_sacado",
)
# Canal por segmento oficial Bacen.
_SEGMENTOS = ("banco_digital", "cooperativa", "ip", "scd", "financeira")


async def _agregar(
    db: AsyncSession, tenant_id: UUID, inicio: datetime | None, fim: datetime
) -> dict[str, dict[str, Any]]:
    """Roda o agregado numa janela; retorna {cedente_documento: row}."""
    rows = (
        await db.execute(
            _SQL_PERFIL, {"tenant_id": tenant_id, "inicio": inicio, "fim": fim}
        )
    ).mappings().all()
    return {r["cedente_documento"]: dict(r) for r in rows}


async def perfil(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    janela: str = JANELA_PADRAO,
) -> dict[str, Any]:
    """Perfil deterministico das liquidacoes na janela + Delta vs anterior.

    Retorna {janela, inicio, fim, kpis, cedentes[]}. `cedentes` ordenado por
    alerta desc, depois Conta do cedente desc, depois valor desc — cedente em
    alerta (e captura direta) no topo.
    """
    dias = JANELAS.get(janela, JANELAS[JANELA_PADRAO])
    fim = datetime.now(UTC)
    inicio = fim - timedelta(days=dias) if dias is not None else None

    atual = await _agregar(db, tenant_id, inicio, fim)

    anterior: dict[str, dict[str, Any]] = {}
    if dias is not None and inicio is not None:
        anterior = await _agregar(
            db, tenant_id, inicio - timedelta(days=dias), inicio
        )

    cedentes: list[dict[str, Any]] = []
    for doc, r in atual.items():
        prev = anterior.get(doc)
        n_alerta = int(r["n_alerta"] or 0)
        n_liq = int(r["n_liq"] or 0)
        cedentes.append(
            {
                "cedente_documento": doc,
                "cedente_nome": r["cedente_nome"],
                "n_liq": n_liq,
                "valor": float(r["valor"] or 0),
                "ultima_liq": r["ultima_liq"],
                "n_alerta": n_alerta,
                "n_alerta_conta": int(r["n_alerta_conta"] or 0),
                "n_alerta_multicedente": int(r["n_alerta_multicedente"] or 0),
                "sinais": {s: int(r[s] or 0) for s in _SINAIS},
                "segmentos": {s: int(r[f"seg_{s}"] or 0) for s in _SEGMENTOS},
                "delta_alerta": (
                    n_alerta - int(prev["n_alerta"] or 0) if prev is not None else None
                ),
                "delta_liq": (
                    n_liq - int(prev["n_liq"] or 0) if prev is not None else None
                ),
                "cedente_novo": dias is not None and prev is None,
            }
        )

    # Ordena: alerta desc -> Conta do cedente desc (o maior red flag) -> valor.
    cedentes.sort(
        key=lambda c: (-c["n_alerta"], -c["sinais"]["conta_cedente"], -c["valor"])
    )

    # KPIs da janela (somados sobre os cedentes exibidos — reconcilia §14.6).
    n_liq_total = sum(c["n_liq"] for c in cedentes)
    valor_total = sum(c["valor"] for c in cedentes)
    n_alerta_total = sum(c["n_alerta"] for c in cedentes)
    conta_total = sum(c["sinais"]["conta_cedente"] for c in cedentes)
    fora_praca_total = sum(c["sinais"]["fora_praca"] for c in cedentes)
    # Canal de atencao = qualquer segmento != banco tradicional na praca.
    canal_atencao_total = sum(
        sum(c["segmentos"].values()) for c in cedentes
    )
    n_alerta_anterior = (
        sum(int(r["n_alerta"] or 0) for r in anterior.values())
        if anterior
        else None
    )

    def _pct(x: int) -> float:
        return round(100.0 * x / n_liq_total, 1) if n_liq_total else 0.0

    return {
        "janela": janela if janela in JANELAS else JANELA_PADRAO,
        "inicio": inicio.isoformat() if inicio else None,
        "fim": fim.isoformat(),
        "kpis": {
            "valor_total": valor_total,
            "n_liq_total": n_liq_total,
            "n_cedentes": len(cedentes),
            "n_alerta_total": n_alerta_total,
            "n_alerta_anterior": n_alerta_anterior,
            "pct_conta_cedente": _pct(conta_total),
            "pct_fora_praca": _pct(fora_praca_total),
            "pct_canal_atencao": _pct(canal_atencao_total),
        },
        "cedentes": cedentes,
    }
