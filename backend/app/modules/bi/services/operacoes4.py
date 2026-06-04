"""L2 Operacoes4 — service da pagina `/bi/operacoes4` (Mes Corrente · operacoes).

A pagina reorienta `operacoes3` pra responder perguntas que chegam da equipe
de controladoria. Foco: composicao da receita do mes corrente em 4 buckets +
yield efetivo por DU, ambos em REGIME CAIXA (wh_operacao) — ver CLAUDE.md
banner operacoes4 + handoff SPEC.

Endpoints alimentados por este service:
- GET /bi/operacoes4/lens-receitas

Demais necessidades (cedentes/diaria enriquecidos) viram endpoints proprios
quando o frontend (PR3) precisar consumi-los — esta primeira etapa cobre
apenas L3.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bi.schemas.common import Provenance
from app.modules.bi.schemas.operacoes4 import (
    Operacoes4DiariaData,
    Operacoes4DiariaPonto,
    Operacoes4LensReceitasData,
    Operacoes4LensTaxasData,
    Operacoes4Mover,
    Operacoes4Movers,
    Operacoes4ReceitaComposicaoItem,
    Operacoes4ReceitaTipo,
    Operacoes4TaxaBucket,
    Operacoes4YieldPonto,
)
from app.modules.bi.services.operacoes import (
    _MES_PT,
    _apply_filters,
    _as_float,
    _build_provenance,
    _calcular_receita_composicao,
    _calcular_receita_por_dia,
    _calcular_yield_du,
)
from app.modules.bi.services.operacoes2 import (
    _agg_kpi,
    _du_position,
    _mes_anterior_paridade_du,
    _vop_diario_mes_corrente,
)
from app.warehouse.operacao import Operacao

_ONE_DAY = timedelta(days=1)


# Limiares de "atypical" usados pra ligar `flag_atypical` na composicao da
# receita. Sintonizados com o handoff SPEC: |delta| > 20% OU (share > 5% E
# delta nao trivial).
_FLAG_DELTA_THRESHOLD_PCT = 20.0
_FLAG_SHARE_THRESHOLD_PCT = 5.0
_FLAG_NONTRIVIAL_DELTA_PCT = 10.0

_BUCKETS_ORDER: tuple[str, ...] = (
    "desagio",
    "tarifa_cessao",
    "tarifas_operacionais",
    "outras",
)

_BUCKET_TO_ENUM: dict[str, Operacoes4ReceitaTipo] = {
    "desagio": Operacoes4ReceitaTipo.DESAGIO,
    "tarifa_cessao": Operacoes4ReceitaTipo.TARIFA_CESSAO,
    "tarifas_operacionais": Operacoes4ReceitaTipo.TARIFAS_OPERACIONAIS,
    "outras": Operacoes4ReceitaTipo.OUTRAS,
}

# Histograma de taxas (L3 card 1) — 5 faixas fixas, herdadas do proto Hi-Fi.
# Bordas em pontos percentuais; ultima faixa (>3,5) e cauda. Labels casam com
# o MOCK original pra nao gerar regressao visual vs handoff.
_TAXA_BUCKET_EDGES: tuple[float, ...] = (2.0, 2.5, 3.0, 3.5)
# En dash via escape — casa com o label do proto Hi-Fi sem disparar RUF001.
_D = chr(0x2013)
_TAXA_BUCKET_LABELS: tuple[str, ...] = (
    "<2,0",
    f"2,0{_D}2,5",
    f"2,5{_D}3,0",
    f"3,0{_D}3,5",
    ">3,5",
)


def _taxa_bucket_index(taxa: float) -> int:
    """Indice da faixa para uma taxa (% a.m.). Ultima faixa = cauda >3,5."""
    for i, edge in enumerate(_TAXA_BUCKET_EDGES):
        if taxa < edge:
            return i
    return len(_TAXA_BUCKET_EDGES)


def _weighted_median(pairs: list[tuple[float, float]]) -> float:
    """Mediana de `taxa` ponderada por `peso` (VOP).

    Retorna a taxa no ponto onde a metade do peso acumulado e atingida. 0.0
    quando nao ha peso positivo. Consistente com a ponderacao por VOP do resto
    do card (wavg, histograma).
    """
    valid = [(t, w) for t, w in pairs if w > 0]
    if not valid:
        return 0.0
    valid.sort(key=lambda p: p[0])
    half = sum(w for _, w in valid) / 2.0
    acc = 0.0
    for taxa, peso in valid:
        acc += peso
        if acc >= half:
            return taxa
    return valid[-1][0]


def _is_atypical(delta_pct: float | None, share_pct: float) -> bool:
    """Decide se uma linha de composicao recebe flag visual no frontend.

    Regras:
    - |delta| > 20%               → flag.
    - share > 5% E |delta| > 10%  → flag (movimento perceptivel em bucket
                                      relevante).
    - sem delta (paridade zero)   → sem flag (nao da pra avaliar).
    """
    if delta_pct is None:
        return False
    abs_delta = abs(delta_pct)
    if abs_delta > _FLAG_DELTA_THRESHOLD_PCT:
        return True
    return (
        share_pct > _FLAG_SHARE_THRESHOLD_PCT
        and abs_delta > _FLAG_NONTRIVIAL_DELTA_PCT
    )


def _pick_movers(
    composicao_dict: dict[str, dict[str, Any]],
) -> Operacoes4Movers:
    """Encontra o bucket que mais cresceu e o que mais caiu (vs paridade).

    Ignora `_total`. Retorna `cresceu=None` quando nenhum bucket tem delta
    positivo; idem `caiu=None` quando nenhum tem delta negativo.
    """
    cresceu: tuple[str, float, float] | None = None
    caiu: tuple[str, float, float] | None = None

    for bucket in _BUCKETS_ORDER:
        info = composicao_dict[bucket]
        delta = info["delta_pct"]
        if delta is None:
            continue
        valor = info["valor"]
        if delta > 0 and (cresceu is None or delta > cresceu[1]):
            cresceu = (bucket, delta, valor)
        if delta < 0 and (caiu is None or delta < caiu[1]):
            caiu = (bucket, delta, valor)

    return Operacoes4Movers(
        cresceu=(
            Operacoes4Mover(
                tipo=_BUCKET_TO_ENUM[cresceu[0]],
                delta_pct=cresceu[1],
                valor=Decimal(str(cresceu[2])),
            )
            if cresceu is not None
            else None
        ),
        caiu=(
            Operacoes4Mover(
                tipo=_BUCKET_TO_ENUM[caiu[0]],
                delta_pct=caiu[1],
                valor=Decimal(str(caiu[2])),
            )
            if caiu is not None
            else None
        ),
    )


def _build_yield_serie(
    yield_data: dict[str, Any],
    today: date,
    mes_inicio: date,
    mes_ant_par_fim: date | None,
) -> list[Operacoes4YieldPonto]:
    """Monta a serie de yield por DU do mes corrente, com paridade do mes ant.

    Itera os dias-calendario do MTD ([mes_inicio, today]). Para cada dia com
    dado, calcula yield_pct = receita_dia / vop_dia. Paridade vem do mes
    anterior — pareamento e por DU index (1o DU do mes ant. corresponde ao
    1o DU do mes corrente, etc).

    Quando wh_dim_dia_util esta vazia (degraded mode), a serie e construida
    por contagem sequencial de dias com dado.
    """
    mtd_idx: dict[date, tuple[float, float, float | None]] = yield_data[
        "yield_mtd_por_data"
    ]
    par_idx: dict[date, tuple[float, float, float | None]] = yield_data[
        "yield_par_por_data"
    ]

    # Ordenacao por data calendario.
    mtd_dates = sorted(mtd_idx.keys())
    par_dates = sorted(par_idx.keys())

    pontos: list[Operacoes4YieldPonto] = []
    for du_index, data_mtd in enumerate(mtd_dates, start=1):
        _rec, _vop, y_mtd = mtd_idx[data_mtd]
        if y_mtd is None:
            continue  # sem yield nesse dia (vop=0 ou ausencia de dado)

        # Pareamento por DU index dentro do mes anterior (1o com 1o, 2o com 2o)
        y_par: float | None = None
        if du_index - 1 < len(par_dates):
            data_par = par_dates[du_index - 1]
            if mes_ant_par_fim is None or data_par <= mes_ant_par_fim:
                _rec2, _vop2, y_par_val = par_idx[data_par]
                y_par = y_par_val

        pontos.append(
            Operacoes4YieldPonto(
                du=du_index,
                yield_pct=y_mtd,
                yield_parity_pct=y_par,
                today=(data_mtd == today),
            )
        )
    return pontos


async def get_lens_receitas(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
) -> tuple[Operacoes4LensReceitasData, Provenance]:
    """Bundle da L3 — composicao da receita MTD + yield efetivo por DU.

    Regime CAIXA (wh_operacao). 4 buckets: desagio, tarifa_cessao,
    tarifas_operacionais, outras. Yield = receita_total / vop_bruto.

    Paridade: mesmos N DUs do mes anterior (calculados via
    `_mes_anterior_paridade_du`). Quando wh_dim_dia_util esta vazia, degrada
    para janela calendario do mes anterior cheio (com nota em
    `du_disponivel=False`).

    Toda query passa por `_apply_filters` (CLAUDE.md §7.2).
    """
    periodo_fim = filters.get("periodo_fim")
    today = periodo_fim or date.today()
    mes_inicio = today.replace(day=1)
    mes_label = f"{_MES_PT[today.month - 1]}/{today.year % 100:02d}"

    # Janelas: MTD vs paridade DU do mes anterior.
    mtd_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": today}

    du_disponivel, du_decorridos, du_totais = await _du_position(
        db, tenant_id, today
    )
    if du_disponivel and du_decorridos > 0:
        mes_ant_par_inicio, mes_ant_par_fim = await _mes_anterior_paridade_du(
            db, tenant_id, today, du_decorridos
        )
    else:
        # Degraded: mes anterior cheio.
        mes_ant_par_inicio = (mes_inicio.replace(day=1) - _ONE_DAY).replace(day=1)
        mes_ant_par_fim = mes_inicio - _ONE_DAY
    par_filters = {
        **filters,
        "periodo_inicio": mes_ant_par_inicio,
        "periodo_fim": mes_ant_par_fim,
    }

    # 1. Composicao por bucket.
    composicao_dict = await _calcular_receita_composicao(
        db,
        tenant_id=tenant_id,
        filters=mtd_filters,
        parity_filters=par_filters,
    )

    composicao_items: list[Operacoes4ReceitaComposicaoItem] = []
    for bucket in _BUCKETS_ORDER:
        info = composicao_dict[bucket]
        composicao_items.append(
            Operacoes4ReceitaComposicaoItem(
                tipo=_BUCKET_TO_ENUM[bucket],
                valor=Decimal(str(info["valor"])),
                share_pct=info["share_pct"],
                delta_pct=info["delta_pct"],
                flag_atypical=_is_atypical(
                    info["delta_pct"], info["share_pct"]
                ),
            )
        )

    total = composicao_dict["_total"]

    # 2. Yield por DU.
    yield_data = await _calcular_yield_du(
        db,
        tenant_id=tenant_id,
        filters=mtd_filters,
        parity_filters=par_filters,
    )
    yield_du = _build_yield_serie(
        yield_data,
        today=today,
        mes_inicio=mes_inicio,
        mes_ant_par_fim=mes_ant_par_fim,
    )

    # 3. Movers.
    movers = _pick_movers(composicao_dict)

    data = Operacoes4LensReceitasData(
        total_mtd=Decimal(str(total["valor"])),
        total_parity=Decimal(str(total["parity"])),
        delta_pct=total["delta_pct"],
        composicao=composicao_items,
        yield_du=yield_du,
        yield_wavg=yield_data["yield_wavg"],
        yield_delta_pp=yield_data["yield_delta_pp"],
        yield_parity_wavg=yield_data["yield_parity_wavg"],
        movers=movers,
        mes_label=mes_label,
        du_decorridos=du_decorridos if du_disponivel else 0,
        du_totais_mes=du_totais if du_disponivel else 0,
        du_disponivel=du_disponivel,
    )

    prov = await _build_provenance(db, tenant_id, mtd_filters)
    return data, prov


async def get_lens_taxas(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
) -> tuple[Operacoes4LensTaxasData, Provenance]:
    """Bundle da L3 card 1 — distribuicao de taxas MTD ponderada por VOP.

    Histograma de 5 faixas fixas (<2,0 .. >3,5) com VOP MTD por faixa, taxa
    media ponderada por VOP (wavg — identica ao termometro) e mediana
    ponderada por VOP. `delta_pct` = wavg MTD vs wavg dos mesmos N DUs do mes
    anterior (paridade DU); degrada para mes anterior cheio quando
    wh_dim_dia_util esta vazia.

    Toda query passa por `_apply_filters` (CLAUDE.md §7.2).
    """
    periodo_fim = filters.get("periodo_fim")
    today = periodo_fim or date.today()
    mes_inicio = today.replace(day=1)
    mes_label = f"{_MES_PT[today.month - 1]}/{today.year % 100:02d}"

    mtd_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": today}

    du_disponivel, du_decorridos, du_totais = await _du_position(
        db, tenant_id, today
    )
    if du_disponivel and du_decorridos > 0:
        mes_ant_par_inicio, mes_ant_par_fim = await _mes_anterior_paridade_du(
            db, tenant_id, today, du_decorridos
        )
    else:
        mes_ant_par_inicio = (mes_inicio - _ONE_DAY).replace(day=1)
        mes_ant_par_fim = mes_inicio - _ONE_DAY
    par_filters = {
        **filters,
        "periodo_inicio": mes_ant_par_inicio,
        "periodo_fim": mes_ant_par_fim,
    }

    # wavg via _agg_kpi — garante paridade EXATA com a taxa do termometro
    # (mesma ponderacao por total_bruto, mesmo escopo).
    agg_mtd = await _agg_kpi(db, tenant_id, mtd_filters)
    agg_par = await _agg_kpi(db, tenant_id, par_filters)
    wavg = agg_mtd["taxa"]
    par_wavg = agg_par["taxa"]
    delta_pct = ((wavg / par_wavg) - 1.0) * 100.0 if par_wavg else None

    # Pares (taxa, vop) do MTD — base do histograma e da mediana ponderada.
    stmt = _apply_filters(
        select(Operacao.taxa_de_juros, Operacao.total_bruto),
        tenant_id=tenant_id,
        **mtd_filters,
    )
    rows = (await db.execute(stmt)).all()
    pairs = [(_as_float(t), _as_float(v)) for t, v in rows]

    bucket_vop = [0.0] * len(_TAXA_BUCKET_LABELS)
    for taxa, vop in pairs:
        bucket_vop[_taxa_bucket_index(taxa)] += vop

    last_idx = len(_TAXA_BUCKET_LABELS) - 1
    histograma = [
        Operacoes4TaxaBucket(
            label=_TAXA_BUCKET_LABELS[i],
            vop_mtd=Decimal(str(bucket_vop[i])),
            is_tail=(i == last_idx),
        )
        for i in range(len(_TAXA_BUCKET_LABELS))
    ]

    data = Operacoes4LensTaxasData(
        histograma=histograma,
        wavg_pct=wavg,
        mediana_pct=_weighted_median(pairs),
        delta_pct=delta_pct,
        n_operacoes=len(pairs),
        mes_label=mes_label,
        du_decorridos=du_decorridos if du_disponivel else 0,
        du_totais_mes=du_totais if du_disponivel else 0,
        du_disponivel=du_disponivel,
    )

    prov = await _build_provenance(db, tenant_id, mtd_filters)
    return data, prov


# ─── L7 — serie narrativa diaria (1 linha por DU) ─────────────────────────

# Limiar default de outlier diario (handoff SPEC §4.3): |Δ DU-par| > 50%.
# Quantis P5/P95 do MTD entram quando a serie tem >= 5 pontos com VOP > 0.
_OUTLIER_DELTA_PCT = 50.0


def _quantis_p5_p95(valores: list[float]) -> tuple[float, float] | None:
    """Quantis P5/P95 de uma lista de floats. None se < 5 elementos."""
    n = len(valores)
    if n < 5:
        return None
    ordered = sorted(valores)

    def _quantil(p: float) -> float:
        idx = max(0, min(n - 1, round(p * (n - 1))))
        return ordered[idx]

    return _quantil(0.05), _quantil(0.95)


async def get_diaria_enriquecida(
    db: AsyncSession,
    tenant_id: UUID,
    filters: dict[str, Any],
) -> tuple[Operacoes4DiariaData, Any]:
    """Serie narrativa diaria do mes corrente — 1 linha por DU.

    Alimenta L7 da pagina /bi/operacoes4. Inclui receita + yield_pct +
    outlier flag por DU. Reusa `_vop_diario_mes_corrente` (operacoes2) para
    a serie de VOP base e enriquece com `_calcular_receita_por_dia`.
    Outlier flag pelos criterios do SPEC: P5/P95 do MTD OU |Δ DU-par| > 50%.

    Toda query passa por `_apply_filters` (§7.2).
    """
    periodo_fim = filters.get("periodo_fim")
    today = periodo_fim or date.today()
    mes_inicio = today.replace(day=1)
    mes_fim = (mes_inicio.replace(day=28) + timedelta(days=4)).replace(
        day=1
    ) - timedelta(days=1)  # ultimo dia do mes
    mes_label = f"{_MES_PT[today.month - 1]}/{today.year % 100:02d}"

    # 1) VOP por dia (reuso de operacoes2).
    vop_pontos = await _vop_diario_mes_corrente(
        db,
        tenant_id,
        filters,
        mes_inicio,
        mes_fim,
        today,
    )

    # 2) Receita por dia (regime caixa, 4 buckets).
    mtd_filters = {**filters, "periodo_inicio": mes_inicio, "periodo_fim": today}
    receita_idx = await _calcular_receita_por_dia(
        db, tenant_id=tenant_id, filters=mtd_filters
    )

    # 3) Posicao DU + paridade do mes anterior para flag de outlier.
    du_disponivel, du_decorridos, du_totais = await _du_position(
        db, tenant_id, today
    )
    if du_disponivel and du_decorridos > 0:
        mes_ant_par_inicio, mes_ant_par_fim = await _mes_anterior_paridade_du(
            db, tenant_id, today, du_decorridos
        )
    else:
        mes_ant_par_inicio = (mes_inicio - timedelta(days=1)).replace(day=1)
        mes_ant_par_fim = mes_inicio - timedelta(days=1)

    par_filters = {
        **filters,
        "periodo_inicio": mes_ant_par_inicio,
        "periodo_fim": mes_ant_par_fim,
    }
    # VOP por dia do mes anterior — pareamento por ordem (DU-a-DU).
    par_pontos = await _vop_diario_mes_corrente(
        db,
        tenant_id,
        par_filters,
        mes_ant_par_inicio,
        mes_ant_par_fim,
        mes_ant_par_fim,
    )
    par_vops = [
        p.vop
        for p in par_pontos
        if p.eh_dia_util and p.vop is not None and p.vop > 0
    ]

    # 4) Filtra dias uteis com VOP > 0 e enumera como DU.
    dias_uteis_com_vop = [
        p for p in vop_pontos if p.eh_dia_util and p.vop is not None and p.vop > 0
    ]
    vop_values = [p.vop or 0.0 for p in dias_uteis_com_vop]
    quantis = _quantis_p5_p95(vop_values)

    pontos_out: list[Operacoes4DiariaPonto] = []
    for du_idx, p in enumerate(dias_uteis_com_vop, start=1):
        vop_dia = p.vop or 0.0
        rec, y_pct = receita_idx.get(p.data, (0.0, None))

        # Delta vs paridade DU correspondente.
        delta_par: float | None = None
        if du_idx - 1 < len(par_vops):
            par_v = par_vops[du_idx - 1]
            if par_v > 0:
                delta_par = (vop_dia - par_v) / par_v * 100.0

        # Outlier: P5/P95 (quando disponivel) OU |Δ DU-par| > 50%.
        is_outlier = False
        if quantis is not None:
            p5, p95 = quantis
            if vop_dia < p5 or vop_dia > p95:
                is_outlier = True
        if delta_par is not None and abs(delta_par) > _OUTLIER_DELTA_PCT:
            is_outlier = True

        pontos_out.append(
            Operacoes4DiariaPonto(
                du=du_idx,
                data=p.data,
                vop=vop_dia,
                receita=rec,
                yield_pct=y_pct,
                today=(p.data == today),
                delta_par_pct=delta_par,
                outlier=is_outlier,
            )
        )

    data = Operacoes4DiariaData(
        pontos=pontos_out,
        mes_label=mes_label,
        mes_inicio=mes_inicio,
        mes_fim=mes_fim,
        du_decorridos=du_decorridos if du_disponivel else len(pontos_out),
        du_totais_mes=du_totais if du_disponivel else 0,
        du_disponivel=du_disponivel,
    )

    prov = await _build_provenance(db, tenant_id, mtd_filters)
    return data, prov
