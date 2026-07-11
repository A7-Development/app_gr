"""Calculo do rating deterministico de integridade de liquidacao.

Formula (fechada com Ricardo 2026-07-11; todos os numeros em
`deteccao_parametro`, versionados):

    score_evento = 100 - soma(deducao dos sinais do catalogo que acenderam)
    score_par    = media dos score_evento ponderada por VALOR
    critico      = qualquer evento com sinal de severidade critica
                   (PRC-01 / CNV-90) -> score do par TRAVA em <= teto_critico
    grade        = faixa do score; grades boas (A/B) exigem
                   n >= rating_n_minimo_grade_boa E cobertura >=
                   rating_cobertura_minima_grade_boa, senao NC

Universo do score = eventos com ALEGACAO de pagamento do sacado (canais
bancaria + baixa_manual). Recompra/perda/baixa administrativa ficam fora do
score e dentro da COBERTURA (decisao 2026-07-11: integridade e credito nao
se misturam — recompra e variavel do futuro sub-rating de performance).

Sinais lidos de `deteccao_score.features` (vetor persistido) com as lentes
aplicadas na conjuncao (praca indistinguivel: PRC-02/03 so contam com
cidades divergentes — mesma convencao do painel /risco/padroes-liquidacao).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risco.models.rating import RatingLiquidacao
from app.modules.risco.services.deteccao_parametros import carregar_parametros
from app.shared.audit_log.decision_log import DecisionLog, DecisionType

logger = logging.getLogger(__name__)

FORMULA_VERSION = "rating_liquidacao@v1"

# Sinais do catalogo avaliados por evento: (codigo, severidade, predicado
# sobre o vetor de features). Predicados espelham as CONDICOES do catalogo
# (deteccao_sinal.definicao) — lente "praca indistinguivel" embutida nas
# conjuncoes de PRC-02/03/CNV. Severidade critica NAO deduz: trava a nota.
_F = dict[str, float]


def _f(feats: _F, nome: str) -> float:
    v = feats.get(nome)
    return float(v) if v is not None else 0.0


_SINAIS_EVENTO: tuple[tuple[str, str], ...] = (
    # (codigo, severidade) — predicado em _sinal_acendeu.
    ("PRC-01", "critica"),
    ("CNV-90", "critica"),
    # Critico PENDENTE: trava a nota ate a curadoria decidir (OK libera).
    ("PRC-05", "critica_pendente"),
    ("PRC-02", "alta"),
    ("CNV-01", "alta"),
    ("CNV-02", "alta"),
    ("MEC-01", "alta"),
    ("PRC-03", "media"),
    ("FGP-01", "media"),
)


def _sinal_acendeu(codigo: str, feats: _F, regra_dura: bool) -> bool:
    """Predicados dos sinais AUTOMATICOS (a tag humana e tratada em
    score_evento — humano manda sobre qualquer predicado)."""
    neq_sacado = _f(feats, "cidade_pgto_neq_sacado") >= 0.5
    match codigo:
        case "PRC-01":
            # Agencia da conta do cedente E sacado de OUTRA cidade — o
            # qualificador e essencial (Ricardo 2026-07-11): em cidade
            # pequena, sacado local paga na unica agencia da praca, que por
            # acaso e a do cedente (Fricock: 107/107 mesma cidade). Mesma
            # condicao da regra dura original do motor.
            return _f(feats, "match_agencia_conta_cedente") >= 0.5 and neq_sacado
        case "PRC-05":
            # Agencia da conta do cedente, MESMA cidade: ambiguo — cidade
            # pequena pode ser inocente, mas ambiguidade em sinal grave e
            # decisao HUMANA (Ricardo 2026-07-11): trava a nota como critico
            # PENDENTE ate a curadoria liberar (tag OK) ou confirmar (FRAUDE).
            return _f(feats, "match_agencia_conta_cedente") >= 0.5 and not neq_sacado
        case "CNV-90":
            # Composto critico — hoje materializado pela regra dura de
            # multicidade do builder (motivo 'agencia compartilhada...').
            return regra_dura and not (_f(feats, "match_agencia_conta_cedente") >= 0.5)
        case "PRC-02":
            return _f(feats, "cidade_pgto_eq_cedente") >= 0.5 and neq_sacado
        case "CNV-01":
            return _f(feats, "agencia_compartilhada") > 0 and neq_sacado
        case "CNV-02":
            return _f(feats, "agencia_compartilhada_cedentes") > 0 and neq_sacado
        case "MEC-01":
            return _f(feats, "baixa_confirmada") >= 0.5
        case "PRC-03":
            return neq_sacado
        case "FGP-01":
            return _f(feats, "quebra_fingerprint") > 0
    return False


def score_evento(
    feats: _F,
    regra_dura: bool,
    params: dict[str, Any],
    tag_curadoria: str | None = None,
) -> tuple[float, bool, list[str]]:
    """(score 0-100, tem_critico, codigos acesos) de UM evento — funcao pura.

    Tag humana da curadoria MANDA sobre o automatico (IA opina, humano
    decide): FRAUDE = critico definitivo (mesmo sem sinal); OK libera o
    PRC-05 pendente (validado inocente); NEUTRO/sem tag = pendencia fica.
    """
    if tag_curadoria == "FRAUDE":
        return 0.0, True, ["TAG-FRAUDE"]
    deducao = {"alta": float(params["rating_deducao_alta"]),
               "media": float(params["rating_deducao_media"])}
    acesos: list[str] = []
    critico = False
    total = 0.0
    for codigo, severidade in _SINAIS_EVENTO:
        if not _sinal_acendeu(codigo, feats, regra_dura):
            continue
        if codigo == "PRC-05" and tag_curadoria == "OK":
            continue  # humano validou: mesma-cidade inocente
        acesos.append(codigo)
        if severidade in ("critica", "critica_pendente"):
            critico = True
        else:
            total += deducao[severidade]
    return max(0.0, 100.0 - total), critico, acesos


# Universo do SCORE: eventos com alegacao de pagamento do sacado, scoreados.
# EXCLUI baixa_manual de titulo que TEM recompra declarada: pela precedencia
# do framework ("recompra vence a inferencia" — caso 693), a recompra explica
# a saida e o evento manual e artefato de registro (Situacao=1 + RecompraItem)
# — nao e alegacao de pagamento do sacado. Bancaria permanece mesmo com
# recompra (dinheiro no trilho e fato CNAB; titulo de vidas multiplas).
_SQL_EVENTOS_SCORE = text("""
SELECT o.cedente_documento,
       max(o.cedente_nome) AS cedente_nome,
       sac.documento AS sacado_documento,
       max(sac.nome) AS sacado_nome,
       ds.features, ds.regra_dura,
       coalesce(l.valor_pago, l.valor_titulo, 0) AS valor,
       l.canal,
       tag.tag AS tag_curadoria
