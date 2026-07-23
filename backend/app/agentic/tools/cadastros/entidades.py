"""buscar_entidade — resolucao nome/documento -> entidade do party model.

Porta de entrada do chat livre (spec copiloto-mcp §10 Fase 2): o usuario
fala "cedente MFL" ou cola um CNPJ; esta tool resolve contra `wh_entidade`
(+ papeis em `wh_entidade_papel`) para as demais tools trabalharem com o
documento exato. Silver-only (§13.2.1), tenant-scoped (§10).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission

_MAX_RESULTS = 10


def _digits(value: str) -> str:
    return "".join(c for c in value if c.isdigit())


@register_tool(
    name="buscar_entidade",
    description=(
        "Busca uma entidade (empresa ou pessoa) nos dados da plataforma por "
        "NOME (busca parcial, sem acento nao e ignorado — tente variantes) ou "
        "por DOCUMENTO (CNPJ/CPF, com ou sem pontuacao). Retorna documento, "
        "nome, papeis na operacao (cedente/sacado/...), cidade/UF e porte. "
        "Use SEMPRE que o usuario citar uma empresa por nome e voce precisar "
        "do documento exato para outras consultas. Argumento opcional "
        "`papel` filtra por papel ('cedente', 'sacado')."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "termo": {
                "type": "string",
                "description": "Nome (parcial) ou CNPJ/CPF da entidade.",
            },
            "papel": {
                "type": "string",
                "description": "Filtro opcional de papel: 'cedente' | 'sacado'.",
            },
        },
        "required": ["termo"],
    },
    module=Module.CADASTROS,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def buscar_entidade(scope: ScopedContext, args: dict[str, Any]) -> str:
    termo = str(args.get("termo", "")).strip()
    papel = (str(args.get("papel", "")).strip().lower() or None)
    if not termo:
        return json.dumps({"erro": "Informe um nome ou documento."}, ensure_ascii=False)

    digits = _digits(termo)
    by_document = len(digits) >= 11 and len(digits) == len(termo.replace(".", "").replace("/", "").replace("-", "").replace(" ", ""))

    where = ["e.tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": str(scope.tenant_id)}
    if by_document:
        where.append("regexp_replace(e.documento, '\\D', '', 'g') = :doc")
        params["doc"] = digits
    else:
        where.append("e.nome ILIKE :nome")
        params["nome"] = f"%{termo}%"

    papel_join = ""
    if papel:
        papel_join = (
            "JOIN wh_entidade_papel pf ON pf.entidade_id = e.id "
            "AND pf.tenant_id = e.tenant_id AND lower(pf.papel) = :papel "
        )
        params["papel"] = papel

    rows = (
        await scope.db.execute(
            text(
                f"""
                SELECT e.documento, e.tipo_pessoa, e.nome, e.porte,
                       e.localidade, e.estado, e.em_recuperacao_judicial,
                       COALESCE(
                         (SELECT array_agg(DISTINCT p.papel)
                          FROM wh_entidade_papel p
                          WHERE p.entidade_id = e.id
                            AND p.tenant_id = e.tenant_id),
                         ARRAY[]::varchar[]
                       ) AS papeis
                FROM wh_entidade e
                {papel_join}
                WHERE {" AND ".join(where)}
                ORDER BY e.nome
                LIMIT :limit
                """
            ),
            {**params, "limit": _MAX_RESULTS + 1},
        )
    ).mappings().all()

    truncado = len(rows) > _MAX_RESULTS
    resultado = [
        {
            "documento": r["documento"],
            "tipo_pessoa": r["tipo_pessoa"],
            "nome": r["nome"],
            "porte": r["porte"],
            "cidade_uf": (
                f"{r['localidade']}/{r['estado']}"
                if r["localidade"]
                else r["estado"]
            ),
            "em_recuperacao_judicial": r["em_recuperacao_judicial"],
            "papeis": list(r["papeis"] or []),
        }
        for r in rows[:_MAX_RESULTS]
    ]
    return json.dumps(
        {
            "encontradas": resultado,
            "mais_resultados": truncado,
            "dica": (
                "Nenhuma entidade encontrada. Tente parte do nome ou o CNPJ."
                if not resultado
                else None
            ),
        },
        ensure_ascii=False,
        default=str,
    )
