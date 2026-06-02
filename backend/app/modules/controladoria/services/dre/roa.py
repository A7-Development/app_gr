"""ROA bruto 30d -- numerador (DRE + operacoes) / PL medio diario.

Deterministico, silver-only (CLAUDE.md §13.2.1, §14). Nada de LLM no numero.

Numerador (por competencia, por fundo/UA):
    desagio       = receita 'Deságio' de wh_dre_mensal (= total_de_juros das ops)
    prazo_medio   = SUM(prazo_real * valor_base) / SUM(valor_base)  (wh_operacao_item)
                    -> prazo REAL, ponderado por FACE (decisao 2026-06-01)
    desagio_30d   = desagio * 30 / prazo_medio  (normaliza efeito de prazo)
    demais        = receita_operacional_total - desagio  (multa + mora + tarifas)
    numerador     = desagio_30d + demais

Denominador (PL MEDIO DIARIO do mes):
    cotas      = AVG(SUM_classes(patrimonio) por dia) de wh_mec_evolucao_cotas
    debentures = AVG(pl_bruto por dia) de wh_posicao_debenture_dia (por UA)

Gating (sem hardcode de UA): fundo com linhas em wh_posicao_debenture_dia e
"debenture-funded" -> mostra ROA debentures; senao -> ROA cotas (MEC).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.controladoria.schemas.dre import (
    DreRoaCompetencia,
    DreRoaResponse,
)

ZERO = Decimal("0")
_DESAGIO = "Deságio"

# Numerador: desagio + receita operacional total, por competencia, opcional UA.
_SQL_NUMERADOR = """
SELECT date_trunc('month', competencia)::date AS comp,
       COALESCE(SUM(receita) FILTER (WHERE descricao = :desagio), 0) AS desagio,
       COALESCE(SUM(receita), 0) AS receita_total
FROM wh_dre_mensal
WHERE tenant_id = :t
  AND grupo_dre = 'RECEITA_OPERACIONAL'
  AND competencia >= :de AND competencia <= :ate
  AND (:ua IS NULL OR unidade_administrativa_id = :ua)
GROUP BY 1
"""

# Prazo real ponderado por face, das operacoes efetivadas no mes.
_SQL_PRAZO = """
SELECT date_trunc('month', o.data_de_efetivacao)::date AS comp,
       SUM(oi.prazo_real * oi.valor_base) AS num,
       SUM(oi.valor_base) AS den
FROM wh_operacao_item oi
JOIN wh_operacao o
  ON o.operacao_id = oi.operacao_id AND o.tenant_id = oi.tenant_id
WHERE oi.tenant_id = :t
  AND o.efetivada = true
  AND o.data_de_efetivacao >= :de
  AND o.data_de_efetivacao < (:ate + INTERVAL '1 month')
  AND (:ua IS NULL OR o.unidade_administrativa_id = :ua)
GROUP BY 1
"""

# PL cotas medio diario: media dos PLs diarios (soma das classes) por mes.
_SQL_PL_COTAS = """
WITH por_dia AS (
  SELECT data_posicao, SUM(patrimonio) AS pl
  FROM wh_mec_evolucao_cotas
  WHERE tenant_id = :t
    AND data_posicao >= :de
    AND data_posicao < (:ate + INTERVAL '1 month')
  GROUP BY data_posicao
)
SELECT date_trunc('month', data_posicao)::date AS comp, AVG(pl) AS pl_medio
FROM por_dia GROUP BY 1
"""

# PL debentures medio diario por mes (por UA), + origens (proveniencia).
_SQL_PL_DEB = """
SELECT date_trunc('month', data_posicao)::date AS comp,
       AVG(pl_bruto) AS pl_medio,
       array_agg(DISTINCT origem) AS origens
FROM wh_posicao_debenture_dia
WHERE tenant_id = :t
  AND data_posicao >= :de
  AND data_posicao < (:ate + INTERVAL '1 month')
  AND (:ua IS NULL OR unidade_administrativa_id = :ua)
