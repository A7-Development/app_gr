"""Dossie de UMA liquidacao para o modal de curadoria (handoff 6a "case file").

Retorna, numa rolagem unica que cabe sem scroll, os blocos que o analista
precisa para decidir OK/FRAUDE:
  - header (cedente -> sacado + titulo) + classificacao de risco do sistema;
  - fichas Cedente | Sacado (endereco + contas conhecidas / historico de
    liquidacao por agencia);
  - card da liquidacao (titulo/valor/data/produto/canal + onde liquidou) +
    faixa de sinais do catalogo;
  - evidencia (sacados que convergem no balcao) carregada junto (lazy no front);
  - proveniencia + trilha de curadoria.
Read puro, tenant-scoped.
"""

from __future__ import annotations

import unicodedata
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Contexto do evento: titulo + sacado (com endereco) + operacao + score +
# agencia pagadora (CNAB -> ref_bacen consolidada) + conta do cedente naquela
# agencia + endereco do cedente. left(ltrim(...,'0'),8) normaliza a raiz do
# CNPJ (cedente_documento vem com zero a esquerda; wh_conta_bancaria nao).
_SQL_EVENTO = text("""
SELECT l.id AS liquidacao_id, l.titulo_id, l.canal, l.evidencia,
       l.data_evento, l.ingested_at AS sincronizado_em,
       coalesce(l.valor_pago, l.valor_titulo, 0) AS valor,
       t.numero AS titulo_numero, t.status AS titulo_status, t.sacado_id,
       o.cedente_nome, o.cedente_documento,
       split_part(o.modalidade, '-', 1) AS produto_sigla,
       dp.nome AS produto_nome,
       sac.nome AS sacado_nome, sac.documento AS sacado_documento,
       sac.localidade AS sacado_cidade, sac.estado AS sacado_uf,
       sac.logradouro AS sacado_logradouro, sac.endereco_numero AS sacado_numero,
       sac.bairro AS sacado_bairro,
       ds.features, ds.regra_dura, ds.regra_dura_motivo,
       be.banco_pagador, be.agencia_pagadora, be.data_credito,
       ra.nome_agencia, ra.municipio AS ag_municipio, ra.uf AS ag_uf,
       ra.endereco AS ag_endereco, ra.bairro AS ag_bairro,
       ra.primeira_competencia, ra.ultima_competencia, ra.ativa,
       cc.tem_conta AS conta_do_cedente,
       ced.localidade AS cedente_cidade, ced.estado AS cedente_uf,
       ced.logradouro AS cedente_logradouro, ced.endereco_numero AS cedente_numero,
       ced.bairro AS cedente_bairro
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
    SELECT e.localidade, e.estado, e.logradouro, e.endereco_numero, e.bairro
    FROM wh_entidade e
    WHERE e.documento_raiz = left(ltrim(o.cedente_documento, '0'), 8)
      AND e.localidade IS NOT NULL
    ORDER BY e.is_matriz DESC NULLS LAST LIMIT 1
) ced ON true
LEFT JOIN LATERAL (
    SELECT true AS tem_conta FROM wh_conta_bancaria cb
    WHERE cb.tenant_id = l.tenant_id
      AND left(ltrim(cb.entidade_documento, '0'), 8)
          = left(ltrim(o.cedente_documento, '0'), 8)
      AND cb.banco_codigo = lpad(be.banco_pagador, 3, '0')
      AND lpad(cb.agencia_codigo, 5, '0') = lpad(be.agencia_pagadora, 5, '0')
    LIMIT 1
) cc ON true
WHERE l.tenant_id = :tenant_id AND l.id = :liquidacao_id
""")

