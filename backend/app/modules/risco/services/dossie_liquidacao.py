"""Dossie de UMA liquidacao para o modal de julgamento da curadoria.

Retorna os blocos que o analista precisa para decidir OK/FRAUDE numa rolagem
so (sem tabs): header, KPI strip, onde-o-dinheiro-caiu (agencia + endereco +
convergencia), por-que-o-sistema-marcou (sinais do catalogo), o sacado, e o
historico de curadoria (quem marcou, quando, o que — trilha ja no
curadoria_tag). Read puro, tenant-scoped.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Contexto do evento: titulo + sacado + operacao + score + agencia pagadora
# (CNAB -> ref_bacen consolidada) + conta do cedente naquela agencia.
_SQL_EVENTO = text("""
SELECT l.id AS liquidacao_id, l.titulo_id, l.canal, l.evidencia,
       l.data_evento, coalesce(l.valor_pago, l.valor_titulo, 0) AS valor,
       t.numero AS titulo_numero, t.status AS titulo_status,
       o.cedente_nome, o.cedente_documento,
       split_part(o.modalidade, '-', 1) AS produto_sigla,
       dp.nome AS produto_nome,
       sac.nome AS sacado_nome, sac.documento AS sacado_documento,
       sac.localidade AS sacado_cidade, sac.estado AS sacado_uf,
       ds.features, ds.regra_dura, ds.regra_dura_motivo,
       be.banco_pagador, be.agencia_pagadora, be.data_credito,
       ra.nome_agencia, ra.municipio AS ag_municipio, ra.uf AS ag_uf,
       ra.endereco AS ag_endereco, ra.bairro AS ag_bairro,
       ra.primeira_competencia, ra.ultima_competencia, ra.ativa,
       cc.tem_conta AS conta_do_cedente
FROM wh_liquidacao l
JOIN wh_titulo t ON t.tenant_id = l.tenant_id AND t.titulo_id = l.titulo_id
LEFT JOIN wh_operacao o
    ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
LEFT JOIN wh_dim_produto dp
    ON dp.tenant_id = l.tenant_id AND dp.sigla = split_part(o.modalidade, '-', 1)
LEFT JOIN wh_entidade_papel pap
    ON pap.tenant_id = l.tenant_id AND pap.papel = 'sacado'
   AND pap.source_id = t.sacado_id::text
LEFT JOIN wh_entidade sac ON sac.id = pap.entidade_id
LEFT JOIN deteccao_score ds
    ON ds.tenant_id = l.tenant_id AND ds.liquidacao_id = l.id
LEFT JOIN LATERAL (
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
    SELECT true AS tem_conta FROM wh_conta_bancaria cb
    WHERE cb.tenant_id = l.tenant_id
      AND left(cb.entidade_documento, 8) = left(o.cedente_documento, 8)
      AND cb.banco_codigo = lpad(be.banco_pagador, 3, '0')
      AND lpad(cb.agencia_codigo, 5, '0') = lpad(be.agencia_pagadora, 5, '0')
    LIMIT 1
) cc ON true
WHERE l.tenant_id = :tenant_id AND l.id = :liquidacao_id
""")

# Convergencia da agencia pagadora deste evento (S2): quantos sacados do
# cedente pagam nela, de quantas cidades, quantos de outra praca.
_SQL_CONVERGENCIA = text("""
SELECT count(DISTINCT sac.id) AS sacados,
       count(DISTINCT lower(sac.localidade)) AS cidades,
       count(DISTINCT sac.id) FILTER (
           WHERE sac.localidade IS NOT NULL
             AND lower(sac.localidade) <> lower(:ag_municipio)
       ) AS fora
FROM wh_liquidacao l
JOIN wh_operacao o ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
JOIN wh_titulo t ON t.tenant_id = l.tenant_id AND t.titulo_id = l.titulo_id
JOIN wh_boleto_evento be
    ON be.tenant_id = l.tenant_id AND be.titulo_id = l.titulo_id
   AND be.data_credito IS NOT NULL
LEFT JOIN wh_entidade_papel pap
    ON pap.tenant_id = l.tenant_id AND pap.papel = 'sacado'
   AND pap.source_id = t.sacado_id::text
LEFT JOIN wh_entidade sac ON sac.id = pap.entidade_id
WHERE l.tenant_id = :tenant_id AND o.cedente_documento = :cedente
  AND l.canal = 'bancaria'
  AND lpad(be.banco_pagador, 3, '0') = :banco
  AND lpad(be.agencia_pagadora, 5, '0') = :agencia
  AND l.data_evento >= now() - interval '365 days'
