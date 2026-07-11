"""Raio-X do cedente: dossie profundo do perfil de liquidacao (rating v2).

Agrega, para UM cedente, o que a tela de detalhamento precisa:
    - header: a linha de rollup do rating (grade, score, watchlist, cobertura)
    - filme: serie MENSAL reconstruida dos eventos (o "filme, nao a foto") —
      volume liquidado, % via boleto, nº criticos, nº eventos por mes;
    - sinais: breakdown dos sinais acesos com a definicao do catalogo;
    - agencias: onde o dinheiro cai (banco+agencia -> endereco/cidade Bacen),
      com flag de conta-do-cedente e fora-da-praca-do-sacado.

O grao TITULO (tabela central) e a curadoria inline reusam a listagem de
curadoria (listar_liquidacoes com cedente_documento_exato) e o POST de tag.

Reconstrucao do filme = lente da formula ATUAL sobre cada mes (nao ha
snapshot mensal persistido ainda; decisao 2026-07-11 — suficiente para
analise, persistir quando decisoes de risco montarem no rating).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# (DeteccaoSinal lido via SQL cru — SAEnum severidade le pelo NOME)
from app.modules.risco.models.rating import RatingLiquidacao

# Serie mensal (12m): 1 linha por mes com os indicadores que contam o filme.
_SQL_FILME = text("""
SELECT to_char(date_trunc('month', l.data_evento), 'YYYY-MM') AS competencia,
       count(*) AS n_eventos,
       sum(coalesce(l.valor_pago, l.valor_titulo, 0)) AS valor,
       count(*) FILTER (WHERE l.canal = 'bancaria') AS n_bancaria,
       sum(coalesce(l.valor_pago, l.valor_titulo, 0))
         FILTER (WHERE l.canal = 'bancaria') AS valor_bancaria,
       count(*) FILTER (
           WHERE coalesce((ds.features->>'match_agencia_conta_cedente')::float, 0) >= 0.5
             AND coalesce((ds.features->>'cidade_pgto_neq_sacado')::float, 0) >= 0.5
       ) AS n_prc01,
       count(*) FILTER (WHERE ds.regra_dura IS TRUE) AS n_cnv90
FROM wh_liquidacao l
JOIN wh_operacao o
    ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
LEFT JOIN deteccao_score ds
    ON ds.liquidacao_id = l.id AND ds.tenant_id = l.tenant_id
WHERE l.tenant_id = :tenant_id
  AND o.cedente_documento = :cedente
  AND l.canal IN ('bancaria', 'baixa_manual')
  AND l.data_evento >= date_trunc('month', now()) - interval '11 months'
GROUP BY 1
ORDER BY 1
""")

# Agencias pagadoras do cedente (via CNAB titulo_id -> ref_bacen consolidada).
_SQL_AGENCIAS = text("""
SELECT be.banco_pagador, be.agencia_pagadora,
       ra.nome_agencia, ra.municipio, ra.uf, ra.endereco, ra.bairro,
       ra.primeira_competencia, ra.ultima_competencia, ra.ativa,
       count(*) AS n,
       sum(coalesce(l.valor_pago, l.valor_titulo, 0)) AS valor,
       max(be.data_credito) AS ultimo_credito,
       bool_or(cc.tem_conta) AS conta_do_cedente
FROM wh_liquidacao l
JOIN wh_operacao o
    ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
JOIN wh_titulo t
    ON t.tenant_id = l.tenant_id AND t.titulo_id = l.titulo_id
JOIN LATERAL (
    SELECT be.banco_pagador, be.agencia_pagadora, be.data_credito
    FROM wh_boleto_evento be
    WHERE be.tenant_id = l.tenant_id AND be.titulo_id = l.titulo_id
      AND be.data_credito IS NOT NULL
    ORDER BY be.data_credito DESC LIMIT 1
) be ON true
LEFT JOIN ref_bacen_agencia ra
    ON ra.banco_compe = lpad(be.banco_pagador, 3, '0')
   AND ra.agencia_codigo = lpad(be.agencia_pagadora, 5, '0')
LEFT JOIN LATERAL (
    SELECT true AS tem_conta
    FROM wh_conta_bancaria cb
    WHERE cb.tenant_id = l.tenant_id
      AND left(cb.entidade_documento, 8) = left(o.cedente_documento, 8)
      AND cb.banco_codigo = lpad(be.banco_pagador, 3, '0')
      AND lpad(cb.agencia_codigo, 5, '0') = lpad(be.agencia_pagadora, 5, '0')
    LIMIT 1
) cc ON true
WHERE l.tenant_id = :tenant_id
  AND o.cedente_documento = :cedente
  AND l.canal = 'bancaria'
  AND l.data_evento >= now() - interval '365 days'
