"""Controladoria · Lamina mensal do FIDC -- service.

Computa o payload da lamina (3 paginas) a partir das silver alimentadas pela
QiTech, escopado por `tenant_id` + Unidade Administrativa (FIDC) + competencia
fechada. Fontes (CLAUDE.md §13.2.1):

    - wh_mec_evolucao_cotas    -- PL/cota/variacoes por classe (heuristica
                                  `_classificar` reusada da Evolucao Patrimonial).
    - wh_rentabilidade_fundo   -- retorno do CDI (indexador='CDI').
    - wh_estoque_recebivel     -- aging (a vencer/vencido), PDD, concentracao.
    - wh_saldo_conta_corrente  -- caixa.

Competencia: SEMPRE um mes fechado (anterior ao mes corrente) com posicao de
fim de mes na silver. A parcial do mes corrente nunca e oferecida (convencao de
mercado); pedir o mes corrente cai para a ultima competencia fechada.

Os arrays mensais (12 pontos) sao devolvidos crus; o frontend deriva acumulados
/ %CDI / razao de garantia (transformacoes puras sobre dado auditavel).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import bindparam, case, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.evolucao_patrimonial import ClasseCota
from app.modules.controladoria.schemas.lamina import (
    AgingSerie,
    ClasseSerie,
    CompetenciaItem,
    CompetenciasResponse,
    Concentracao,
    ConcentracaoHistorico,
    ConcentracaoItem,
    LaminaResponse,
    Proveniencia,
)
from app.modules.controladoria.services.evolucao_patrimonial import _classificar, _f
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.rentabilidade_fundo import RentabilidadeFundo
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente

_WINDOW = 12
_CLASSE_LABEL: dict[ClasseCota, str] = {
    "sub": "Subordinada",
    "mez": "Mezanino",
    "sr": "Sênior",
}
# Ordem de exibicao na lamina: Senior, Mezanino, Subordinada.
_CLASSE_ORDER: list[ClasseCota] = ["sr", "mez", "sub"]

_MES_ABBR = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
]
_MES_NOME = [
    "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de competencia / janela
# ─────────────────────────────────────────────────────────────────────────────


def _mes_label(y: int, m: int) -> str:
    return f"{_MES_ABBR[m - 1]}/{y % 100:02d}"


def _competencia_str(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}"


def _competencia_label(y: int, m: int) -> str:
    return f"{_MES_NOME[m - 1]} / {y}"


def _parse_competencia(s: str) -> tuple[int, int] | None:
    try:
        y, m = s.split("-")
        yi, mi = int(y), int(m)
        if 1 <= mi <= 12:
            return (yi, mi)
    except (ValueError, AttributeError):
        pass
    return None


def _prev_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


def _window_months(cy: int, cm: int, n: int = _WINDOW) -> list[tuple[int, int]]:
    """Os `n` meses terminando em (cy, cm), em ordem cronologica crescente."""
    out: list[tuple[int, int]] = []
    y, m = cy, cm
    for _ in range(n):
        out.append((y, m))
        y, m = _prev_month(y, m)
    return list(reversed(out))


def _month_first(y: int, m: int) -> date:
    return date(y, m, 1)


def _month_last(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


# ─────────────────────────────────────────────────────────────────────────────
# Resolucao do fundo (Unidade Administrativa)
# ─────────────────────────────────────────────────────────────────────────────


async def _resolve_ua(
    db: AsyncSession, *, tenant_id: UUID, fundo_id: UUID | None
) -> UnidadeAdministrativa:
    """Resolve a UA do FIDC. Sem `fundo_id`, escolhe a 1a UA tipo='fidc'."""
    stmt = select(UnidadeAdministrativa).where(
        UnidadeAdministrativa.tenant_id == tenant_id
    )
    if fundo_id is not None:
        stmt = stmt.where(UnidadeAdministrativa.id == fundo_id)
    uas = (await db.execute(stmt)).scalars().all()
    if not uas:
        raise ValueError("Nenhuma Unidade Administrativa encontrada para o tenant.")
    if fundo_id is not None:
        return uas[0]
    fidcs = [
        u for u in uas
        if str(getattr(u.tipo, "value", u.tipo)).lower() == "fidc"
    ]
    return (fidcs or uas)[0]


async def _resolve_fundo_doc(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID
) -> str | None:
    """CNPJ do fundo a partir do MEC (carteira_cliente_doc) -- robusto contra
    divergencia de CNPJ no cadastro da UA."""
    return (
        await db.execute(
            select(MecEvolucaoCotas.carteira_cliente_doc)
            .where(MecEvolucaoCotas.tenant_id == tenant_id)
            .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def _competencias_fechadas(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, hoje: date
) -> list[tuple[int, int, date]]:
    """Meses com MEC publicado, anteriores ao mes corrente, desc.

    Retorna (ano, mes, posicao) onde posicao = ultimo dia com dado no mes.
    """
    datas = (
        (
            await db.execute(
                select(distinct(MecEvolucaoCotas.data_posicao))
                .where(MecEvolucaoCotas.tenant_id == tenant_id)
                .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
            )
        )
        .scalars()
        .all()
    )
    by_month: dict[tuple[int, int], date] = {}
    for d in datas:
        ym = (d.year, d.month)
        if ym >= (hoje.year, hoje.month):
            continue  # mes corrente/futuro = nao fechado
        if ym not in by_month or d > by_month[ym]:
            by_month[ym] = d
    return sorted(
        ((y, m, pos) for (y, m), pos in by_month.items()), reverse=True
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: lista de competencias fechadas
# ─────────────────────────────────────────────────────────────────────────────


async def list_competencias(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_id: UUID | None,
    hoje: date | None = None,
) -> CompetenciasResponse:
    hoje = hoje or date.today()
    ua = await _resolve_ua(db, tenant_id=tenant_id, fundo_id=fundo_id)
    fechadas = await _competencias_fechadas(
        db, tenant_id=tenant_id, ua_id=ua.id, hoje=hoje
    )
    return CompetenciasResponse(
        fundo_id=str(ua.id),
        fundo_nome=ua.nome,
        competencias=[
            CompetenciaItem(
                competencia=_competencia_str(y, m),
                label=_competencia_label(y, m),
                posicao=pos,
            )
            for (y, m, pos) in fechadas
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: lamina completa
# ─────────────────────────────────────────────────────────────────────────────


async def compute_lamina(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_id: UUID | None,
    competencia: str | None = None,
    hoje: date | None = None,
) -> LaminaResponse:
    hoje = hoje or date.today()
    ua = await _resolve_ua(db, tenant_id=tenant_id, fundo_id=fundo_id)
    ua_nome = ua.nome

    fechadas = await _competencias_fechadas(
        db, tenant_id=tenant_id, ua_id=ua.id, hoje=hoje
    )
    if not fechadas:
        raise ValueError(
            f"Sem competencia fechada com dados MEC para o fundo {ua_nome}."
        )
    fechadas_idx = {(y, m): pos for (y, m, pos) in fechadas}

    # Resolve a competencia alvo: pedida (se fechada) OU a ultima fechada.
    alvo = _parse_competencia(competencia) if competencia else None
    if alvo is None or alvo not in fechadas_idx:
        cy, cm, posicao = fechadas[0]  # ultima fechada
    else:
        cy, cm = alvo
        posicao = fechadas_idx[alvo]

    fundo_doc = await _resolve_fundo_doc(db, tenant_id=tenant_id, ua_id=ua.id)
    if fundo_doc is None:
        raise ValueError(f"Sem CNPJ de fundo (MEC) para {ua_nome}.")

    window = _window_months(cy, cm, _WINDOW)
    meses = [_mes_label(y, m) for (y, m) in window]

    # ---- MEC: fotos de fim de mes por classe (+ 1 mes anterior p/ detectar parcial) ----
    lo = _month_first(*_prev_month(*window[0]))
    hi = _month_last(cy, cm)
    mec_rows = (
        (
            await db.execute(
                select(MecEvolucaoCotas)
                .where(MecEvolucaoCotas.tenant_id == tenant_id)
                .where(MecEvolucaoCotas.unidade_administrativa_id == ua.id)
                .where(MecEvolucaoCotas.data_posicao >= lo)
                .where(MecEvolucaoCotas.data_posicao <= hi)
                .order_by(MecEvolucaoCotas.data_posicao.asc())
            )
        )
        .scalars()
        .all()
    )

    by_month_class: dict[tuple[int, int], dict[ClasseCota, MecEvolucaoCotas]] = (
        defaultdict(dict)
    )
    present: dict[ClasseCota, set[tuple[int, int]]] = defaultdict(set)
    max_source_updated: object | None = None
    for row in mec_rows:
        if row.patrimonio == 0 and row.quantidade == 0 and row.valor_da_cota == 0:
            continue  # buraco de publicacao QiTech ("MEC zerada")
        classe = _classificar(row.carteira_cliente_nome, ua_nome)
        if classe is None:
            continue
        ym = (row.data_posicao.year, row.data_posicao.month)
        present[classe].add(ym)
        cur = by_month_class[ym].get(classe)
        if cur is None or row.data_posicao > cur.data_posicao:
            by_month_class[ym][classe] = row
        if row.source_updated_at is not None and (
            max_source_updated is None or row.source_updated_at > max_source_updated
        ):
            max_source_updated = row.source_updated_at

    classes_presentes = [
        c for c in _CLASSE_ORDER if any(c in by_month_class.get(ym, {}) for ym in window)
    ]
    if not classes_presentes:
        raise ValueError(
            f"Sem dados de cota MEC para {ua_nome} na competencia {_competencia_str(cy, cm)}."
        )

    classes: list[ClasseSerie] = []
    for c in classes_presentes:
        var_mensal: list[float | None] = []
        patrimonio: list[float] = []
        for ym in window:
            row = by_month_class.get(ym, {}).get(c)
            if row is None:
                var_mensal.append(None)
                patrimonio.append(0.0)
                continue
            patrimonio.append(_f(row.patrimonio))
            # Mes parcial de constituicao (sem mes anterior) -> retorno nao exibido.
            var_mensal.append(
                _f(row.variacao_mensal) if _prev_month(*ym) in present[c] else None
            )
        last = by_month_class.get(window[-1], {}).get(c)
        classes.append(
            ClasseSerie(
                classe=c,
                label=_CLASSE_LABEL[c],
                var_mensal=var_mensal,
                patrimonio=patrimonio,
                quantidade=_f(last.quantidade) if last else 0.0,
                valor_cota=_f(last.valor_da_cota) if last else 0.0,
                variacao_total=_f(last.variacao_total) if last else 0.0,
            )
        )

    last_month_rows = by_month_class.get(window[-1], {})
    pl_total = round(
        sum(_f(row.patrimonio) for row in last_month_rows.values()), 2
    )

    # ---- CDI mensal (retorno do proprio CDI por mes) ----
    rent_rows = (

            await db.execute(
                select(
                    RentabilidadeFundo.data_posicao,
                    RentabilidadeFundo.rentabilidade_mensal,
                )
                .where(RentabilidadeFundo.tenant_id == tenant_id)
                .where(RentabilidadeFundo.unidade_administrativa_id == ua.id)
                .where(RentabilidadeFundo.indexador == "CDI")
                .where(RentabilidadeFundo.data_posicao >= lo)
                .where(RentabilidadeFundo.data_posicao <= hi)
                .order_by(RentabilidadeFundo.data_posicao.asc())
            )

    ).all()
    # Por mes, ancora na ULTIMA data (fim de mes). Nessa data ha 1 linha de CDI
    # por classe; a de uma classe constituida no meio do mes traz o CDI parcial
    # (periodo curto) -- por isso tomamos o MAIOR rentabilidade_mensal na data,
    # que e o retorno do CDI do mes cheio.
    cdi_by_month: dict[tuple[int, int], tuple[date, float]] = {}
    for d, rm in rent_rows:
        if rm is None:
            continue
        ym = (d.year, d.month)
        val = float(rm)
        prev = cdi_by_month.get(ym)
        if prev is None or d > prev[0] or (d == prev[0] and val > prev[1]):
            cdi_by_month[ym] = (d, val)
    cdi = [cdi_by_month.get(ym, (None, 0.0))[1] for ym in window]

    # ---- Estoque: datas de fim de mes (por fundo_doc) ----
    est_datas = (
        (
            await db.execute(
                select(distinct(EstoqueRecebivel.data_referencia))
                .where(EstoqueRecebivel.tenant_id == tenant_id)
                .where(EstoqueRecebivel.fundo_doc == fundo_doc)
                .where(EstoqueRecebivel.data_referencia >= _month_first(*window[0]))
                .where(EstoqueRecebivel.data_referencia <= hi)
            )
        )
        .scalars()
        .all()
    )
    est_month_date: dict[tuple[int, int], date] = {}
    for d in est_datas:
        ym = (d.year, d.month)
        if ym not in est_month_date or d > est_month_date[ym]:
            est_month_date[ym] = d
    est_dates = list(est_month_date.values())

    aging = await _aging(db, tenant_id, fundo_doc, window, est_month_date, est_dates)
    caixa = await _caixa(db, tenant_id, fundo_doc, window)
    concentracao = await _concentracao(
        db, tenant_id, fundo_doc, window, est_month_date, est_dates
    )

    # ---- Cadastrais que a QiTech entrega (gestor/originador) ----
    cad = None
    latest_est = est_month_date.get(window[-1])
    if latest_est is not None:
        cad = (
            await db.execute(
                select(
                    EstoqueRecebivel.gestor_nome,
                    EstoqueRecebivel.originador_nome,
                )
                .where(EstoqueRecebivel.tenant_id == tenant_id)
                .where(EstoqueRecebivel.fundo_doc == fundo_doc)
                .where(EstoqueRecebivel.data_referencia == latest_est)
                .limit(1)
            )
        ).first()

    return LaminaResponse(
        fundo_id=str(ua.id),
        fundo_nome=ua_nome,
        cnpj=fundo_doc,
        gestor_nome=cad[0] if cad else None,
        originador_nome=cad[1] if cad else None,
        competencia=_competencia_str(cy, cm),
        competencia_label=_competencia_label(cy, cm),
        posicao=posicao,
        meses=meses,
        cdi=cdi,
        classes=classes,
        pl_total=pl_total,
        aging=AgingSerie(**aging, caixa=caixa),
        concentracao=concentracao,
        proveniencia=Proveniencia(atualizado_em=max_source_updated),  # type: ignore[arg-type]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Agregados de estoque / caixa / concentracao
# ─────────────────────────────────────────────────────────────────────────────


async def _aging(
    db: AsyncSession,
    tenant_id: UUID,
    fundo_doc: str,
    window: list[tuple[int, int]],
    est_month_date: dict[tuple[int, int], date],
    est_dates: list[date],
) -> dict[str, list[float]]:
    """A vencer / vencido / PDD por mes (fim de mes). A vencer = total - vencido.

    Exclui a faixa 'WOP' (Write-Off Papers -- papeis baixados, 100%
    provisionados) tanto da carteira quanto do PDD: a lamina mede a carteira
    ativa e PDD/PL ex-WOP (indicador oficial do gestor).
    """
    by_date: dict[date, tuple[float, float, float]] = {}
    if est_dates:
        rows = (
            await db.execute(
                select(
                    EstoqueRecebivel.data_referencia,
                    func.sum(EstoqueRecebivel.valor_presente).label("total"),
                    func.sum(
                        case(
                            (
                                EstoqueRecebivel.situacao_recebivel == "Vencido",
                                EstoqueRecebivel.valor_presente,
                            ),
                            else_=0,
                        )
                    ).label("vencido"),
                    func.sum(EstoqueRecebivel.valor_pdd).label("pdd"),
                )
                .where(EstoqueRecebivel.tenant_id == tenant_id)
                .where(EstoqueRecebivel.fundo_doc == fundo_doc)
                .where(EstoqueRecebivel.faixa_pdd != "WOP")
                .where(EstoqueRecebivel.data_referencia.in_(est_dates))
                .group_by(EstoqueRecebivel.data_referencia)
            )
        ).all()
        for d, total, venc, pdd in rows:
            by_date[d] = (float(total or 0), float(venc or 0), float(pdd or 0))

    a_vencer: list[float] = []
    vencido: list[float] = []
    pdd_l: list[float] = []
    for ym in window:
        ed = est_month_date.get(ym)
        total, venc, pdd = by_date.get(ed, (0.0, 0.0, 0.0)) if ed else (0.0, 0.0, 0.0)
        a_vencer.append(round(total - venc, 2))
        vencido.append(round(venc, 2))
        pdd_l.append(round(pdd, 2))
    return {"a_vencer": a_vencer, "vencido": vencido, "pdd": pdd_l}


async def _caixa(
    db: AsyncSession,
    tenant_id: UUID,
    fundo_doc: str,
    window: list[tuple[int, int]],
) -> list[float]:
    """Caixa por mes (saldo de conta corrente positivo, fim de mes)."""
    datas = (
        (
            await db.execute(
                select(distinct(SaldoContaCorrente.data_posicao))
                .where(SaldoContaCorrente.tenant_id == tenant_id)
                .where(SaldoContaCorrente.carteira_cliente_doc == fundo_doc)
                .where(SaldoContaCorrente.data_posicao >= _month_first(*window[0]))
                .where(SaldoContaCorrente.data_posicao <= _month_last(*window[-1]))
            )
        )
        .scalars()
        .all()
    )
    month_date: dict[tuple[int, int], date] = {}
    for d in datas:
        ym = (d.year, d.month)
        if ym not in month_date or d > month_date[ym]:
            month_date[ym] = d
    dates = list(month_date.values())

    by_date: dict[date, float] = {}
    if dates:
        rows = (
            await db.execute(
                select(
                    SaldoContaCorrente.data_posicao,
                    func.sum(
                        case(
                            (
                                SaldoContaCorrente.valor_total > 0,
                                SaldoContaCorrente.valor_total,
                            ),
                            else_=0,
                        )
                    ).label("caixa"),
                )
                .where(SaldoContaCorrente.tenant_id == tenant_id)
                .where(SaldoContaCorrente.carteira_cliente_doc == fundo_doc)
                .where(SaldoContaCorrente.data_posicao.in_(dates))
                .group_by(SaldoContaCorrente.data_posicao)
            )
        ).all()
        for d, caixa in rows:
            by_date[d] = float(caixa or 0)

    out: list[float] = []
    for ym in window:
        d = month_date.get(ym)
        out.append(round(by_date.get(d, 0.0), 2) if d else 0.0)
    return out


# Razao maior/top10 por data, em % do total do estoque na data.
_CONC_SQL = """
WITH g AS (
    SELECT data_referencia, {dim} AS k, SUM(valor_presente) AS fin
    FROM wh_estoque_recebivel
    WHERE tenant_id = :tenant AND fundo_doc = :fundo
      AND data_referencia IN :dates
    GROUP BY data_referencia, {dim}
), r AS (
    SELECT data_referencia, fin,
           SUM(fin) OVER (PARTITION BY data_referencia) AS tot,
           ROW_NUMBER() OVER (PARTITION BY data_referencia ORDER BY fin DESC) AS rn
    FROM g
)
SELECT data_referencia,
       MAX(fin) FILTER (WHERE rn = 1) / NULLIF(MAX(tot), 0) * 100 AS maior,
       SUM(fin) FILTER (WHERE rn <= 10) / NULLIF(MAX(tot), 0) * 100 AS top10
