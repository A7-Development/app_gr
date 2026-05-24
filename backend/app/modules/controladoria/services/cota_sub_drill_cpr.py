"""Controladoria · Cota Sub · drill CPR (F2 do redesign, 2026-05-23).

Decompoe a categoria CPR (Contas a Pagar e Receber) do Balance hero em:

  1. Totais D-1 / D0 / delta            - sum wh_cpr_movimento (sinal natural)
  2. Agrupamento por natureza           - classifica cada rubrica em uma
     de 7 buckets via regex sobre `descricao`/`historico_traduzido`:
       . diferimento          - 'Diferimento de despesa%'
       . apropriacao_taxa     - 'Taxa de % Apropriada'
       . apropriacao_despesa  - 'Despesa de %', 'Despesas com %', '% a Pagar%',
                                REGISTRADORA%
       . iof_ir               - 'IOF a Recolher%', 'IR a Recolher%'
       . provisao_liquidacao  - 'LIQUIDADOS TOTAL - PROV' (provisao de
                                receita por liquidacoes do dia)
       . aporte_engaiolado    - descricao iniciando em 'Aporte%'
       . outros               - residual (rubricas sem mapping)
  3. Aportes engaiolados rastreados     - listagem de aportes com transicao
                                          (entrou, devolvido, persiste).

Refinamento 2026-05-23 pos-smoke (F2):
  - Adicionada natureza `provisao_liquidacao` apos descobrir que
    `LIQUIDADOS TOTAL - PROV` (caso pedagogico, ver memo redesign)
    estava caindo em `Outros`.
  - Detector de aporte engaiolado refeito: a heuristica antiga procurava
    par (Aporte, Provisao Devolucao) no mesmo dia, mas a query empirica
    confirmou que NAO existe rubrica de provisao pareada no CPR.  O que
    de fato acontece e o aporte aparecer sozinho com valor negativo e
    persistir por N dias uteis ate ser devolvido/integralizado.

Sub absorve todo movimento de CPR - sinais NAO sao invertidos aqui (despesa
no CPR vira negativo, receita positivo; UI interpreta).
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub_drill import (
    CprNaturezaKey,
    DrillCprAporteEngaiolado,
    DrillCprLinha,
    DrillCprNaturezaGroup,
    DrillCprResponse,
)
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.cpr_movimento import CprMovimento

ZERO = Decimal("0")

_TOP_LINHAS_POR_NATUREZA = 10
_THRESHOLD_APORTE_BRL = Decimal("100")  # magnitude minima pra rastrear aporte

# Labels pt-BR exibidos na UI.
_NATUREZA_LABEL: dict[CprNaturezaKey, str] = {
    "diferimento":         "Diferimento de despesa",
    "apropriacao_taxa":    "Taxa apropriada (Adm/Custodia/Gestao)",
    "apropriacao_despesa": "Despesa apropriada (Auditoria/Consultoria/Cobranca)",
    "iof_ir":              "IOF / IR a recolher",
    "provisao_liquidacao": "Provisao de liquidacoes (LIQUIDADOS TOTAL - PROV)",
    "aporte_engaiolado":   "Aporte engaiolado",
    "outros":              "Outros",
}

# Ordem fixa de apresentacao (maior absorbencia primeiro).
_NATUREZA_ORDER: tuple[CprNaturezaKey, ...] = (
    "diferimento",
    "apropriacao_taxa",
    "apropriacao_despesa",
    "iof_ir",
    "provisao_liquidacao",
    "aporte_engaiolado",
    "outros",
)

# Regex pre-compilados sobre descricao/historico_traduzido (case-insensitive).
_RX_DIFERIMENTO = re.compile(r"diferimento\s+de\s+despesa", re.IGNORECASE)
_RX_TAXA_APROP = re.compile(r"taxa\s+de\s+.*\s+apropriada", re.IGNORECASE)
_RX_DESPESA_DE = re.compile(r"^despesa(s)?\s+(de|com)\s+", re.IGNORECASE)
_RX_A_PAGAR = re.compile(r"\s+a\s+pagar\s+em\s+", re.IGNORECASE)
_RX_REGISTRADORA = re.compile(r"^registradora", re.IGNORECASE)
_RX_IOF = re.compile(r"^iof\s+a\s+recolher", re.IGNORECASE)
_RX_IR = re.compile(r"^ir\s+a\s+recolher", re.IGNORECASE)
_RX_APORTE = re.compile(r"^aporte\b", re.IGNORECASE)
_RX_LIQUIDADOS_TOTAL_PROV = re.compile(
    r"^liquidados\s+total\s*-\s*prov", re.IGNORECASE,
)


def _classificar(descricao: str, historico_traduzido: str) -> CprNaturezaKey:
    """Aplica regex em ordem de especificidade. Primeiro match vence."""
    texto = f"{descricao} {historico_traduzido}".strip()

    if _RX_DIFERIMENTO.search(texto):
        return "diferimento"
    if _RX_IOF.search(texto) or _RX_IR.search(texto):
        return "iof_ir"
    if _RX_LIQUIDADOS_TOTAL_PROV.search(texto):
        return "provisao_liquidacao"
    if _RX_TAXA_APROP.search(texto):
        return "apropriacao_taxa"
    if _RX_DESPESA_DE.search(texto) or _RX_A_PAGAR.search(texto) or _RX_REGISTRADORA.search(texto):
        return "apropriacao_despesa"
    if _RX_APORTE.search(texto):
        return "aporte_engaiolado"
    return "outros"


async def _linhas_cpr_pivotadas(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d1: date,
    data_d0: date,
) -> list[DrillCprLinha]:
    """Lista (descricao, historico) com valor D-1 e D0 numa unica query.

    Agregamos por (descricao, historico_traduzido) — mesmo nivel que o
    `_cpr_diff_by_descricao` ja existente. Sem threshold aqui (deixamos
    a UI agrupar tudo; threshold so pra top N dentro do grupo).
    """
    d1q = (
        select(
            CprMovimento.descricao,
            CprMovimento.historico_traduzido,
            func.sum(CprMovimento.valor).label("valor"),
        )
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data_d1)
        .group_by(CprMovimento.descricao, CprMovimento.historico_traduzido)
        .subquery()
    )
    d0q = (
        select(
            CprMovimento.descricao,
            CprMovimento.historico_traduzido,
            func.sum(CprMovimento.valor).label("valor"),
        )
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data_d0)
        .group_by(CprMovimento.descricao, CprMovimento.historico_traduzido)
        .subquery()
    )

    valor_d1 = func.coalesce(d1q.c.valor, ZERO)
    valor_d0 = func.coalesce(d0q.c.valor, ZERO)

    stmt = select(
        func.coalesce(d0q.c.descricao, d1q.c.descricao).label("descricao"),
        func.coalesce(
            d0q.c.historico_traduzido, d1q.c.historico_traduzido
        ).label("historico_traduzido"),
        valor_d1.label("valor_d1"),
        valor_d0.label("valor_d0"),
    ).select_from(
        d0q.join(d1q, d0q.c.descricao == d1q.c.descricao, full=True)
    )

    rows = (await db.execute(stmt)).all()

    linhas: list[DrillCprLinha] = []
    for r in rows:
        desc = r.descricao or ""
        hist = r.historico_traduzido or desc
        v_d1 = Decimal(r.valor_d1 or 0)
        v_d0 = Decimal(r.valor_d0 or 0)
        linhas.append(
            DrillCprLinha(
                descricao=desc,
                historico_traduzido=hist,
                valor_d1=v_d1,
                valor_d0=v_d0,
                delta_valor=v_d0 - v_d1,
                natureza=_classificar(desc, hist),
            )
        )
    return linhas


def _detectar_aportes_engaiolados(
    linhas: list[DrillCprLinha],
) -> list[DrillCprAporteEngaiolado]:
    """Rastreia rubricas `Aporte%` no CPR e classifica transicao D-1 -> D0.

    Refatorado em 2026-05-23 apos validacao empirica em REALINVEST: NAO
    existe rubrica `Provisao Devolucao` pareando o aporte no mesmo dia
    (ver memo F2). O detector entao apenas rastreia a transicao da
    rubrica `Aporte` em si:

      - `entrou`     : magnitude > threshold em D0, < threshold em D-1
      - `devolvido`  : magnitude > threshold em D-1, < threshold em D0
      - `persiste`   : magnitude > threshold em ambos
    """
    eventos: list[DrillCprAporteEngaiolado] = []
    for ln in linhas:
        if not _RX_APORTE.search(ln.descricao or ""):
            continue
        em_d1 = abs(ln.valor_d1) > _THRESHOLD_APORTE_BRL
        em_d0 = abs(ln.valor_d0) > _THRESHOLD_APORTE_BRL
        if not em_d1 and not em_d0:
            continue
        if em_d0 and not em_d1:
            estado: Literal["entrou", "devolvido", "persiste"] = "entrou"
        elif em_d1 and not em_d0:
            estado = "devolvido"
        else:
            estado = "persiste"
        eventos.append(
            DrillCprAporteEngaiolado(
                descricao=ln.descricao,
                estado=estado,
                valor_d1=ln.valor_d1,
                valor_d0=ln.valor_d0,
                delta_valor=ln.delta_valor,
            )
        )
    return eventos


async def compute_drill_cpr(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> DrillCprResponse:
    """Drill CPR: totais + agrupamento por natureza + aportes engaiolados."""
    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada")

    d1 = data_d1 or await dia_util_anterior_qitech(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    linhas = await _linhas_cpr_pivotadas(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d1=d1, data_d0=data_d0,
    )

    # ── Totais
    total_d1 = sum((ln.valor_d1 for ln in linhas), ZERO)
    total_d0 = sum((ln.valor_d0 for ln in linhas), ZERO)
    qtd_d1 = sum(1 for ln in linhas if ln.valor_d1 != ZERO)
    qtd_d0 = sum(1 for ln in linhas if ln.valor_d0 != ZERO)

    # ── Agrupa por natureza
    por_natureza: dict[CprNaturezaKey, list[DrillCprLinha]] = defaultdict(list)
    for ln in linhas:
        por_natureza[ln.natureza].append(ln)

    naturezas: list[DrillCprNaturezaGroup] = []
    for natureza in _NATUREZA_ORDER:
        bucket = por_natureza.get(natureza, [])
        if not bucket:
            continue
        # Ordena top lines por |delta| DESC.
        bucket_sorted = sorted(bucket, key=lambda ln: abs(ln.delta_valor), reverse=True)
        top = bucket_sorted[:_TOP_LINHAS_POR_NATUREZA]
        naturezas.append(
            DrillCprNaturezaGroup(
                natureza=natureza,
                label=_NATUREZA_LABEL[natureza],
                qtd_linhas=len(bucket),
                sum_valor_d1=sum((ln.valor_d1 for ln in bucket), ZERO),
                sum_valor_d0=sum((ln.valor_d0 for ln in bucket), ZERO),
                sum_delta=sum((ln.delta_valor for ln in bucket), ZERO),
                top_linhas=top,
            )
        )

    aportes_engaiolados = _detectar_aportes_engaiolados(linhas)

    return DrillCprResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        cpr_total_d1=total_d1,
        cpr_total_d0=total_d0,
        cpr_total_delta=total_d0 - total_d1,
        qtd_linhas_d1=qtd_d1,
        qtd_linhas_d0=qtd_d0,
        naturezas=naturezas,
        aportes_engaiolados=aportes_engaiolados,
    )
