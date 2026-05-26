"""Controladoria · Evolucao Patrimonial -- service.

Monta a serie temporal da evolucao do PL do passivo do FIDC (todas as
classes de cota) a partir de duas tabelas silver (CLAUDE.md §13.2.1):

    - wh_mec_evolucao_cotas   -- PL, quantidade, valor da cota, fluxo e
                                  variacoes % por (data, classe).
    - wh_rentabilidade_fundo  -- % do CDI, rentabilidade real e o retorno do
                                  proprio CDI (indexador='CDI'), por (data, classe).

Escopo multi-tenant (CLAUDE.md §10): toda query filtra `tenant_id` +
`unidade_administrativa_id` antes de qualquer outra condicao -- mesmo padrao
do cota_sub. A classe (Sub/Mez/Sr) e identificada por heuristica sobre
`carteira_cliente_nome` (convencao QiTech validada com REALINVEST FIDC).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.evolucao_patrimonial import (
    ClasseCota,
    ClasseInfo,
    EvolucaoPatrimonialResponse,
    Granularidade,
    KpiResumo,
    Proveniencia,
    ResumoClasse,
    SeriePonto,
    SeriePontoClasse,
)
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.rentabilidade_fundo import RentabilidadeFundo

_CLASSE_LABEL: dict[ClasseCota, str] = {
    "sub": "Subordinada",
    "mez": "Mezanino",
    "sr": "Senior",
}
# Ordem canonica de exibicao (senior no topo da pilha, sub na base).
_CLASSE_ORDER: list[ClasseCota] = ["sr", "mez", "sub"]


# ─────────────────────────────────────────────────────────────────────────────
# Heuristica de classificacao (mesma convencao do cota_sub.py)
# ─────────────────────────────────────────────────────────────────────────────


def _norm(s: str | None) -> str:
    return (s or "").strip().upper()


def _classificar(carteira_nome: str, ua_nome: str) -> ClasseCota | None:
    """carteira_cliente_nome -> classe.

    Convencao QiTech (validada REALINVEST FIDC, 2026-04-23):
        Sub Jr:   `clienteNome` == nome cru do fundo (== nome da UA)
        Mezanino: contem 'MEZANINO'
        Senior:   contem 'SENIOR'
    """
    n = _norm(carteira_nome)
    if "MEZANINO" in n:
        return "mez"
    if "SENIOR" in n:
        return "sr"
    if n == _norm(ua_nome):
        return "sub"
    return None


def _f(v: Decimal | float | None) -> float:
    return float(v) if v is not None else 0.0


def _shift_12m(d: date) -> date:
    """Mesmo dia 12 meses antes ('12M corridos'). Trata 29/fev -> 28/fev."""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


# ─────────────────────────────────────────────────────────────────────────────
# Estruturas internas
# ─────────────────────────────────────────────────────────────────────────────


class _MecPonto:
    """Snapshot de uma classe num dia (acumula fluxos quando agregado por mes)."""

    __slots__ = (
        "entradas",
        "patrimonio",
        "quantidade",
        "saidas",
        "valor_cota",
        "variacao_diaria",
        "variacao_mensal",
    )

    def __init__(self, row: MecEvolucaoCotas) -> None:
        self.patrimonio = _f(row.patrimonio)
        self.quantidade = _f(row.quantidade)
        self.valor_cota = _f(row.valor_da_cota)
        self.variacao_diaria = _f(row.variacao_diaria)
        self.variacao_mensal = _f(row.variacao_mensal)
        self.entradas = _f(row.entradas)
        self.saidas = _f(row.saidas)


# ─────────────────────────────────────────────────────────────────────────────
# Service principal
# ─────────────────────────────────────────────────────────────────────────────


async def compute_evolucao_patrimonial(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    periodo_inicio: date | None = None,
    periodo_fim: date | None = None,
    granularidade: Granularidade = "mensal",
    classes_filtro: list[ClasseCota] | None = None,
) -> EvolucaoPatrimonialResponse:
    # 1. Resolve UA (nome -> classificacao Sub + titulo da pagina).
    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada.")
    ua_nome = ua.nome

    # 2. Resolve janela. O default de `fim` NAO e a ultima data publicada e
    #    sim o ultimo dia com a classe Sub presente e nao-zerada -- a ultima
    #    data costuma ser um snapshot incompleto (bug conhecido QiTech "MEC
    #    Sub zerada"), que faria a pagina renderizar uma queda falsa pra zero.
    #    Override explicito de periodo_fim ainda mostra o dia incompleto.
    max_data = (
        await db.execute(
            select(MecEvolucaoCotas.data_posicao)
            .where(MecEvolucaoCotas.tenant_id == tenant_id)
            .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
            .order_by(MecEvolucaoCotas.data_posicao.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if max_data is None:
        raise ValueError(
            f"Sem dados MEC para a Unidade Administrativa {ua_id}."
        )
    ultimo_sub = (
        await db.execute(
            select(MecEvolucaoCotas.data_posicao)
            .where(MecEvolucaoCotas.tenant_id == tenant_id)
            .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
            .where(MecEvolucaoCotas.patrimonio > 0)
            .where(
                func.upper(func.trim(MecEvolucaoCotas.carteira_cliente_nome))
                == ua_nome.strip().upper()
            )
            .order_by(MecEvolucaoCotas.data_posicao.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    fim = periodo_fim or ultimo_sub or max_data
    inicio = periodo_inicio or _shift_12m(fim)

    # 3. Le MEC no intervalo. Cada (data, classe) e 1 linha.
    mec_rows = (
        (
            await db.execute(
                select(MecEvolucaoCotas)
                .where(MecEvolucaoCotas.tenant_id == tenant_id)
                .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
                .where(MecEvolucaoCotas.data_posicao >= inicio)
                .where(MecEvolucaoCotas.data_posicao <= fim)
                .order_by(MecEvolucaoCotas.data_posicao.asc())
            )
        )
        .scalars()
        .all()
    )

    # 4. Le rentabilidade (CDI) no intervalo -- % do CDI + retorno do CDI.
    rent_rows = (
        (
            await db.execute(
                select(RentabilidadeFundo)
                .where(RentabilidadeFundo.tenant_id == tenant_id)
                .where(RentabilidadeFundo.unidade_administrativa_id == ua_id)
                .where(RentabilidadeFundo.indexador == "CDI")
                .where(RentabilidadeFundo.data_posicao >= inicio)
                .where(RentabilidadeFundo.data_posicao <= fim)
                .order_by(RentabilidadeFundo.data_posicao.asc())
            )
        )
        .scalars()
        .all()
    )

    # 5. Indexa MEC por (data, classe) e rentabilidade por (data, classe).
    #    Tambem o retorno diario do proprio CDI por data (igual entre classes).
    daily: dict[date, dict[ClasseCota, _MecPonto]] = defaultdict(dict)
    classe_dias: dict[ClasseCota, list[date]] = defaultdict(list)
    classe_carteira_nome: dict[ClasseCota, str] = {}
    max_source_updated = None
    gaps_ignorados = 0

    for row in mec_rows:
        classe = _classificar(row.carteira_cliente_nome, ua_nome)
        if classe is None:
            continue
        # Linha all-zero = buraco de publicacao QiTech ("MEC zerada"), nao
        # valor real. Uma classe ativa nao fica 0/0/0 entre dois dias de R$ MM.
        if (
            row.patrimonio == 0
            and row.quantidade == 0
            and row.valor_da_cota == 0
        ):
            gaps_ignorados += 1
            continue
        d = row.data_posicao
        daily[d][classe] = _MecPonto(row)
        classe_dias[classe].append(d)
        classe_carteira_nome.setdefault(classe, row.carteira_cliente_nome)
        if row.source_updated_at is not None and (
            max_source_updated is None or row.source_updated_at > max_source_updated
        ):
            max_source_updated = row.source_updated_at

    pct_cdi_by: dict[tuple[date, ClasseCota], float | None] = {}
    rent_real_by: dict[tuple[date, ClasseCota], float | None] = {}
    cdi_ret_diario: dict[date, float] = {}
    for row in rent_rows:
        classe = _classificar(row.carteira_cliente_nome, ua_nome)
        if classe is None:
            continue
        d = row.data_posicao
        pct_cdi_by[(d, classe)] = (
            float(row.percentual_bench_mark)
            if row.percentual_bench_mark is not None
            else None
        )
        rent_real_by[(d, classe)] = (
            float(row.rentabilidade_real)
            if row.rentabilidade_real is not None
            else None
        )
        # Retorno do proprio CDI no dia (identico entre classes -- e o indice).
        if row.rentabilidade_diaria is not None:
            cdi_ret_diario[d] = float(row.rentabilidade_diaria)

    if not daily:
        raise ValueError(
            "Sem dados de cota MEC para o fundo no periodo selecionado."
        )

    # 6. Classes disponiveis (independente do filtro) -- alimenta o multiselect.
    classes_disponiveis: list[ClasseInfo] = []
    for c in _CLASSE_ORDER:
        dias = sorted(classe_dias.get(c, []))
        if not dias:
            continue
        classes_disponiveis.append(
            ClasseInfo(
                classe=c,
                label=_CLASSE_LABEL[c],
                carteira_cliente_nome=classe_carteira_nome.get(c, ""),
                primeiro_dia=dias[0],
                ultimo_dia=dias[-1],
            )
        )
    todas_classes = [ci.classe for ci in classes_disponiveis]
    classes_sel = (
        [c for c in todas_classes if c in set(classes_filtro)]
        if classes_filtro
        else list(todas_classes)
    )

    # 7. Constroi a serie nos pontos pedidos (diaria ou mes-a-mes).
    if granularidade == "mensal":
        pontos = _agregar_mensal(daily, cdi_ret_diario)
    else:
        pontos = _serie_diaria(daily, cdi_ret_diario)

    serie: list[SeriePonto] = []
    for d, classe_map in pontos:
        ponto_classes: list[SeriePontoClasse] = []
        pl_total = 0.0
        for c in _CLASSE_ORDER:
            if c not in classes_sel or c not in classe_map:
                continue
            mp = classe_map[c]
            captacao = mp.entradas - mp.saidas
            ponto_classes.append(
                SeriePontoClasse(
                    classe=c,
                    patrimonio=mp.patrimonio,
                    quantidade=mp.quantidade,
                    valor_cota=mp.valor_cota,
                    variacao_diaria_pct=mp.variacao_diaria,
                    variacao_mensal_pct=mp.variacao_mensal,
                    entradas=mp.entradas,
                    saidas=mp.saidas,
                    captacao_liquida=captacao,
                    pct_cdi=pct_cdi_by.get((d, c)),
                    rentab_real_cdi_pct=rent_real_by.get((d, c)),
                )
            )
            pl_total += mp.patrimonio
        serie.append(
            SeriePonto(
                data=d,
                pl_total=round(pl_total, 2),
                cdi_retorno_pct=_cdi_retorno_no_ponto(d, granularidade, daily, cdi_ret_diario),
                classes=ponto_classes,
            )
        )

    # 8. Resumo por classe + KPIs do fundo no periodo filtrado.
    resumo_por_classe = _resumo_por_classe(serie, classes_sel)
    kpis = _kpis(serie, daily, classes_sel)

    return EvolucaoPatrimonialResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua_nome,
        periodo_inicio=inicio,
        periodo_fim=fim,
        granularidade=granularidade,
        classes_disponiveis=classes_disponiveis,
        serie=serie,
        resumo_por_classe=resumo_por_classe,
        kpis=kpis,
        proveniencia=Proveniencia(
            atualizado_em=max_source_updated, gaps_ignorados=gaps_ignorados
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Agregacao temporal
# ─────────────────────────────────────────────────────────────────────────────


def _serie_diaria(
    daily: dict[date, dict[ClasseCota, _MecPonto]],
    cdi_ret_diario: dict[date, float],
) -> list[tuple[date, dict[ClasseCota, _MecPonto]]]:
    return [(d, daily[d]) for d in sorted(daily.keys())]


def _agregar_mensal(
    daily: dict[date, dict[ClasseCota, _MecPonto]],
    cdi_ret_diario: dict[date, float],
) -> list[tuple[date, dict[ClasseCota, _MecPonto]]]:
    """Agrega em pontos mes-a-mes.

    Estoques (patrimonio, quantidade, valor_cota, variacoes) = ultima foto do
    mes. Fluxos (aporte/retirada/entradas/saidas) = soma do mes.
    """
    by_month: dict[tuple[int, int], list[date]] = defaultdict(list)
    for d in daily:
        by_month[(d.year, d.month)].append(d)

    pontos: list[tuple[date, dict[ClasseCota, _MecPonto]]] = []
    for _ym, dias in sorted(by_month.items()):
        dias_ord = sorted(dias)
        ultimo = dias_ord[-1]
        classe_map: dict[ClasseCota, _MecPonto] = {}
        # Estoque = foto do ultimo dia do mes que tem a classe.
        for c, mp in daily[ultimo].items():
            classe_map[c] = _clone_estoque(mp)
        # Algumas classes podem nao existir no ultimo dia mas sim em dias
        # anteriores do mes (raro) -- pega a foto mais recente disponivel.
        for d in reversed(dias_ord[:-1]):
            for c, mp in daily[d].items():
                classe_map.setdefault(c, _clone_estoque(mp))
        # Fluxos = soma do mes inteiro por classe.
        for d in dias_ord:
            for c, mp in daily[d].items():
                if c in classe_map:
                    classe_map[c].entradas += mp.entradas
                    classe_map[c].saidas += mp.saidas
        pontos.append((ultimo, classe_map))
    return pontos


def _clone_estoque(mp: _MecPonto) -> _MecPonto:
    """Copia so estoque; zera fluxo (somado depois no _agregar_mensal)."""
    clone = _MecPonto.__new__(_MecPonto)
    clone.patrimonio = mp.patrimonio
    clone.quantidade = mp.quantidade
    clone.valor_cota = mp.valor_cota
    clone.variacao_diaria = mp.variacao_diaria
    clone.variacao_mensal = mp.variacao_mensal
    clone.entradas = 0.0
    clone.saidas = 0.0
    return clone


def _cdi_retorno_no_ponto(
    d: date,
    granularidade: Granularidade,
    daily: dict[date, dict[ClasseCota, _MecPonto]],
    cdi_ret_diario: dict[date, float],
) -> float | None:
    """Retorno do CDI no intervalo do ponto (%)."""
    if granularidade == "diaria":
        return cdi_ret_diario.get(d)
    # Mensal: composto dos retornos diarios do CDI dentro do mes do ponto.
    fator = 1.0
    achou = False
    for dia in daily:
        if dia.year == d.year and dia.month == d.month and dia in cdi_ret_diario:
            fator *= 1.0 + cdi_ret_diario[dia] / 100.0
            achou = True
    if not achou:
        return None
    return round((fator - 1.0) * 100.0, 6)


# ─────────────────────────────────────────────────────────────────────────────
# Resumos
# ─────────────────────────────────────────────────────────────────────────────


def _resumo_por_classe(
    serie: list[SeriePonto], classes_sel: list[ClasseCota]
) -> list[ResumoClasse]:
    # Indexa por classe: primeiro e ultimo ponto em que a classe aparece.
    primeiro: dict[ClasseCota, SeriePontoClasse] = {}
    ultimo: dict[ClasseCota, SeriePontoClasse] = {}
    captacao_acc: dict[ClasseCota, float] = defaultdict(float)
    pct_cdi_ultimo: dict[ClasseCota, float | None] = {}

    for ponto in serie:
        for pc in ponto.classes:
            primeiro.setdefault(pc.classe, pc)
            ultimo[pc.classe] = pc
            captacao_acc[pc.classe] += pc.captacao_liquida
            if pc.pct_cdi is not None:
                pct_cdi_ultimo[pc.classe] = pc.pct_cdi

    pl_total_atual = serie[-1].pl_total if serie else 0.0

    out: list[ResumoClasse] = []
    for c in _CLASSE_ORDER:
        if c not in classes_sel or c not in primeiro:
            continue
        p0 = primeiro[c]
        p1 = ultimo[c]
        rentab = (
            (p1.valor_cota / p0.valor_cota - 1.0) * 100.0
            if p0.valor_cota
            else None
        )
        out.append(
            ResumoClasse(
                classe=c,
                label=_CLASSE_LABEL[c],
                pl_inicio=round(p0.patrimonio, 2),
                pl_atual=round(p1.patrimonio, 2),
                valor_cota_inicio=p0.valor_cota,
                valor_cota_atual=p1.valor_cota,
                rentab_periodo_pct=round(rentab, 6) if rentab is not None else None,
                captacao_liquida_periodo=round(captacao_acc[c], 2),
                pct_cdi_ultimo=pct_cdi_ultimo.get(c),
                participacao_pct=(
                    round(p1.patrimonio / pl_total_atual * 100.0, 4)
                    if pl_total_atual
                    else None
                ),
            )
        )
    return out


def _kpis(
    serie: list[SeriePonto],
    daily: dict[date, dict[ClasseCota, _MecPonto]],
    classes_sel: list[ClasseCota],
) -> KpiResumo:
    pl_inicio = serie[0].pl_total if serie else 0.0
    pl_atual = serie[-1].pl_total if serie else 0.0
    delta_pct = (pl_atual / pl_inicio - 1.0) * 100.0 if pl_inicio else None
    captacao = sum(pc.captacao_liquida for ponto in serie for pc in ponto.classes)

    # Subordinacao usa TODAS as classes do fundo (estrutural), independente do
    # filtro de classe, no ultimo dia em que a Sub esta presente (pos gap-skip).
    dia_sub = max((d for d in daily if "sub" in daily[d]), default=None)
    subordinacao = None
    if dia_sub is not None:
        classe_map = daily[dia_sub]
        pl_sub = classe_map["sub"].patrimonio
        pl_todas = sum(mp.patrimonio for mp in classe_map.values())
        subordinacao = pl_sub / pl_todas * 100.0 if pl_todas else None

    # Rentabilidade + % CDI da classe Sub no periodo (destaque -- residual).
    rentab_sub = None
    pct_cdi_sub = None
    sub_pontos = [
        pc for ponto in serie for pc in ponto.classes if pc.classe == "sub"
    ]
    if len(sub_pontos) >= 2 and sub_pontos[0].valor_cota:
        rentab_sub = (
            sub_pontos[-1].valor_cota / sub_pontos[0].valor_cota - 1.0
        ) * 100.0
    for pc in reversed(sub_pontos):
        if pc.pct_cdi is not None:
            pct_cdi_sub = pc.pct_cdi
            break

    return KpiResumo(
        pl_total_inicio=round(pl_inicio, 2),
        pl_total_atual=round(pl_atual, 2),
        pl_total_delta_pct=round(delta_pct, 4) if delta_pct is not None else None,
        captacao_liquida_periodo=round(captacao, 2),
        subordinacao_pct=round(subordinacao, 4) if subordinacao is not None else None,
        rentab_sub_periodo_pct=round(rentab_sub, 6) if rentab_sub is not None else None,
        pct_cdi_sub_ultimo=pct_cdi_sub,
    )