FROM deteccao_score ds
JOIN wh_liquidacao l ON l.id = ds.liquidacao_id
LEFT JOIN LATERAL (
    SELECT ct.tag FROM curadoria_tag ct
    WHERE ct.liquidacao_id = l.id AND ct.tenant_id = l.tenant_id
    ORDER BY ct.created_at DESC LIMIT 1
) tag ON true
JOIN wh_operacao o
    ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
JOIN wh_titulo t
    ON t.tenant_id = l.tenant_id AND t.titulo_id = l.titulo_id
LEFT JOIN wh_entidade_papel pap
    ON pap.tenant_id = l.tenant_id AND pap.papel = 'sacado'
   AND pap.source_id = t.sacado_id::text
LEFT JOIN wh_entidade sac ON sac.id = pap.entidade_id
WHERE ds.tenant_id = :tenant_id
  AND l.canal IN ('bancaria', 'baixa_manual')
  AND NOT (
      l.canal = 'baixa_manual'
      AND EXISTS (
          SELECT 1 FROM wh_liquidacao r
          WHERE r.tenant_id = l.tenant_id
            AND r.titulo_id = l.titulo_id
            AND r.canal = 'recompra'
      )
  )
  AND o.cedente_documento IS NOT NULL
  AND l.data_evento >= now() - make_interval(days => :janela_dias)
GROUP BY o.cedente_documento, sac.documento, ds.features, ds.regra_dura,
         l.valor_pago, l.valor_titulo, l.canal, l.id, tag.tag
