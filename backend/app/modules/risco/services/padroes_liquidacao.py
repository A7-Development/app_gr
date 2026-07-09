"""Perfil DETERMINISTICO das liquidacoes (painel /risco/padroes-liquidacao).

Diferente de `cedente_risco` (que consome o SCORE do modelo), este servico e
100% factual: le apenas os fatos ja materializados em `deteccao_score.features`
(o vetor de entrada, snapshot por liquidacao) + `regra_dura`/`regra_dura_motivo`
(as conclusoes DETERMINISTICAS, fora do modelo). O `score` do modelo e
deliberadamente IGNORADO aqui.

Duas camadas por cedente, escopadas por uma janela temporal sobre
`wh_liquidacao.data_evento` (a data do evento economico, nao a de ingestao):
  - Fatos    -> contagem de ocorrencias por sinal (match conta/cidade, fora da
                praca, agencia compartilhada, anel entre cedentes, contrato
                aberto, ...) + mix de canal (banco na praca / cooperativa / IP /
                sem praca / nao resolvido / baixa manual).
  - Alertas  -> `regra_dura` acionada (conta+cidade OU agencia compartilhada por
                >=10 sacados de outras cidades). O cedente em alerta sobe ao topo.

Temporalidade: a janela filtra 100% dos agregados (§7.2); cada metrica traz o
Delta vs a janela anterior de mesmo tamanho (separa cronico de novo); a recencia
(ultima `data_evento` na janela) evita alerta velho parecendo atual.

Silver-only, tenant-scoped. Read puro — nao grava decision_log.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Janela -> dias (None = "tudo", sem limite inferior). Espelha os presets do
# seletor no frontend.
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
# deteccao_score.features (fatos) + regra_dura (alertas) — nunca ds.score.
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
    ) AS n_alerta_anel,
    -- ocorrencias de sinal (contagem de eventos que acionaram)
    count(*) FILTER (
        WHERE coalesce((ds.features->>'match_agencia_conta_cedente')::numeric, 0) >= 0.5
    ) AS match_conta,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'cidade_pgto_eq_cedente')::numeric, 0) >= 0.5
    ) AS match_cidade,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'cidade_pgto_neq_sacado')::numeric, 0) >= 0.5
    ) AS fora_praca,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'agencia_compartilhada')::numeric, 0) > 0
    ) AS ag_compartilhada,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'agencia_compartilhada_cedentes')::numeric, 0) > 0
    ) AS anel_cedentes,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'contrato_aberto')::numeric, 0) >= 0.5
    ) AS contrato_aberto,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'baixa_manual_produto_anomala')::numeric, 0) >= 0.5
    ) AS baixa_manual_anomala,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'boleto_nao_esperado_mas_teve')::numeric, 0) >= 0.5
    ) AS boleto_nao_esperado,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'quebra_fingerprint')::numeric, 0) > 0
    ) AS quebra_fingerprint,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'pago_exato_vencimento')::numeric, 0) >= 0.5
    ) AS pago_exato_vencimento,
    -- mix de canal (o banco na praca e derivado: n_liq - os demais)
    count(*) FILTER (
        WHERE coalesce((ds.features->>'canal_cooperativa')::numeric, 0) >= 0.5
    ) AS canal_cooperativa,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'canal_ip')::numeric, 0) >= 0.5
    ) AS canal_ip,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'canal_sem_praca')::numeric, 0) >= 0.5
    ) AS canal_sem_praca,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'canal_nao_resolvido')::numeric, 0) >= 0.5
    ) AS canal_nao_resolvido,
    count(*) FILTER (
        WHERE coalesce((ds.features->>'canal_baixa_manual')::numeric, 0) >= 0.5
    ) AS canal_baixa_manual
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

# Colunas de sinal (contagem de ocorrencia) na ordem canonica da matriz.
_SINAIS = (
    "match_conta",
    "match_cidade",
    "fora_praca",
    "ag_compartilhada",
    "anel_cedentes",
    "contrato_aberto",
    "baixa_manual_anomala",
    "boleto_nao_esperado",
    "quebra_fingerprint",
    "pago_exato_vencimento",
)


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


def _canal_mix(r: dict[str, Any]) -> dict[str, int]:
    """Mix de canal por cedente; banco_praca = resto (nenhum flag acionado)."""
    coop = int(r["canal_cooperativa"] or 0)
    ip = int(r["canal_ip"] or 0)
    sem_praca = int(r["canal_sem_praca"] or 0)
    nao_resolvido = int(r["canal_nao_resolvido"] or 0)
    baixa_manual = int(r["canal_baixa_manual"] or 0)
    banco_praca = max(
        0, int(r["n_liq"] or 0) - (coop + ip + sem_praca + nao_resolvido + baixa_manual)
    )
    return {
        "banco_praca": banco_praca,
        "cooperativa": coop,
        "ip": ip,
        "sem_praca": sem_praca,
        "nao_resolvido": nao_resolvido,
        "baixa_manual": baixa_manual,
    }


async def perfil(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    janela: str = JANELA_PADRAO,
) -> dict[str, Any]:
    """Perfil deterministico das liquidacoes na janela + Delta vs anterior.

    Retorna {janela, inicio, fim, kpis, cedentes[]}. `cedentes` ordenado por
    alerta (regra dura) desc, depois valor desc — cedente em alerta no topo.
    """
    dias = JANELAS.get(janela, JANELAS[JANELA_PADRAO])
    fim = datetime.now(UTC)
    inicio = fim - timedelta(days=dias) if dias is not None else None

    atual = await _agregar(db, tenant_id, inicio, fim)

    # Janela anterior de mesmo tamanho (para o Delta). "tudo" nao tem anterior.
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
                "n_alerta_anel": int(r["n_alerta_anel"] or 0),
                "sinais": {s: int(r[s] or 0) for s in _SINAIS},
                "canal": _canal_mix(r),
                # Delta vs janela anterior (None quando "tudo" ou cedente novo).
                "delta_alerta": (
                    n_alerta - int(prev["n_alerta"] or 0) if prev is not None else None
                ),
                "delta_liq": (
                    n_liq - int(prev["n_liq"] or 0) if prev is not None else None
                ),
                "cedente_novo": dias is not None and prev is None,
            }
        )

    cedentes.sort(key=lambda c: (-c["n_alerta"], -c["valor"]))

    # KPIs da janela (somados sobre os cedentes exibidos — reconcilia §14.6).
    n_liq_total = sum(c["n_liq"] for c in cedentes)
    valor_total = sum(c["valor"] for c in cedentes)
    n_alerta_total = sum(c["n_alerta"] for c in cedentes)
    banco_praca_total = sum(c["canal"]["banco_praca"] for c in cedentes)
    baixa_manual_total = sum(c["canal"]["baixa_manual"] for c in cedentes)
    fora_praca_total = sum(c["sinais"]["fora_praca"] for c in cedentes)
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
            "pct_banco_praca": _pct(banco_praca_total),
            "pct_baixa_manual": _pct(baixa_manual_total),
            "pct_fora_praca": _pct(fora_praca_total),
        },
        "cedentes": cedentes,
    }