# Contas bancarias conhecidas do cedente (ficha esquerda). Qtd de titulos por
# agencia ainda nao computada -> front mostra "—".
_SQL_CEDENTE_CONTAS = text("""
SELECT DISTINCT ON (banco_codigo, agencia_codigo)
       banco_codigo AS banco, banco_nome, agencia_codigo AS agencia,
       agencia_localidade AS cidade, agencia_estado AS uf
FROM wh_conta_bancaria
WHERE tenant_id = :tenant_id
  AND left(ltrim(entidade_documento, '0'), 8) = left(ltrim(:cedente, '0'), 8)
ORDER BY banco_codigo, agencia_codigo
""")

# Historico de liquidacao do sacado por banco+agencia (ficha direita): onde
# este sacado costuma liquidar, com cidade da agencia via ref_bacen.
_SQL_SACADO_HIST = text("""
SELECT lpad(be.banco_pagador, 3, '0') AS banco,
       lpad(be.agencia_pagadora, 5, '0') AS agencia,
       ra.nome_if AS banco_nome, ra.municipio AS cidade, ra.uf AS uf,
       ra.bairro AS bairro,
       count(DISTINCT t.titulo_id) AS qtd
FROM wh_titulo t
JOIN wh_boleto_evento be
    ON be.tenant_id = t.tenant_id AND be.titulo_id = t.titulo_id
   AND be.data_credito IS NOT NULL
LEFT JOIN ref_bacen_agencia ra
    ON ra.banco_compe = lpad(be.banco_pagador, 3, '0')
   AND ra.agencia_codigo = lpad(be.agencia_pagadora, 5, '0')
WHERE t.tenant_id = :tenant_id AND t.sacado_id = :sacado_id
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY qtd DESC
LIMIT 6
""")