GROUP BY be.banco_pagador, be.agencia_pagadora, ra.nome_agencia, ra.municipio,
         ra.uf, ra.endereco, ra.bairro, ra.primeira_competencia,
         ra.ultima_competencia, ra.ativa
ORDER BY valor DESC NULLS LAST
""")


async def raio_x(
    db: AsyncSession, tenant_id: UUID, cedente_documento: str
) -> dict[str, Any] | None:
    """Dossie do cedente. None se o cedente nao tem rating calculado."""
    header = (
        await db.execute(
            select(RatingLiquidacao).where(
                RatingLiquidacao.tenant_id == tenant_id,
                RatingLiquidacao.cedente_documento == cedente_documento,
                RatingLiquidacao.sacado_documento.is_(None),
            )
        )
    ).scalar_one_or_none()
    if header is None:
        return None

    p = {"tenant_id": tenant_id, "cedente": cedente_documento}
    filme = [
        {
            "competencia": r["competencia"],
            "n_eventos": int(r["n_eventos"]),
            "valor": float(r["valor"] or 0),
            "via_boleto": (
                float(r["valor_bancaria"] or 0) / float(r["valor"])
                if r["valor"]
                else 0.0
            ),
            "n_prc01": int(r["n_prc01"]),
            "n_cnv90": int(r["n_cnv90"]),
            "n_critico": int(r["n_prc01"]) + int(r["n_cnv90"]),
        }
        for r in (await db.execute(_SQL_FILME, p)).mappings()
    ]

    agencias = [
        {
            "banco": r["banco_pagador"],
            "agencia": r["agencia_pagadora"],
            "nome": r["nome_agencia"],
            "cidade": r["municipio"],
            "uf": r["uf"],
            "endereco": r["endereco"],
            "bairro": r["bairro"],
            "ativa": r["ativa"],
            "vigencia": (
                f"{r['primeira_competencia']}-{r['ultima_competencia']}"
                if r["primeira_competencia"]
                else None
            ),
            "n": int(r["n"]),
            "valor": float(r["valor"] or 0),
            "conta_do_cedente": bool(r["conta_do_cedente"]),
            "ultimo_credito": r["ultimo_credito"],
        }
        for r in (await db.execute(_SQL_AGENCIAS, p)).mappings()
    ]

    # Sinais acesos (do rollup) + definicao do catalogo, mais grave primeiro.
    # SQL cru: a coluna severidade e SAEnum que le pelo NOME (gotcha) — os
    # valores no banco sao minusculos; ler como texto evita a coercao.
    sinais_ct = header.componentes.get("sinais", {}) if header.componentes else {}
    catalogo = {
        r["codigo"]: r
        for r in (
            await db.execute(
                text("SELECT codigo, nome, definicao, severidade FROM deteccao_sinal")
            )
        ).mappings()
    }
    _sev = {"critica": 0, "pendente": 1, "alta": 2, "media": 3, "baixa": 4}
    sinais = sorted(
        (
            {
                "codigo": c,
                "n": n,
                "nome": catalogo[c]["nome"] if c in catalogo else c,
                "definicao": catalogo[c]["definicao"] if c in catalogo else None,
                "severidade": catalogo[c]["severidade"] if c in catalogo else "?",
            }
            for c, n in sinais_ct.items()
        ),
        key=lambda x: (_sev.get(x["severidade"], 9), -x["n"]),
    )

    comp = header.componentes or {}
    return {
        "cedente_documento": header.cedente_documento,
        "cedente_nome": header.cedente_nome,
        "grade": header.grade,
        "score": float(header.score) if header.score is not None else None,
        "watchlist": bool(comp.get("watchlist")),
        "critico_historico": bool(comp.get("critico_historico")),
        "dias_ultimo_critico": comp.get("dias_ultimo_critico"),
        "pendencias_curadoria": int(comp.get("pendencias_curadoria", 0)),
        "cobertura": float(header.cobertura),
        "n_eventos_score": header.n_eventos_score,
        "n_desfechos": header.n_desfechos,
        "valor_desfechos": float(header.valor_desfechos),
        "formula_version": header.formula_version,
        "filme": filme,
        "agencias": agencias,
        "sinais": sinais,
    }
