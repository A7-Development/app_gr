"""get_ficha_cedente — ficha de risco/exposicao de um cedente (silver).

Cruza: cadastro (`wh_entidade`), exposicao atual em estoque
(`wh_estoque_recebivel`, ultimo snapshot), risco de deteccao
(`cedente_risco_snapshot`, mais recente) e rating de liquidacao por par
cedente-sacado (`rating_liquidacao`). Silver-only, tenant-scoped.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission

_TOP_PARES = 5


@register_tool(
    name="get_ficha_cedente",
    description=(
        "Ficha completa de um CEDENTE nos seus dados, pelo CNPJ/CPF: "
        "cadastro (nome, porte, cidade, recuperacao judicial), exposicao "
        "atual na carteira (valor presente, papeis, sacados, por fundo), "
        "sinal de risco do monitoramento de liquidacoes (quando houver) e "
        "rating de liquidacao por sacado (piores pares primeiro). Use apos "
        "resolver o documento com `buscar_entidade` quando o usuario citar "
        "o cedente por nome."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "documento": {
                "type": "string",
                "description": "CNPJ/CPF do cedente (com ou sem pontuacao).",
            }
        },
        "required": ["documento"],
    },
    module=Module.RISCO,
    min_permission=Permission.READ,
    cost_hint="medium",
    cacheable=True,
)
async def get_ficha_cedente(scope: ScopedContext, args: dict[str, Any]) -> str:
    doc = "".join(c for c in str(args.get("documento", "")) if c.isdigit())
    if len(doc) not in (11, 14):
        return json.dumps(
            {"erro": "Documento invalido — informe um CNPJ (14 digitos) ou CPF (11)."},
            ensure_ascii=False,
        )
    params: dict[str, Any] = {"tenant_id": str(scope.tenant_id), "doc": doc}

    cadastro = (
        await scope.db.execute(
            text(
                """
                SELECT nome, tipo_pessoa, porte, cnae_denominacao, localidade,
                       estado, data_constituicao, em_recuperacao_judicial
                FROM wh_entidade
                WHERE tenant_id = :tenant_id
                  AND regexp_replace(documento, '\\D', '', 'g') = :doc
                LIMIT 1
                """
            ),
            params,
        )
    ).mappings().one_or_none()

    exposicao = (
        await scope.db.execute(
            text(
                """
                WITH ultimo AS (
                  SELECT max(data_referencia) AS d FROM wh_estoque_recebivel
                  WHERE tenant_id = :tenant_id
                )
                SELECT e.data_referencia,
                       COALESCE(sum(e.valor_presente), 0) AS valor_presente,
                       COALESCE(sum(e.valor_pdd), 0) AS valor_pdd,
                       count(*) AS n_papeis,
                       count(DISTINCT e.sacado_doc) AS n_sacados
                FROM wh_estoque_recebivel e, ultimo
                WHERE e.tenant_id = :tenant_id
                  AND e.data_referencia = ultimo.d
                  AND regexp_replace(e.cedente_doc, '\\D', '', 'g') = :doc
                GROUP BY e.data_referencia
                """
            ),
            params,
        )
    ).mappings().one_or_none()

    exposicao_por_fundo = []
    if exposicao is not None:
        exposicao_por_fundo = (
            await scope.db.execute(
                text(
                    """
                    SELECT e.fundo_nome,
                           COALESCE(sum(e.valor_presente), 0) AS valor_presente,
                           count(*) AS n_papeis
                    FROM wh_estoque_recebivel e
                    WHERE e.tenant_id = :tenant_id
                      AND e.data_referencia = :data_ref
                      AND regexp_replace(e.cedente_doc, '\\D', '', 'g') = :doc
                    GROUP BY 1 ORDER BY 2 DESC
                    """
                ),
                {**params, "data_ref": exposicao["data_referencia"]},
            )
        ).mappings().all()

    risco = (
        await scope.db.execute(
            text(
                """
                SELECT data_ref, subscore, valor_avaliado, valor_em_risco,
                       n_eventos, n_criticos, n_alto_risco
                FROM cedente_risco_snapshot
                WHERE tenant_id = :tenant_id
                  AND regexp_replace(cedente_documento, '\\D', '', 'g') = :doc
                ORDER BY data_ref DESC LIMIT 1
                """
            ),
            params,
        )
    ).mappings().one_or_none()

    ratings = (
        await scope.db.execute(
            text(
                """
                SELECT sacado_nome, grade, score, tem_critico, n_desfechos,
                       valor_desfechos
                FROM rating_liquidacao
                WHERE tenant_id = :tenant_id
                  AND regexp_replace(cedente_documento, '\\D', '', 'g') = :doc
                ORDER BY score ASC NULLS LAST
                """
            ),
            params,
        )
    ).mappings().all()

    grades: dict[str, int] = {}
    for r in ratings:
        grades[r["grade"]] = grades.get(r["grade"], 0) + 1

    if cadastro is None and exposicao is None and not ratings:
        return json.dumps(
            {
                "erro": (
                    "Nenhum dado interno encontrado para esse documento — nem "
                    "cadastro, nem exposicao, nem historico de liquidacao."
                )
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "documento": doc,
            "cadastro": dict(cadastro) if cadastro else None,
            "exposicao_atual": (
                {
                    **{
                        k: (float(v) if k.startswith("valor") else v)
                        for k, v in dict(exposicao).items()
                    },
                    "por_fundo": [
                        {
                            "fundo": r["fundo_nome"],
                            "valor_presente": float(r["valor_presente"]),
                            "n_papeis": r["n_papeis"],
                        }
                        for r in exposicao_por_fundo
                    ],
                }
                if exposicao
                else None
            ),
            "sinal_risco_liquidacoes": dict(risco) if risco else None,
            "rating_liquidacao": {
                "n_pares_avaliados": len(ratings),
                "por_grade": grades,
                "piores_pares": [
                    {
                        "sacado": r["sacado_nome"],
                        "grade": r["grade"],
                        "score": float(r["score"]) if r["score"] is not None else None,
                        "tem_critico": r["tem_critico"],
                        "n_desfechos": r["n_desfechos"],
                    }
                    for r in ratings[:_TOP_PARES]
                ],
            }
            if ratings
            else None,
        },
        ensure_ascii=False,
        default=str,
    )