""")

# Universo COMPLETO de desfechos (denominador da cobertura) por par.
# 1 linha por TITULO (nao por evento — titulo com baixa manual + recompra
# contava o valor DUAS vezes; bug pego pelo Ricardo 2026-07-11 na MFL:
# 18,5M por evento vs 15,1M por titulo, VOP 16,6M confirma o por-titulo).
# Desfecho final por precedencia deterministica: recompra > bancaria >
# baixa_manual > baixa_administrativa > perda.
_SQL_DESFECHOS = text("""
WITH desfecho_titulo AS (
    SELECT DISTINCT ON (l.titulo_id)
           l.titulo_id, l.tenant_id, l.operacao_id, l.canal,
           coalesce(l.valor_pago, l.valor_titulo, 0) AS valor
    FROM wh_liquidacao l
    WHERE l.tenant_id = :tenant_id
      AND l.data_evento >= now() - make_interval(days => :janela_dias)
    ORDER BY l.titulo_id,
             CASE l.canal
                 WHEN 'recompra' THEN 1
                 WHEN 'bancaria' THEN 2
                 WHEN 'baixa_manual' THEN 3
                 WHEN 'baixa_administrativa' THEN 4
                 ELSE 5
             END
)
SELECT o.cedente_documento,
       sac.documento AS sacado_documento,
       d.canal,
       count(*) AS n,
       sum(d.valor) AS valor
FROM desfecho_titulo d
JOIN wh_operacao o
    ON o.operacao_id = d.operacao_id AND o.tenant_id = d.tenant_id
JOIN wh_titulo t
    ON t.tenant_id = d.tenant_id AND t.titulo_id = d.titulo_id
LEFT JOIN wh_entidade_papel pap
    ON pap.tenant_id = d.tenant_id AND pap.papel = 'sacado'
   AND pap.source_id = t.sacado_id::text
