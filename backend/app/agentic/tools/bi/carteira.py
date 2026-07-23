"""get_carteira_fundo — fotografia da carteira de recebiveis (silver).

Le `wh_estoque_recebivel` no snapshot mais recente (ou na data pedida):
totais, PDD, quebra por situacao e concentracoes top-5 com linha "Outros"
somando a cauda — a selecao sempre reconcilia com o total (CLAUDE.md
§14.6, zero ocultacao). Silver-only, tenant-scoped.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission

_TOP_N = 5


@register_tool(
    name="get_carteira_fundo",
    description=(
        "Fotografia da carteira de recebiveis nos seus dados: valor presente "
        "total, valor nominal, PDD, quantidade de papeis/cedentes/sacados, "
        "quebra por situacao e as maiores concentracoes por cedente e por "
        "sacado (top 5 + 'Outros' somando o resto — a soma bate o total). "
        "Argumentos opcionais: `fundo` (nome parcial ou CNPJ do fundo, util "
        "quando ha mais de um) e `data_referencia` (AAAA-MM-DD; default = "
        "snapshot mais recente). Use para perguntas como 'como esta a "
        "carteira?', 'qual a exposicao do fundo X?'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fundo": {
                "type": "string",
                "description": "Nome parcial ou CNPJ do fundo (opcional).",
            },
            "data_referencia": {
                "type": "string",
                "description": "Data do snapshot AAAA-MM-DD (opcional).",
            },
        },
    },
    module=Module.BI,
    min_permission=Permission.READ,
    cost_hint="medium",
    cacheable=True,
)
async def get_carteira_fundo(scope: ScopedContext, args: dict[str, Any]) -> str:
    fundo = str(args.get("fundo", "")).strip() or None
    data_ref = str(args.get("data_referencia", "")).strip() or None

    params: dict[str, Any] = {"tenant_id": str(scope.tenant_id)}
    fundo_where = ""
    if fundo:
        digits = "".join(c for c in fundo if c.isdigit())
        if len(digits) == 14:
            fundo_where = "AND regexp_replace(fundo_doc, '\\D', '', 'g') = :fundo_doc"
            params["fundo_doc"] = digits
        else:
            fundo_where = "AND fundo_nome ILIKE :fundo_nome"
            params["fundo_nome"] = f"%{fundo}%"

    if data_ref:
        params["data_ref"] = data_ref
    else:
        row = (
            await scope.db.execute(
                text(
                    f"SELECT max(data_referencia) AS d FROM wh_estoque_recebivel "
                    f"WHERE tenant_id = :tenant_id {fundo_where}"
                ),
                params,
            )
        ).mappings().one()
        if row["d"] is None:
            return json.dumps(
                {"erro": "Nenhum snapshot de carteira encontrado para esse filtro."},
                ensure_ascii=False,
            )
        params["data_ref"] = str(row["d"])

    base_where = (
        f"tenant_id = :tenant_id AND data_referencia = :data_ref {fundo_where}"
    )

    totais = (
        await scope.db.execute(
            text(
                f"""
                SELECT count(*) AS n_papeis,
                       count(DISTINCT cedente_doc) AS n_cedentes,
                       count(DISTINCT sacado_doc) AS n_sacados,
                       count(DISTINCT fundo_doc) AS n_fundos,
                       COALESCE(sum(valor_presente), 0) AS valor_presente,
                       COALESCE(sum(valor_nominal), 0) AS valor_nominal,
                       COALESCE(sum(valor_pdd), 0) AS valor_pdd
                FROM wh_estoque_recebivel WHERE {base_where}
                """
            ),
            params,
        )
    ).mappings().one()

    if totais["n_papeis"] == 0:
        return json.dumps(
            {"erro": "Carteira vazia para esse filtro/data."}, ensure_ascii=False
        )

    fundos = (
        await scope.db.execute(
            text(
                f"""
                SELECT fundo_nome, fundo_doc,
                       COALESCE(sum(valor_presente), 0) AS valor_presente,
                       count(*) AS n_papeis
                FROM wh_estoque_recebivel WHERE {base_where}
                GROUP BY fundo_nome, fundo_doc ORDER BY 3 DESC
                """
            ),
            params,
        )
    ).mappings().all()

    situacoes = (
        await scope.db.execute(
            text(
                f"""
                SELECT COALESCE(situacao_recebivel, '(sem situacao)') AS situacao,
                       COALESCE(sum(valor_presente), 0) AS valor_presente,
                       count(*) AS n_papeis
                FROM wh_estoque_recebivel WHERE {base_where}
                GROUP BY 1 ORDER BY 2 DESC
                """
            ),
            params,
        )
    ).mappings().all()

    async def _top_com_outros(dim: str) -> list[dict[str, Any]]:
        rows = (
            await scope.db.execute(
                text(
                    f"""
                    SELECT {dim}_nome AS nome,
                           COALESCE(sum(valor_presente), 0) AS valor_presente,
                           count(*) AS n_papeis
                    FROM wh_estoque_recebivel WHERE {base_where}
                    GROUP BY 1 ORDER BY 2 DESC
                    """
                ),
                params,
            )
        ).mappings().all()
        total_vp = float(totais["valor_presente"]) or 1.0
        top = [
            {
                "nome": r["nome"],
                "valor_presente": float(r["valor_presente"]),
                "pct": round(100 * float(r["valor_presente"]) / total_vp, 1),
                "n_papeis": r["n_papeis"],
            }
            for r in rows[:_TOP_N]
        ]
        cauda = rows[_TOP_N:]
        if cauda:
            # Zero ocultacao (§14.6): a cauda vira linha explicita — soma bate.
            top.append(
                {
                    "nome": f"Outros ({len(cauda)})",
                    "valor_presente": float(sum(r["valor_presente"] for r in cauda)),
                    "pct": round(
                        100 * float(sum(r["valor_presente"] for r in cauda)) / total_vp,
                        1,
                    ),
                    "n_papeis": int(sum(r["n_papeis"] for r in cauda)),
                }
            )
        return top

    return json.dumps(
        {
            "data_referencia": params["data_ref"],
            "totais": {k: (float(v) if k.startswith("valor") else v) for k, v in dict(totais).items()},
            "fundos": [
                {
                    "fundo": r["fundo_nome"],
                    "documento": r["fundo_doc"],
                    "valor_presente": float(r["valor_presente"]),
                    "n_papeis": r["n_papeis"],
                }
                for r in fundos
            ],
            "por_situacao": [
                {
                    "situacao": r["situacao"],
                    "valor_presente": float(r["valor_presente"]),
                    "n_papeis": r["n_papeis"],
                }
                for r in situacoes
            ],
            "concentracao_cedentes": await _top_com_outros("cedente"),
            "concentracao_sacados": await _top_com_outros("sacado"),
        },
        ensure_ascii=False,
        default=str,
    )