""")

# Historico de curadoria deste evento (quem/quando/o que — trilha ja existe).
_SQL_TAGS = text("""
SELECT ct.tag, ct.nota, ct.created_at, u.name AS autor
FROM curadoria_tag ct
LEFT JOIN users u ON u.id = ct.autor
WHERE ct.tenant_id = :tenant_id AND ct.liquidacao_id = :liquidacao_id
ORDER BY ct.created_at DESC
""")


def _f(feats: dict[str, Any] | None, nome: str) -> float:
    if not feats:
        return 0.0
    v = feats.get(nome)
    return float(v) if v is not None else 0.0


async def dossie(
    db: AsyncSession, tenant_id: UUID, liquidacao_id: UUID
) -> dict[str, Any] | None:
    ev = (
        await db.execute(
            _SQL_EVENTO, {"tenant_id": tenant_id, "liquidacao_id": liquidacao_id}
        )
    ).mappings().first()
    if ev is None:
        return None

    feats = ev["features"] or {}
    ag_muni = ev["ag_municipio"]
    banco = (ev["banco_pagador"] or "").strip().zfill(3) if ev["banco_pagador"] else None
    agencia = (ev["agencia_pagadora"] or "").strip().zfill(5) if ev["agencia_pagadora"] else None

    convergencia = None
    if banco and agencia and ev["cedente_documento"]:
        c = (
            await db.execute(
                _SQL_CONVERGENCIA,
                {
                    "tenant_id": tenant_id,
                    "cedente": ev["cedente_documento"],
                    "banco": banco,
                    "agencia": agencia,
                    "ag_municipio": ag_muni or "",
                },
            )
        ).mappings().first()
        convergencia = {
            "sacados": int(c["sacados"] or 0),
            "cidades": int(c["cidades"] or 0),
            "fora": int(c["fora"] or 0),
        }

    tags = [
        {
            "tag": r["tag"],
            "nota": r["nota"],
            "autor": r["autor"],
            "em": r["created_at"],
        }
        for r in (
            await db.execute(
                _SQL_TAGS, {"tenant_id": tenant_id, "liquidacao_id": liquidacao_id}
            )
        ).mappings()
    ]

    # Sinais acesos (feature vector -> catalogo), mais grave primeiro.
    catalogo = {
        r["codigo"]: r
        for r in (
            await db.execute(
                text("SELECT codigo, nome, definicao, severidade FROM deteccao_sinal")
            )
        ).mappings()
    }
    predicados = [
        ("PRC-01", _f(feats, "match_agencia_conta_cedente") >= 0.5
         and _f(feats, "cidade_pgto_neq_sacado") >= 0.5),
        ("PRC-05", _f(feats, "match_agencia_conta_cedente") >= 0.5
         and _f(feats, "cidade_pgto_neq_sacado") < 0.5),
        ("CNV-90", bool(ev["regra_dura"])
         and not (_f(feats, "match_agencia_conta_cedente") >= 0.5)),
        ("PRC-02", _f(feats, "cidade_pgto_eq_cedente") >= 0.5
         and _f(feats, "cidade_pgto_neq_sacado") >= 0.5),
        ("CNV-01", _f(feats, "agencia_compartilhada") > 0
         and _f(feats, "cidade_pgto_neq_sacado") >= 0.5),
        ("CNV-02", _f(feats, "agencia_compartilhada_cedentes") > 0
         and _f(feats, "cidade_pgto_neq_sacado") >= 0.5),
        ("MEC-01", _f(feats, "baixa_confirmada") >= 0.5),
        ("PRC-03", _f(feats, "cidade_pgto_neq_sacado") >= 0.5),
        ("FGP-01", _f(feats, "quebra_fingerprint") > 0),
    ]
    _sev = {"critica": 0, "pendente": 1, "alta": 2, "media": 3, "baixa": 4}
    sinais = sorted(
        (
            {
                "codigo": cod,
                "nome": catalogo.get(cod, {}).get("nome", cod),
                "definicao": catalogo.get(cod, {}).get("definicao"),
                "severidade": catalogo.get(cod, {}).get("severidade", "?"),
            }
            for cod, aceso in predicados
            if aceso
        ),
        key=lambda x: _sev.get(x["severidade"], 9),
    )

    quebra_fingerprint = _f(feats, "quebra_fingerprint")
    return {
        "liquidacao_id": str(ev["liquidacao_id"]),
        "titulo_id": ev["titulo_id"],
        "titulo_numero": ev["titulo_numero"],
        "cedente_nome": ev["cedente_nome"],
        "cedente_documento": ev["cedente_documento"],
        "produto_sigla": ev["produto_sigla"],
        "produto_nome": ev["produto_nome"],
        "sacado_nome": ev["sacado_nome"],
        "sacado_documento": ev["sacado_documento"],
        "sacado_cidade": ev["sacado_cidade"],
        "sacado_uf": ev["sacado_uf"],
        "canal": ev["canal"],
        "evidencia": ev["evidencia"],
        "valor": float(ev["valor"] or 0),
        "data_evento": ev["data_evento"],
        "agencia": {
            "banco": ev["banco_pagador"],
            "agencia": ev["agencia_pagadora"],
            "nome": ev["nome_agencia"],
            "cidade": ev["ag_municipio"],
            "uf": ev["ag_uf"],
            "endereco": ev["ag_endereco"],
            "bairro": ev["ag_bairro"],
            "ativa": ev["ativa"],
            "vigencia": (
                f"{ev['primeira_competencia']}-{ev['ultima_competencia']}"
                if ev["primeira_competencia"]
                else None
            ),
            "conta_do_cedente": bool(ev["conta_do_cedente"]),
            "data_credito": ev["data_credito"],
            "convergencia": convergencia,
        },
        "sinais": sinais,
        "quebra_fingerprint": round(quebra_fingerprint, 2) if quebra_fingerprint else 0.0,
        "historico_curadoria": tags,
    }