# Evidencia de convergencia: sacados do cedente que liquidam NESTA agencia
# (para o "Ver os N sacados do balcao"). Fora = cidade do sacado != cidade
# do balcao.
_SQL_EVIDENCIA = text("""
SELECT sac.nome, sac.localidade AS cidade, sac.estado AS uf,
       count(DISTINCT t.titulo_id) AS qtd,
       (sac.localidade IS NOT NULL
        AND lower(sac.localidade) <> lower(:ag_municipio)) AS fora
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
GROUP BY sac.nome, sac.localidade, sac.estado
ORDER BY fora DESC, qtd DESC
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


def _norm(s: str | None) -> str:
    """Casefold + strip accents for city comparison (Rio De Janeiro == Rio de Janeiro)."""
    if not s:
        return ""
    n = unicodedata.normalize("NFD", s)
    return "".join(c for c in n if unicodedata.category(c) != "Mn").strip().lower()


# Severidade do pior sinal -> classificacao de risco do sistema (pill do header).
_CLASSIF = {
    "critica": ("critico", "Risco crítico"),
    "pendente": ("critico", "Risco crítico"),
    "alta": ("alto", "Risco alto"),
    "media": ("medio", "Risco médio"),
    "baixa": ("baixo", "Risco baixo"),
}
_SEV_ORDEM = {"critica": 0, "pendente": 1, "alta": 2, "media": 3, "baixa": 4}


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

    # Contas conhecidas do cedente (ficha esquerda).
    cedente_contas = [
        {
            "banco": r["banco"],
            "banco_nome": r["banco_nome"],
            "agencia": r["agencia"],
            "cidade": r["cidade"],
            "uf": r["uf"],
        }
        for r in (
            await db.execute(
                _SQL_CEDENTE_CONTAS,
                {"tenant_id": tenant_id, "cedente": ev["cedente_documento"] or ""},
            )
        ).mappings()
    ] if ev["cedente_documento"] else []

    # Historico de liquidacao do sacado por agencia (ficha direita).
    sacado_historico = [
        {
            "banco": r["banco"],
            "banco_nome": r["banco_nome"],
            "agencia": r["agencia"],
            "cidade": r["cidade"],
            "uf": r["uf"],
            "bairro": r["bairro"],
            "qtd": int(r["qtd"] or 0),
        }
        for r in (
            await db.execute(
                _SQL_SACADO_HIST,
                {"tenant_id": tenant_id, "sacado_id": ev["sacado_id"]},
            )
        ).mappings()
    ] if ev["sacado_id"] is not None else []

    # Alerta "fora da praca": todo o historico do sacado cai em cidade(s)
    # diferente(s) da sua propria praca.
    sac_city = _norm(ev["sacado_cidade"])
    hist_com_cidade = [h for h in sacado_historico if h["cidade"]]
    sacado_fora_praca = bool(
        sac_city
        and hist_com_cidade
        and all(_norm(h["cidade"]) != sac_city for h in hist_com_cidade)
    )
    sacado_liquida_em = None
    if sacado_historico and sacado_historico[0]["cidade"]:
        top = sacado_historico[0]
        sacado_liquida_em = f"{top['cidade']}/{top['uf']}" if top["uf"] else top["cidade"]

    convergencia = None
    evidencia_sacados: list[dict[str, Any]] = []
    if banco and agencia and ev["cedente_documento"]:
        params = {
            "tenant_id": tenant_id,
            "cedente": ev["cedente_documento"],
            "banco": banco,
            "agencia": agencia,
            "ag_municipio": ag_muni or "",
        }
        c = (await db.execute(_SQL_CONVERGENCIA, params)).mappings().first()
        convergencia = {
            "sacados": int(c["sacados"] or 0),
            "cidades": int(c["cidades"] or 0),
            "fora": int(c["fora"] or 0),
        }
        evidencia_sacados = [
            {
                "nome": r["nome"],
                "cidade": r["cidade"],
                "uf": r["uf"],
                "qtd": int(r["qtd"] or 0),
                "fora": bool(r["fora"]),
            }
            for r in (await db.execute(_SQL_EVIDENCIA, params)).mappings()
        ]

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
        key=lambda x: _SEV_ORDEM.get(x["severidade"], 9),
    )

    # Classificacao do sistema (pill do header): pior severidade acesa.
    if sinais:
        nivel, label = _CLASSIF.get(sinais[0]["severidade"], ("indefinido", "Sem sinal"))
    else:
        nivel, label = ("indefinido", "Sem sinal automático")

    quebra_fingerprint = _f(feats, "quebra_fingerprint")
    return {
        "liquidacao_id": str(ev["liquidacao_id"]),
        "titulo_id": ev["titulo_id"],
        "titulo_numero": ev["titulo_numero"],
        "sincronizado_em": ev["sincronizado_em"],
        "cedente_nome": ev["cedente_nome"],
        "cedente_documento": ev["cedente_documento"],
        "cedente_cidade": ev["cedente_cidade"],
        "cedente_uf": ev["cedente_uf"],
        "cedente_logradouro": ev["cedente_logradouro"],
        "cedente_numero": ev["cedente_numero"],
        "cedente_bairro": ev["cedente_bairro"],
        "cedente_contas": cedente_contas,
        "produto_sigla": ev["produto_sigla"],
        "produto_nome": ev["produto_nome"],
        "sacado_nome": ev["sacado_nome"],
        "sacado_documento": ev["sacado_documento"],
        "sacado_cidade": ev["sacado_cidade"],
        "sacado_uf": ev["sacado_uf"],
        "sacado_logradouro": ev["sacado_logradouro"],
        "sacado_numero": ev["sacado_numero"],
        "sacado_bairro": ev["sacado_bairro"],
        "sacado_historico": sacado_historico,
        "sacado_fora_praca": sacado_fora_praca,
        "sacado_liquida_em": sacado_liquida_em,
        "canal": ev["canal"],
        "evidencia": ev["evidencia"],
        "valor": float(ev["valor"] or 0),
        "data_evento": ev["data_evento"],
        "classificacao": {"nivel": nivel, "label": label},
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
        "evidencia_sacados": evidencia_sacados,
        "sinais": sinais,
        "quebra_fingerprint": round(quebra_fingerprint, 2) if quebra_fingerprint else 0.0,
        "historico_curadoria": tags,
    }
