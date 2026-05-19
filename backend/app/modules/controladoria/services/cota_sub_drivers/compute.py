"""Compute functions dos 11 drivers da Cota Sub — modelo ΔSaldo simples.

Refactor 2026-05-19 (metodo gestor REALINVEST, ΔSaldo patrimonial):
cada driver retorna `valor = saldo_d0 - saldo_d_prev` da fonte correta.
Σ drivers ≡ ΔPL Sub POR CONSTRUCAO — movimento interno de caixa entre
categorias se cancela naturalmente (caixa sai de Fundos DI → entra em
Tesouraria → ΔFundos_DI + ΔTesouraria = 0).

Categorias patrimoniais e fontes silver:

| Driver           | Formula              | Fonte silver canonica                            |
|------------------|----------------------|--------------------------------------------------|
| pdd              | ΔSaldo               | wh_posicao_outros_ativos WHERE codigo='PDD'      |
| apropriacao_dc   | ΔSaldo               | wh_posicao_cota_fundo (internos REALINVEST)      |
| apropriacao_dsp  | ΔSaldo               | wh_cpr_movimento Σ valor                         |
| fundos_di        | ΔSaldo               | wh_posicao_cota_fundo (externos)                 |
| compromissada    | ΔSaldo               | wh_posicao_compromissada.valor_bruto             |
| titulos_publicos | ΔSaldo               | wh_posicao_renda_fixa via COSIF (TPF)            |
| senior           | -ΔPL_Sr (sem fluxo)  | wh_mec_evolucao_cotas.patrimonio (Senior) × -1   |
| mezanino         | -ΔPL_Mz (sem fluxo)  | wh_mec_evolucao_cotas.patrimonio (Mez) × -1      |
| tesouraria       | ΔSaldo               | wh_saldo_tesouraria (classe Sub)                 |
| op_estruturadas  | ΔSaldo               | wh_posicao_renda_fixa via COSIF (Nota Comercial) |
| outros_ativos    | ΔSaldo               | wh_posicao_outros_ativos (exclui PDD + TPF)      |

Validacao com planilha do gestor REALINVEST (28/11→01/12/2025 e
12→13/05/2026): residuo R$ 0,00 — modelo fecha por construcao.

A formula complexa "Apropriacao DC = ΔEstoque - Aq + Liq" foi DESCONTINUADA
como decomposicao principal (deferida pra analise complementar). Helpers
`_apropriacao_dc` / `_aquisicoes` / `_liquidados` continuam vivos pra
populacao de evidencias informacionais (subseccao 'Atividade do dia').
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.services.cota_sub_drivers.catalog import (
    COTA_SUB_DRIVERS,
    COTA_SUB_DRIVERS_BY_NAME,
)
from app.modules.integracoes.public import dia_util_anterior_qitech


# Reusa helpers do service principal de cota_sub.
# Import direto evita duplicacao + mantem queries num lugar so. Eventualmente
# essas queries migram pra cota_sub_drivers/_queries.py — refactor pos-Fase 3c.
from app.modules.controladoria.services.cota_sub import (  # noqa: I001 - circular OK aqui
    ZERO,
    _composicao_compromissada_evidencias,
    _composicao_fundos_di_evidencias,
    _cpr_detalhado,
    _mec_classes,
    _saldo_tesouraria_evidencias,
    _sum_compromissada,
    _sum_dc,
    _sum_fundos_di,
    _sum_op_estruturadas,
    _sum_outros_ativos_nao_tpf,
    _sum_pdd,
    _sum_tesouraria,
    _sum_titulos_publicos,
)
from sqlalchemy import select


# ─────────────────────────────────────────────────────────────────────────────
# Tipos
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Evidence:
    """Evidencia citada por um driver — heuristicas existentes alimentam isso.

    Exemplos:
        - "NC 464444 da Petrobras (Δ+R$ 1.509,01)"
        - "Aporte engaiolado R$ 124.500 (CPR 'Aporte ABC')"
        - "Liquidacao de 23 papeis (R$ 89.450)"

    No MVP da Fase 3b, `evidencias` fica vazia em todos os drivers. Population
    via heuristicas em `cota_sub_explainers.py` vem em Fase 4 (refactor service).
    """

    label: str
    valor_brl: Decimal | None
    source: str  # ex.: "wh_estoque_recebivel.valor_pdd"


@dataclass(frozen=True)
class DriverResult:
    """Resultado do compute de um driver.

    Attributes:
        metric_global_id: ref ao `MetricSpec.global_id` (ex.:
            "controladoria.cota_sub.driver.pdd").
        label: copia de `MetricSpec.label` pra renderizacao direta.
        formula_description: copia de `MetricSpec.formula_description`.
        valor_brl: impacto liquido no PL Sub. Σ drivers ≈ ΔPL_Sub_MEC.
        valor_d_prev / valor_d0: valores brutos da posicao em D-1 e D0 quando
            aplicavel. Util pra debug e mostrar contexto na UI. None quando
            driver e derivado (ex.: apropriacao_dc).
        evidencias: itens auxiliares que justificam o valor — vazio em MVP.
        endpoints_required: copia de `MetricSpec.endpoints_required`.
        indeterminado_por_dado: True quando algum endpoint requerido nao esta
            saudavel pra essa data (PARTIAL/NOT_PUBLISHED/FURO_DEFINITIVO).
            Quando True, `valor_brl` deve ser desconsiderado.
        motivo_indeterminado: string humana explicando porque (quando True).
        endpoints_unavailable: lista de endpoints faltando (quando True).
        pdd_evidencias: lista de `PddEvidencia` (papel-a-papel) quando driver
            e PDD. Tupla porque DriverResult e frozen. Tipado como tuple[Any]
            pra evitar import circular com schemas — caller faz cast pra
            list[PddEvidencia] ao serializar.
    """

    metric_global_id: str
    label: str
    formula_description: str
    valor_brl: Decimal
    valor_d_prev: Decimal | None = None
    valor_d0: Decimal | None = None
    evidencias: tuple[Evidence, ...] = ()
    endpoints_required: tuple[str, ...] = ()
    indeterminado_por_dado: bool = False
    motivo_indeterminado: str | None = None
    endpoints_unavailable: tuple[str, ...] = ()
    # Evidencias granulares indisponiveis por dado upstream ausente (ex.: PDD
    # / Apropriacao DC quando wh_estoque_recebivel esta vazio porque QiTech
    # ainda nao publicou fidc-estoque). Driver continua confiavel (valor_brl
    # vem do consolidado MEC/posicoes); apenas as evidencias papel-a-papel
    # ficam vazias. Frontend exibe o motivo em vez de evidencias falsas.
    evidencias_indisponiveis_motivo: str | None = None
    # Evidencias especializadas por tipo. Fase 4b (2026-05-18): 5 campos,
    # 1 por shape de evidencia. Cada compute_fn popula 0-1 dos campos.
    # Quando o numero crescer demais, refactor pra discriminated union.
    pdd_evidencias: tuple = ()                 # PDD driver
    mtm_evidencias: tuple = ()                 # Titulos Publicos driver
    cpr_evidencias: tuple = ()                 # Apropriacao Despesas (mescla apropriacao + diferimento)
    remuneracao_evidencias: tuple = ()         # Senior / Mezanino drivers
    movimento_carteira_evidencias: tuple = ()  # Apropriacao DC: INFORMACIONAL (sub-secao)
    saldo_tesouraria_evidencias: tuple = ()    # Tesouraria driver
    apropriacao_dc_evidencias: tuple = ()      # Apropriacao DC driver (4 inputs do calculo)


# Tipo do compute_fn — assinatura uniforme para o dispatcher.
ComputeFn = Callable[
    [AsyncSession, UUID, UUID, str, str, date, date],
    Awaitable[DriverResult],
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _spec(name: str):
    """Lookup do MetricSpec pelo nome curto."""
    return COTA_SUB_DRIVERS_BY_NAME[name]


def _result(name: str, *, valor: Decimal, **kwargs) -> DriverResult:
    """Builder helper — popula campos derivados do MetricSpec."""
    spec = _spec(name)
    return DriverResult(
        metric_global_id=spec.global_id,
        label=spec.label,
        formula_description=spec.formula_description,
        valor_brl=valor,
        endpoints_required=spec.endpoints_required,
        **kwargs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 11 compute_fns
# ─────────────────────────────────────────────────────────────────────────────


async def compute_pdd(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """PDD = ΔSaldo `wh_posicao_outros_ativos` WHERE codigo='PDD'.

    `_sum_pdd` foi refatorado pra ler do consolidado (mesma fonte do gestor
    REALINVEST). Valor ja vem com sinal contabil natural — PDD aumentando
    em modulo (mais passivo) → delta negativo → Sub cai.

    `pdd_evidencias` (papel-a-papel via `_pdd_diff` em `wh_estoque_recebivel`)
    continua INFORMACIONAL — Σ evidencias pode divergir do `valor_brl` (fonte
    granular vs consolidada), mas explica QUAIS cedentes/sacados moveram.
    """
    pdd_prev = await _sum_pdd(db, tenant_id, ua_id, d_prev)
    pdd_d0 = await _sum_pdd(db, tenant_id, ua_id, d0)
    delta = pdd_d0 - pdd_prev

    # Enriquecer com evidencias papel-a-papel. Lazy import pra evitar
    # circular: cota_sub_explainers.py importa de cota_sub.py.
    from app.modules.controladoria.services.cota_sub_explainers import (
        _pdd_diff,
    )

    pdd_evid, motivo = await _pdd_diff(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_d0=d0,
        data_d1=d_prev,
        threshold_brl=Decimal("100"),
    )
    top_evid = tuple(pdd_evid[:20])

    return _result(
        "cota_sub.driver.pdd",
        valor=delta,
        valor_d_prev=pdd_prev,
        valor_d0=pdd_d0,
        pdd_evidencias=top_evid,
        evidencias_indisponiveis_motivo=motivo,
    )


async def compute_apropriacao_dc(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """DC = ΔSaldo `wh_posicao_cota_fundo` cotas internas REALINVEST.

    Refactor 2026-05-19 (metodo gestor REALINVEST): a carteira de Direitos
    Creditorios e contabilizada como cotas internas do proprio FIDC
    (REALINVEST A VENCER + REALINVEST VENCIDOS). O gestor le esses saldos
    diretos da posicao publicada em `market.outros_fundos` — fechamento
    exato com a fonte de verdade.

    A formula complexa "Apropriacao = ΔEstoque - Aq + Liq" foi descontinuada
    como decomposicao principal. `movimento_carteira_evidencias` (papeis
    adquiridos/liquidados em `wh_estoque_recebivel`) continua populado como
    sub-secao informacional 'Atividade do dia'.

    `metric_global_id` mantido como `cota_sub.driver.apropriacao_dc` por
    compatibilidade com o frontend; label/description atualizados no catalog.
    """
    prev = await _sum_dc(db, tenant_id, ua_id, ua_nome, d_prev)
    d_0 = await _sum_dc(db, tenant_id, ua_id, ua_nome, d0)

    # Movimento de carteira (informacional). Lazy import.
    from app.modules.controladoria.services.cota_sub_explainers import (
        _movimento_carteira_diff,
    )

    mc_evid, _tot_liq, _tot_adq, _n_liq, _n_adq, motivo = await _movimento_carteira_diff(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_d0=d0,
        data_d1=d_prev,
        threshold_brl=Decimal("100"),
    )

    return _result(
        "cota_sub.driver.apropriacao_dc",
        valor=d_0 - prev,
        valor_d_prev=prev,
        valor_d0=d_0,
        movimento_carteira_evidencias=tuple(mc_evid[:20]),
        evidencias_indisponiveis_motivo=motivo,
    )


async def compute_apropriacao_despesas(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """CPR = ΔSaldo total `wh_cpr_movimento` (Σ valor, sem filtro).

    Refactor 2026-05-19: ΔSaldo direto cobre TODAS as rubricas (apropriacao,
    diferimento, LIQUIDADOS, Aporte, etc.) — quando uma linha CPR vira caixa
    em outra categoria, a soma das duas se cancela naturalmente. Filtrar
    dentro do CPR quebra a particao.

    `cpr_evidencias` agora lista TODAS as rubricas que mexeram entre D-1 e
    D0 (sem filtro de apropriacao/diferimento). Σ evidencias = valor_brl
    (modulo rubricas abaixo do threshold de R$ 100, somadas em outros_brl).

    `metric_global_id` mantido por compatibilidade; label/description
    atualizados no catalog.
    """
    cpr = await _cpr_detalhado(db, tenant_id, ua_id, d_prev, d0)

    # Diff de TODAS as rubricas (sem filtro). Lazy import pra evitar circular.
    from app.modules.controladoria.services.cota_sub_explainers import (
        _cpr_diff_by_descricao,
    )

    cpr_evid_all = await _cpr_diff_by_descricao(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        data_d0=d0,
        data_d1=d_prev,
        descricao_filters=None,  # sem filtro: todas as rubricas
        threshold_brl=Decimal("0.01"),  # 1 cent — Σ evidencias ≡ valor_brl
    )
    # Top 20 por |delta| desc (ja vem ordenado).
    cpr_evid = cpr_evid_all[:20]

    return _result(
        "cota_sub.driver.apropriacao_despesas",
        valor=cpr.total_d0 - cpr.total_d1,
        valor_d_prev=cpr.total_d1,
        valor_d0=cpr.total_d0,
        cpr_evidencias=tuple(cpr_evid),
    )


async def compute_fundos_di(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Fundos DI = ΔSaldo `wh_posicao_cota_fundo` (fundos externos).

    Refactor 2026-05-19 (metodo gestor REALINVEST, ΔSaldo simples): antes
    subtraia movimento de caixa pra isolar rendimento. Na otica patrimonial
    com 11 categorias particionando o PL, isso e desnecessario — aplicacao
    em fundo DI sai do caixa (ΔTes negativo) e entra na cota (ΔFundos_DI
    positivo); soma das duas categorias = 0 naturalmente.

    Evidencias: composicao por fundo externo (1 linha por fundo). Σ deltas
    = valor_brl. Reaproveita o shape `SaldoTesourariaEvidencia` (generico)
    via `saldo_tesouraria_evidencias`.
    """
    prev = await _sum_fundos_di(db, tenant_id, ua_id, ua_nome, d_prev)
    d_0 = await _sum_fundos_di(db, tenant_id, ua_id, ua_nome, d0)
    evid = await _composicao_fundos_di_evidencias(
        db, tenant_id, ua_id, ua_nome, d_prev, d0,
    )
    return _result(
        "cota_sub.driver.fundos_di",
        valor=d_0 - prev,
        valor_d_prev=prev,
        valor_d0=d_0,
        saldo_tesouraria_evidencias=evid,
    )