GROUP BY 1
"""


async def compute_roa(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    competencia_de: date,
    competencia_ate: date,
    fundo_id: int | None = None,
) -> DreRoaResponse:
    """ROA bruto 30d por competencia para um fundo (ou todos se fundo_id None)."""
    params = {
        "t": str(tenant_id),
        "de": competencia_de,
        "ate": competencia_ate,
        "ua": fundo_id,
        "desagio": _DESAGIO,
    }

    num_rows = (await db.execute(text(_SQL_NUMERADOR), params)).mappings().all()
    prazo_rows = (await db.execute(text(_SQL_PRAZO), params)).mappings().all()
    cotas_rows = (await db.execute(text(_SQL_PL_COTAS), params)).mappings().all()
    deb_rows = (await db.execute(text(_SQL_PL_DEB), params)).mappings().all()

    desagio_by = {r["comp"]: _dec(r["desagio"]) for r in num_rows}
    receita_by = {r["comp"]: _dec(r["receita_total"]) for r in num_rows}
    prazo_by = {
        r["comp"]: (_dec(r["num"]) / _dec(r["den"]) if r["den"] else ZERO)
        for r in prazo_rows
    }
    pl_cotas_by = {r["comp"]: _dec(r["pl_medio"]) for r in cotas_rows}
    pl_deb_by = {r["comp"]: _dec(r["pl_medio"]) for r in deb_rows}
    deb_origens_by = {r["comp"]: list(r["origens"] or []) for r in deb_rows}

    # Conjunto de competencias = uniao das fontes, dentro do range pedido.
    comps = sorted(
        c
        for c in set(desagio_by) | set(prazo_by) | set(pl_cotas_by) | set(pl_deb_by)
        if competencia_de <= c <= competencia_ate
    )

    out: list[DreRoaCompetencia] = []
    for comp in comps:
        desagio = desagio_by.get(comp, ZERO)
        receita_total = receita_by.get(comp, ZERO)
        prazo = prazo_by.get(comp, ZERO)
        demais = receita_total - desagio

        # Normaliza so o desagio (proporcional ao prazo). Sem prazo -> usa cheio.
        desagio_30d = desagio * Decimal(30) / prazo if prazo > 0 else desagio
        numerador = desagio_30d + demais

        pl_deb = pl_deb_by.get(comp)
        pl_cotas = pl_cotas_by.get(comp)
        is_debenture_fund = pl_deb is not None and pl_deb > 0

        # Gating: fundo capitalizado por debenture nao usa PL cotas e vice-versa.
        if is_debenture_fund:
            pl_cotas = None
        roa_deb = (
            (numerador / pl_deb) if (is_debenture_fund and pl_deb) else None
        )
        roa_cotas = (
            (numerador / pl_cotas)
            if (not is_debenture_fund and pl_cotas and pl_cotas > 0)
            else None
        )

        out.append(
            DreRoaCompetencia(
                competencia=comp,
                desagio=_q2(desagio),
                prazo_medio=_q4(prazo),
                desagio_30d=_q2(desagio_30d),
                demais_receitas=_q2(demais),
                numerador=_q2(numerador),
                pl_cotas_medio=_q2(pl_cotas) if pl_cotas is not None else None,
                pl_debentures_medio=_q2(pl_deb) if pl_deb is not None else None,
                roa_cotas_30d=_q6(roa_cotas) if roa_cotas is not None else None,
                roa_debentures_30d=_q6(roa_deb) if roa_deb is not None else None,
                pl_debentures_origens=deb_origens_by.get(comp, []),
            )
        )

    return DreRoaResponse(
        competencia_de=competencia_de,
        competencia_ate=competencia_ate,
        fundo_id=fundo_id,
        competencias=out,
    )


def _dec(v: object) -> Decimal:
    return Decimal(str(v)) if v is not None else ZERO


def _q2(v: Decimal | None) -> Decimal | None:
    return None if v is None else v.quantize(Decimal("0.01"))


def _q4(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.0001"))


def _q6(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.000001"))