LEFT JOIN wh_entidade sac ON sac.id = pap.entidade_id
WHERE o.cedente_documento IS NOT NULL
GROUP BY o.cedente_documento, sac.documento, d.canal
""")


def _grade(score: float | None, params: dict[str, Any]) -> str:
    if score is None:
        return "NC"
    if score >= float(params["rating_grade_a"]):
        return "A"
    if score >= float(params["rating_grade_b"]):
        return "B"
    if score >= float(params["rating_grade_c"]):
        return "C"
    if score >= float(params["rating_grade_d"]):
        return "D"
    return "E"


def _aplicar_portao(
    grade: str, n_eventos: int, cobertura: float, params: dict[str, Any]
) -> str:
    """Assimetria estatistica: grade boa exige base; nota ruim vale sempre."""
    if grade in ("A", "B") and (
        n_eventos < int(params["rating_n_minimo_grade_boa"])
        or cobertura < float(params["rating_cobertura_minima_grade_boa"])
    ):
        return "NC"
    return grade


def _consolidar(
    escopo: dict[str, Any], params: dict[str, Any]
) -> dict[str, Any]:
    """Fecha score/grade/componentes de um escopo (par ou cedente)."""
    valor_score = escopo["valor_score"]
    score: float | None = None
    if escopo["n_eventos"] > 0 and valor_score > 0:
        score = escopo["soma_ponderada"] / valor_score
    elif escopo["n_eventos"] > 0:
        score = min(e for e in escopo["scores_sem_valor"])  # eventos valor 0
    teto = float(params["rating_teto_critico"])
    if score is not None and escopo["critico"]:
        score = min(score, teto)

    valor_desfechos = escopo["valor_desfechos"]
    cobertura = (
        float(escopo["valor_bancaria"] / valor_desfechos) if valor_desfechos else 0.0
    )
    grade_bruta = _grade(score, params)
    grade = _aplicar_portao(grade_bruta, escopo["n_eventos"], cobertura, params)
    return {
        "score": round(score, 2) if score is not None else None,
        "grade": grade,
        "tem_critico": escopo["critico"],
        "n_eventos_score": escopo["n_eventos"],
        "n_desfechos": escopo["n_desfechos"],
        "valor_desfechos": round(float(valor_desfechos), 2),
        "cobertura": round(cobertura, 4),
        "componentes": {
            "grade_bruta": grade_bruta,
            "pendencias_curadoria": escopo["pendencias_curadoria"],
            "sinais": escopo["sinais"],
            "mix_desfechos": escopo["mix"],
            "parametros": {
                k: params[k]
                for k in (
                    "rating_deducao_alta", "rating_deducao_media",
                    "rating_teto_critico", "rating_janela_dias",
                    "rating_n_minimo_grade_boa",
                    "rating_cobertura_minima_grade_boa",
                )
            },
        },
    }


def _novo_escopo() -> dict[str, Any]:
    return {
        "n_eventos": 0, "soma_ponderada": 0.0, "valor_score": 0.0,
        "pendencias_curadoria": 0,
        "scores_sem_valor": [], "critico": False, "sinais": {},
        "mix": {}, "n_desfechos": 0,
        "valor_desfechos": Decimal(0), "valor_bancaria": Decimal(0),
    }


async def recalcular(db: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    """Full refresh do rating (pares + rollup por cedente) de um tenant."""
    params = await carregar_parametros(db)
    janela = int(params["rating_janela_dias"])

    pares: dict[tuple[str, str | None], dict[str, Any]] = {}
    cedentes: dict[str, dict[str, Any]] = {}
    nomes: dict[str, str | None] = {}

    def escopos(ced: str, sacado: str | None):
        par = pares.setdefault((ced, sacado), _novo_escopo())
        rollup = cedentes.setdefault(ced, _novo_escopo())
        return (par, rollup)

    rows = (
        await db.execute(
            _SQL_EVENTOS_SCORE, {"tenant_id": tenant_id, "janela_dias": janela}
        )
    ).mappings()
    for r in rows:
        ced = r["cedente_documento"]
        sacado = r["sacado_documento"]
        nomes.setdefault(ced, r["cedente_nome"])
        if sacado:
            nomes.setdefault(sacado, r["sacado_nome"])
        s, critico, acesos = score_evento(
            r["features"] or {},
            bool(r["regra_dura"]),
            params,
            tag_curadoria=r["tag_curadoria"],
        )
        valor = float(r["valor"] or 0)
        for escopo in escopos(ced, sacado):
            escopo["n_eventos"] += 1
            if valor > 0:
                escopo["soma_ponderada"] += s * valor
                escopo["valor_score"] += valor
            else:
                escopo["scores_sem_valor"].append(s)
            escopo["critico"] = escopo["critico"] or critico
            if "PRC-05" in acesos:
                escopo["pendencias_curadoria"] += 1
            for codigo in acesos:
                escopo["sinais"][codigo] = escopo["sinais"].get(codigo, 0) + 1

    rows = (
        await db.execute(
            _SQL_DESFECHOS, {"tenant_id": tenant_id, "janela_dias": janela}
        )
    ).mappings()
    for r in rows:
        ced = r["cedente_documento"]
        valor = Decimal(r["valor"] or 0)
        for escopo in escopos(ced, r["sacado_documento"]):
            escopo["n_desfechos"] += int(r["n"])
            escopo["valor_desfechos"] += valor
            escopo["mix"][r["canal"]] = escopo["mix"].get(r["canal"], 0) + int(r["n"])
            if r["canal"] == "bancaria":
                escopo["valor_bancaria"] += valor

    agora = datetime.now(UTC)
    linhas: list[RatingLiquidacao] = []
    for (ced, sacado), escopo in pares.items():
        out = _consolidar(escopo, params)
        linhas.append(
            RatingLiquidacao(
                tenant_id=tenant_id,
                cedente_documento=ced,
                cedente_nome=nomes.get(ced),
                sacado_documento=sacado,
                sacado_nome=nomes.get(sacado) if sacado else None,
                formula_version=FORMULA_VERSION,
                calculado_em=agora,
                **out,
            )
        )
    for ced, escopo in cedentes.items():
        out = _consolidar(escopo, params)
        linhas.append(
            RatingLiquidacao(
                tenant_id=tenant_id,
                cedente_documento=ced,
                cedente_nome=nomes.get(ced),
                sacado_documento=None,
                sacado_nome=None,
                formula_version=FORMULA_VERSION,
                calculado_em=agora,
                **out,
            )
        )

    await db.execute(
        delete(RatingLiquidacao).where(RatingLiquidacao.tenant_id == tenant_id)
    )
    db.add_all(linhas)

    resumo = {
        "cedentes": len(cedentes),
        "pares": len(pares),
        "criticos": sum(1 for c in cedentes.values() if c["critico"]),
        "formula_version": FORMULA_VERSION,
        "janela_dias": janela,
    }
    db.add(
        DecisionLog(
            tenant_id=tenant_id,
            decision_type=DecisionType.RECOMMENDATION,
            rule_or_model="rating_liquidacao",
            rule_or_model_version=FORMULA_VERSION,
            inputs_ref={"janela_dias": janela},
            output=resumo,
            explanation=(
                f"rating de integridade de liquidacao recalculado: "
                f"{len(cedentes)} cedentes / {len(pares)} pares, "
                f"{resumo['criticos']} cedentes com sinal critico"
            ),
            triggered_by="system:scheduler",
        )
    )
    await db.commit()
    logger.info("rating_liquidacao: %s", resumo)
    return resumo