FROM r GROUP BY data_referencia
"""


async def _conc_hist_dim(
    db: AsyncSession,
    tenant_id: UUID,
    fundo_doc: str,
    dim: str,
    est_month_date: dict[tuple[int, int], date],
    window: list[tuple[int, int]],
    est_dates: list[date],
) -> tuple[list[float], list[float]]:
    by_date: dict[date, tuple[float, float]] = {}
    if est_dates:
        stmt = text(_CONC_SQL.format(dim=dim)).bindparams(
            bindparam("dates", expanding=True)
        )
        rows = (
            await db.execute(
                stmt, {"tenant": tenant_id, "fundo": fundo_doc, "dates": est_dates}
            )
        ).all()
        for d, maior, top10 in rows:
            by_date[d] = (float(maior or 0), float(top10 or 0))
    maior_l: list[float] = []
    top10_l: list[float] = []
    for ym in window:
        ed = est_month_date.get(ym)
        maior, top10 = by_date.get(ed, (0.0, 0.0)) if ed else (0.0, 0.0)
        maior_l.append(round(maior, 1))
        top10_l.append(round(top10, 1))
    return maior_l, top10_l


async def _concentracao(
    db: AsyncSession,
    tenant_id: UUID,
    fundo_doc: str,
    window: list[tuple[int, int]],
    est_month_date: dict[tuple[int, int], date],
    est_dates: list[date],
) -> Concentracao:
    latest = est_month_date.get(window[-1])

    async def _top10(dim_col: object) -> list[ConcentracaoItem]:
        if latest is None:
            return []
        rows = (
            await db.execute(
                select(dim_col, func.sum(EstoqueRecebivel.valor_presente).label("fin"))
                .where(EstoqueRecebivel.tenant_id == tenant_id)
                .where(EstoqueRecebivel.fundo_doc == fundo_doc)
                .where(EstoqueRecebivel.data_referencia == latest)
                .group_by(dim_col)
                .order_by(func.sum(EstoqueRecebivel.valor_presente).desc())
                .limit(10)
            )
        ).all()
        return [
            ConcentracaoItem(posicao=i + 1, financeiro=round(float(r.fin or 0), 2))
            for i, r in enumerate(rows)
        ]

    cedentes = await _top10(EstoqueRecebivel.cedente_doc)
    sacados = await _top10(EstoqueRecebivel.sacado_doc)
    ced_maior, ced_top10 = await _conc_hist_dim(
        db, tenant_id, fundo_doc, "cedente_doc", est_month_date, window, est_dates
    )
    sac_maior, sac_top10 = await _conc_hist_dim(
        db, tenant_id, fundo_doc, "sacado_doc", est_month_date, window, est_dates
    )
    return Concentracao(
        cedentes=cedentes,
        sacados=sacados,
        historico=ConcentracaoHistorico(
            cedente_maior=ced_maior,
            cedente_top10=ced_top10,
            sacado_maior=sac_maior,
            sacado_top10=sac_top10,
        ),
    )