async def compute_compromissada(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Compromissada = ΔSaldo `wh_posicao_compromissada.valor_bruto`.

    Evidencias: 1 linha por operacao (codigo) presente em D-1 ou D0, com
    papel + taxa + janela (aquisicao→resgate). Σ deltas = valor_brl.
    Reaproveita o shape `SaldoTesourariaEvidencia` via `saldo_tesouraria_evidencias`.
    """
    prev = await _sum_compromissada(db, tenant_id, ua_id, d_prev)
    d_0 = await _sum_compromissada(db, tenant_id, ua_id, d0)
    evid = await _composicao_compromissada_evidencias(
        db, tenant_id, ua_id, d_prev, d0,
    )
    return _result(
        "cota_sub.driver.compromissada",
        valor=d_0 - prev,
        valor_d_prev=prev,
        valor_d0=d_0,
        saldo_tesouraria_evidencias=evid,
    )


async def compute_titulos_publicos(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Titulos Publicos = ΔSaldo wh_posicao_renda_fixa via COSIF (TPF).

    Evidencias via `_mtm_diff` filtradas por `driver_filter='titulos_publicos'`
    (classifier COSIF) — antes vinham TODOS os papeis de RF (TPF + NCs +
    debentures), agora apenas TPF reais. Mesma classificacao usada em
    `_sum_titulos_publicos`.
    """
    prev = await _sum_titulos_publicos(db, tenant_id, ua_id, d_prev)
    d_0 = await _sum_titulos_publicos(db, tenant_id, ua_id, d0)

    # Evidencias = composicao completa por papel (Σ ≡ valor_brl). Lazy import.
    from app.modules.controladoria.services.cota_sub_explainers import (
        _mtm_diff,
    )

    mtm_evid = await _mtm_diff(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        data_d0=d0,
        data_d1=d_prev,
        threshold_brl=Decimal("0.01"),  # threshold minimo: cobre MtM pequeno
        driver_filter="titulos_publicos",
        require_qtd_estavel=False,  # inclui papeis adquiridos/liquidados
    )

    return _result(
        "cota_sub.driver.titulos_publicos",
        valor=d_0 - prev,
        valor_d_prev=prev,
        valor_d0=d_0,
        mtm_evidencias=tuple(mtm_evid[:20]),
    )


async def _remuneracao_evidencias_por_classe(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    d_prev: date,
    d0: date,
    classe: str,
) -> tuple:
    """Helper interno: chama compute_remuneracao_sr_mez_explanation e filtra
    evidencias por classe ('senior' ou 'mezanino'). Lazy import."""
    from app.modules.controladoria.services.cota_sub_explainers import (
        compute_remuneracao_sr_mez_explanation,
    )

    exp = await compute_remuneracao_sr_mez_explanation(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        ua_nome=ua_nome,
        data_d0=d0,
        data_d1=d_prev,
        threshold_brl=Decimal("100"),
    )
    if exp is None:
        return ()
    return tuple(e for e in exp.evidencias if e.classe == classe)


async def compute_senior(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Senior = -ΔPL_Senior (Sub absorve a subordinacao bruta).

    Refactor 2026-05-19 (metodo gestor REALINVEST, ΔSaldo simples): antes
    subtraia o fluxo de caixa da classe (entradas-saidas+aporte-retirada)
    pra isolar APENAS o rendimento. Na otica patrimonial, aporte na Senior
    e ABSORVIDO no PL Sub via equity (PL_Sub = Ativo - Passivo - PL_Sr - PL_Mz);
    quando entra aporte em Sr, ΔPL_Sr+ + ΔAtivo (caixa)+ se anulam e o ΔPL_Sub
    fica zero — particao se mantem sem precisar separar fluxo.

    `valor_brl` = -(PL_Sr_d0 - PL_Sr_d_prev). PL_Sr sobe → Sub paga → driver
    negativo. `remuneracao_evidencias` traz pl_d0/pl_d1/valor_cota da classe
    (informacional).
    """
    classes_prev = await _mec_classes(db, tenant_id, ua_id, ua_nome, d_prev)
    classes_d0 = await _mec_classes(db, tenant_id, ua_id, ua_nome, d0)
    delta_pl_sr = classes_d0["senior"] - classes_prev["senior"]
    rem_evid = await _remuneracao_evidencias_por_classe(
        db, tenant_id, ua_id, ua_nome, d_prev, d0, classe="senior"
    )
    return _result(
        "cota_sub.driver.senior",
        valor=-delta_pl_sr,
        valor_d_prev=classes_prev["senior"],
        valor_d0=classes_d0["senior"],
        remuneracao_evidencias=rem_evid,
    )


async def compute_mezanino(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Mezanino = -ΔPL_Mezanino (analogo a Senior, ΔSaldo simples)."""
    classes_prev = await _mec_classes(db, tenant_id, ua_id, ua_nome, d_prev)
    classes_d0 = await _mec_classes(db, tenant_id, ua_id, ua_nome, d0)
    delta_pl_mz = classes_d0["mezanino"] - classes_prev["mezanino"]
    rem_evid = await _remuneracao_evidencias_por_classe(
        db, tenant_id, ua_id, ua_nome, d_prev, d0, classe="mezanino"
    )
    return _result(
        "cota_sub.driver.mezanino",
        valor=-delta_pl_mz,
        valor_d_prev=classes_prev["mezanino"],
        valor_d0=classes_d0["mezanino"],
        remuneracao_evidencias=rem_evid,
    )


async def compute_tesouraria(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Tesouraria = dPosicao (saldo Sub apenas, sem CONCILIA).

    Refactor 2026-05-19: `_sum_tesouraria` filtra so classe Sub
    em `wh_saldo_tesouraria` (exclui MEZANINO/SENIOR) e exclui
    `CONCILIA` (conta transitoria) em `wh_saldo_conta_corrente`.

    Evidencias: composicao do saldo por conta (D-1 → D0). Σ deltas das
    evidencias = valor_brl do driver. Permite ao usuario ver de onde
    vem o saldo (Tesouraria QiTech + Bradesco + Socopa) e o que mexeu
    entre D-1 e D0.
    """
    prev = await _sum_tesouraria(db, tenant_id, ua_id, d_prev)
    d_0 = await _sum_tesouraria(db, tenant_id, ua_id, d0)
    evid = await _saldo_tesouraria_evidencias(db, tenant_id, ua_id, d_prev, d0)
    return _result(
        "cota_sub.driver.tesouraria",
        valor=d_0 - prev,
        valor_d_prev=prev,
        valor_d0=d_0,
        saldo_tesouraria_evidencias=evid,
    )


async def compute_op_estruturadas(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Op Estruturadas = ΔSaldo wh_posicao_renda_fixa via COSIF (Nota Comercial).

    Vocabulario gestor REALINVEST: "Op Estruturadas" = NCPX, NC*. Classificacao
    via COSIF 1.3.1.10.16 (regra `rf.nota_comercial`) — agnostico, sem
    hardcode de siglas.

    Evidencias via `_mtm_diff` filtradas por `driver_filter='op_estruturadas'`
    (mesma classificacao do somatorio).
    """
    prev = await _sum_op_estruturadas(db, tenant_id, ua_id, d_prev)
    d_0 = await _sum_op_estruturadas(db, tenant_id, ua_id, d0)

    # Evidencias MtM filtradas por NC. Lazy import pra evitar circular.
    from app.modules.controladoria.services.cota_sub_explainers import (
        _mtm_diff,
    )

    mtm_evid = await _mtm_diff(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        data_d0=d0,
        data_d1=d_prev,
        threshold_brl=Decimal("0.01"),  # threshold minimo
        driver_filter="op_estruturadas",
        require_qtd_estavel=False,  # inclui papeis adquiridos/liquidados
    )

    return _result(
        "cota_sub.driver.op_estruturadas",
        valor=d_0 - prev,
        valor_d_prev=prev,
        valor_d0=d_0,
        mtm_evidencias=tuple(mtm_evid[:20]),
    )


async def compute_outros_ativos(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Outros Ativos = dPosicao residual em wh_posicao_outros_ativos.

    Inclui tudo que nao e TPF. Quando op_estruturadas tiver filtro proprio
    (Fase 3c), aqui passa a excluir tambem.
    """
    prev = await _sum_outros_ativos_nao_tpf(db, tenant_id, ua_id, d_prev)
    d_0 = await _sum_outros_ativos_nao_tpf(db, tenant_id, ua_id, d0)
    return _result(
        "cota_sub.driver.outros_ativos",
        valor=d_0 - prev,
        valor_d_prev=prev,
        valor_d0=d_0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

COMPUTE_FNS: dict[str, ComputeFn] = {
    "cota_sub.driver.pdd": compute_pdd,
    "cota_sub.driver.apropriacao_dc": compute_apropriacao_dc,
    "cota_sub.driver.apropriacao_despesas": compute_apropriacao_despesas,
    "cota_sub.driver.fundos_di": compute_fundos_di,
    "cota_sub.driver.compromissada": compute_compromissada,
    "cota_sub.driver.titulos_publicos": compute_titulos_publicos,
    "cota_sub.driver.senior": compute_senior,
    "cota_sub.driver.mezanino": compute_mezanino,
    "cota_sub.driver.tesouraria": compute_tesouraria,
    "cota_sub.driver.op_estruturadas": compute_op_estruturadas,
    "cota_sub.driver.outros_ativos": compute_outros_ativos,
}


# ─────────────────────────────────────────────────────────────────────────────
# Orquestrador
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CotaSubDriversComputation:
    """Resultado completo do compute_drivers."""

    data_d0: date
    data_d_prev: date
    drivers: tuple[DriverResult, ...]
    pl_sub_d_prev: Decimal
    pl_sub_d0: Decimal
    pl_sub_delta: Decimal
    soma_drivers: Decimal
    residuo: Decimal  # pl_sub_delta - soma_drivers
    indeterminados: tuple[DriverResult, ...] = field(default_factory=tuple)


async def compute_drivers(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d_prev: date | None = None,
) -> CotaSubDriversComputation:
    """Orquestra: itera 11 drivers, chama compute_fn de cada um, calcula residuo.

    Args:
        db: sessao async.
        tenant_id: escopo multi-tenant.
        ua_id: Unidade Administrativa (= fundo).
        data_d0: data alvo (geralmente D-1 do calendario real).
        data_d_prev: data anterior (default: dia util anterior pelo calendario
            QiTech). Quando passado explicito, usa esse.

    Returns:
        CotaSubDriversComputation com 11 DriverResult + agregados.
    """
    # Resolver UA + dia anterior
    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada no tenant")

    fundo_doc = ua.cnpj or ""
    d_prev = data_d_prev or await dia_util_anterior_qitech(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    # Iterar specs do catalog (ordem determinada pela declaracao no catalog)
    drivers: list[DriverResult] = []
    for spec in COTA_SUB_DRIVERS:
        fn = COMPUTE_FNS.get(spec.name)
        if fn is None:
            # Defesa: spec sem compute_fn registrado e bug — listar como
            # indeterminado em vez de propagar excecao silenciosa.
            drivers.append(
                DriverResult(
                    metric_global_id=spec.global_id,
                    label=spec.label,
                    formula_description=spec.formula_description,
                    valor_brl=ZERO,
                    endpoints_required=spec.endpoints_required,
                    indeterminado_por_dado=True,
                    motivo_indeterminado=f"compute_fn nao implementado para {spec.name}",
                )
            )
            continue
        result = await fn(db, tenant_id, ua_id, fundo_doc, ua.nome, d_prev, data_d0)
        drivers.append(result)

    # Σ drivers (excluindo indeterminados)
    determinados = [d for d in drivers if not d.indeterminado_por_dado]
    indeterminados = [d for d in drivers if d.indeterminado_por_dado]
    soma_drivers = sum((d.valor_brl for d in determinados), ZERO)

    # PL Sub Jr (alvo do delta)
    classes_prev = await _mec_classes(db, tenant_id, ua_id, ua.nome, d_prev)
    classes_d0 = await _mec_classes(db, tenant_id, ua_id, ua.nome, data_d0)
    pl_sub_prev = classes_prev["sub_jr"]
    pl_sub_d0 = classes_d0["sub_jr"]
    pl_sub_delta = pl_sub_d0 - pl_sub_prev

    residuo = pl_sub_delta - soma_drivers

    return CotaSubDriversComputation(
        data_d0=data_d0,
        data_d_prev=d_prev,
        drivers=tuple(drivers),
        pl_sub_d_prev=pl_sub_prev,
        pl_sub_d0=pl_sub_d0,
        pl_sub_delta=pl_sub_delta,
        soma_drivers=soma_drivers,
        residuo=residuo,
        indeterminados=tuple(indeterminados),
    )
