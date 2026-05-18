"""Compute functions dos 11 drivers da Cota Sub — Fase 3b do refactor.

Cada driver e uma funcao pura `(db, tenant_id, ua_id, fundo_doc, ua_nome,
d_prev, d0) -> DriverResult`. As queries vem do `cota_sub.py` ja existente
(helpers `_sum_*` / `_mec_classes` / `_apropriacao_dc` / `_cpr_detalhado`).

## Aritmetica vs metodo do gestor

| Driver           | Formula            | Fase 3b                | Refinamento (Fase 3c)              |
|------------------|--------------------|------------------------|------------------------------------|
| pdd              | -ΔPDD              | implementado completo  | -                                  |
| apropriacao_dc   | dEstoque-Aq+Liq    | implementado completo  | -                                  |
| apropr_despesas  | dCPR liquido       | implementado completo  | -                                  |
| fundos_di        | dPos − caixa       | dPos bruta             | subtrair mov caixa por descricao   |
| compromissada    | dPos − overnight   | dPos bruta             | subtrair mov caixa por descricao   |
| titulos_publicos | dPos − aq + liq    | dPos bruta             | subtrair aquisicao + liquidacao    |
| senior           | -(ΔPL_Sr − caixa)  | -(ΔPL_Sr − caixa) (3c-A) | -                                  |
| mezanino         | -(ΔPL_Mz − caixa)  | -(ΔPL_Mz − caixa) (3c-A) | -                                  |
| tesouraria       | dPos (literal)     | implementado completo  | -                                  |
| op_estruturadas  | dPos (filtrado)    | zero hardcoded         | filtro por descricao_tipo_de_ativo |
| outros_ativos    | dPos residual      | implementado completo  | -                                  |

Decisao 2026-05-18: subtracao de movimento de caixa em fundos_di / compromissada /
titulos_publicos exige heuristica em `wh_movimento_caixa.historico_traduzido`
(qual movimento foi pra qual destino). Adiado pra Fase 3c (~3h). MVP entrega
dPosicao bruta nesses 3 drivers — residuo aceito como tech debt visivel.
Tesouraria mantida literal ao memo do gestor (dPosicao sem subtracao).
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
    _apropriacao_dc,
    _cpr_detalhado,
    _mec_classes,
    _mec_classes_fluxo_caixa,
    _sum_compromissada,
    _sum_fundos_di,
    _sum_mov_caixa_fundo_externo,
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
    # Evidencias especializadas por tipo. Fase 4b (2026-05-18): 5 campos,
    # 1 por shape de evidencia. Cada compute_fn popula 0-1 dos campos.
    # Quando o numero crescer demais, refactor pra discriminated union.
    pdd_evidencias: tuple = ()                 # PDD driver
    mtm_evidencias: tuple = ()                 # Titulos Publicos driver
    cpr_evidencias: tuple = ()                 # Apropriacao Despesas (mescla apropriacao + diferimento)
    remuneracao_evidencias: tuple = ()         # Senior / Mezanino drivers
    movimento_carteira_evidencias: tuple = ()  # Apropriacao DC driver


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
    """PDD = -Δvalor_pdd (PDD sobe -> Sub cai).

    Fase 4 do refactor de proveniencia: heuristica de _pdd_diff
    (cota_sub_explainers.py) populada como `pdd_evidencias` — papel-a-papel
    onde |Δvalor_pdd| > R$ 100. Frontend usa pra mostrar cedente/sacado/
    valor que justificam o numero.
    """
    pdd_prev = await _sum_pdd(db, tenant_id, fundo_doc, d_prev)
    pdd_d0 = await _sum_pdd(db, tenant_id, fundo_doc, d0)
    # _sum_pdd ja retorna o valor negativado (PDD eh tratado como passivo
    # na implementacao atual). Delta direto: -(|PDD_d0| - |PDD_d_prev|).
    delta = pdd_d0 - pdd_prev

    # Enriquecer com evidencias papel-a-papel. Lazy import pra evitar
    # circular: cota_sub_explainers.py importa de cota_sub.py.
    from app.modules.controladoria.services.cota_sub_explainers import (
        _pdd_diff,
    )

    pdd_evid = await _pdd_diff(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_d0=d0,
        data_d1=d_prev,
        threshold_brl=Decimal("100"),
    )
    # Top 20 evidencias por |delta| desc (ja vem ordenado de _pdd_diff).
    top_evid = tuple(pdd_evid[:20])

    return _result(
        "cota_sub.driver.pdd",
        valor=delta,
        valor_d_prev=pdd_prev,
        valor_d0=pdd_d0,
        pdd_evidencias=top_evid,
    )


async def compute_apropriacao_dc(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Apropriacao DC = dEstoque - Aquisicoes + Liquidacoes (a_vencer + vencidos).

    Fase 4b: evidencias via `_movimento_carteira_diff` — papel-a-papel
    adquirido/liquidado entre D-1 e D0 (giro de carteira). Movimento
    patrimonial e neutro em si (caixa <-> DC); evidencias justificam a
    parcela de apropriacao da curva no estoque.
    """
    apr = await _apropriacao_dc(db, tenant_id, ua_id, fundo_doc, d_prev, d0)

    # Evidencias de movimento de carteira (Fase 4b). Lazy import.
    from app.modules.controladoria.services.cota_sub_explainers import (
        _movimento_carteira_diff,
    )

    mc_evid, _tot_liq, _tot_adq, _n_liq, _n_adq = await _movimento_carteira_diff(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_d0=d0,
        data_d1=d_prev,
        threshold_brl=Decimal("100"),
    )

    return _result(
        "cota_sub.driver.apropriacao_dc",
        valor=apr.total,
        movimento_carteira_evidencias=tuple(mc_evid[:20]),
    )


async def compute_apropriacao_despesas(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Apropriacao despesas = Σ ΔCPR FILTRADO por items de apropriacao real.

    Frente 2 fix (2026-05-18): antes usavamos `_cpr_detalhado.variacao`
    (ΔCPR cru = total_d0 - total_d1), mas o CPR carrega TAMBEM movimentos
    de caixa (`LIQUIDADOS TOTAL - PROV`, `Aporte`, `Devolucao`) que sao
    neutros pro PL Sub (so trocam ativo→caixa). REALINVEST 13/05 tinha
    `LIQUIDADOS` caindo R$ 182k num dia (papel liquidado, caixa recebido)
    → driver inflava pra -R$ 188k em vez do real ~-R$ 5,8k.

    Agora `valor_brl` = soma `delta_brl` dos 2 explainers ja existentes
    que JA filtram corretamente:
    - `compute_apropriacao_explanation`: Taxa Apropriada, Despesa de %,
      Despesas com %, a Pagar em %, IOF, IR, REGISTRADORA.
    - `compute_diferimento_explanation`: 'Diferimento de despesa%'.

    Items NAO captados (LIQUIDADOS, Aporte, etc) sao movimento de caixa
    e pertencem a outros drivers (Apropriacao DC, fluxo de caixa). Caem
    em "Outros Ativos" / "Tesouraria" naturalmente quando o saldo do
    fundo se ajusta.

    `valor_d_prev` e `valor_d0` continuam mostrando o saldo CPR total
    (informativo para a UI), mas o `valor_brl` reflete so apropriacoes.
    """
    cpr = await _cpr_detalhado(db, tenant_id, ua_id, d_prev, d0)

    # Enriquecer com evidencias (Fase 4b). Lazy import pra evitar circular.
    from app.modules.controladoria.services.cota_sub_explainers import (
        compute_apropriacao_explanation,
        compute_diferimento_explanation,
    )

    apropriacao_exp = await compute_apropriacao_explanation(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        data_d0=d0,
        data_d1=d_prev,
        threshold_brl=Decimal("100"),
        top_n=20,
    )
    diferimento_exp = await compute_diferimento_explanation(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        data_d0=d0,
        data_d1=d_prev,
        threshold_brl=Decimal("100"),
        top_n=20,
    )

    # valor_brl = soma das apropriacoes reais (NAO o ΔCPR cru).
    delta_apropriacao = ZERO
    if apropriacao_exp is not None:
        delta_apropriacao += apropriacao_exp.delta_brl
    if diferimento_exp is not None:
        delta_apropriacao += diferimento_exp.delta_brl

    # Mescla evidencias dos dois e re-ordena por |Δ| desc. Top 20.
    cpr_evid: list = []
    if apropriacao_exp is not None:
        cpr_evid.extend(apropriacao_exp.evidencias)
    if diferimento_exp is not None:
        cpr_evid.extend(diferimento_exp.evidencias)
    cpr_evid.sort(key=lambda e: abs(e.delta_valor), reverse=True)
    cpr_evid = cpr_evid[:20]

    return _result(
        "cota_sub.driver.apropriacao_despesas",
        valor=delta_apropriacao,
        valor_d_prev=cpr.total_d1,
        valor_d0=cpr.total_d0,
        cpr_evidencias=tuple(cpr_evid),
    )


async def compute_fundos_di(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Fundos DI = (ΔPos posicao_cota_fundo externo) + net_caixa_fundos_dia.

    Fase 3c-C (2026-05-18): subtrai movimento de caixa do dia pra isolar
    APENAS rendimento (curva/MtM). Antes retornava ΔPos bruta — em dia
    com aplicacao/resgate (ex.: REALINVEST 13/05 resgate R$ 318k do ITAU
    SOBERANO) o driver indicava -R$ 318k de perda, mas era movimento
    patrimonial neutro pro PL Sub (caixa entrou, fundo saiu — net 0).

    Convencao de sinal:
      - Aplicacao no fundo: ΔPos > 0 (cresce), caixa < 0 (sai). Soma = 0.
      - Resgate do fundo:   ΔPos < 0 (cai),   caixa > 0 (entra). Soma = 0.
      - Rendimento (curva, MtM): ΔPos > 0, caixa = 0. Soma = ΔPos.

    Fonte do estoque: `_sum_fundos_di` (filtra wh_posicao_cota_fundo por
    fundos EXTERNOS — exclui internos REALINVEST A VENCER / VENCIDOS).
    Fonte do caixa: `_sum_mov_caixa_fundo_externo` (filtra wh_movimento_caixa
    por descricao 'Aplicacao'/'Resgate' em fundo externo).
    """
    prev = await _sum_fundos_di(db, tenant_id, ua_id, ua_nome, d_prev)
    d_0 = await _sum_fundos_di(db, tenant_id, ua_id, ua_nome, d0)
    caixa_dia = await _sum_mov_caixa_fundo_externo(
        db, tenant_id, ua_id, ua_nome, d0,
    )
    return _result(
        "cota_sub.driver.fundos_di",
        valor=(d_0 - prev) + caixa_dia,
        valor_d_prev=prev,
        valor_d0=d_0,
    )


async def compute_compromissada(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Compromissada = dPosicao (subtracao de overnight em Fase 3c).

    TECH DEBT (Fase 3c): subtrair movimento overnight.
    """
    prev = await _sum_compromissada(db, tenant_id, ua_id, d_prev)
    d_0 = await _sum_compromissada(db, tenant_id, ua_id, d0)
    return _result(
        "cota_sub.driver.compromissada",
        valor=d_0 - prev,
        valor_d_prev=prev,
        valor_d0=d_0,
    )


async def compute_titulos_publicos(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Titulos Publicos = dPosicao TPF (subtracao de aq+liq em Fase 3c).

    TECH DEBT (Fase 3c): subtrair aquisicao + liquidacao pra isolar so curva.
    Filtro de TPF e via descricao_tipo_de_ativo (_is_titulo_publico).

    Fase 4b: evidencias via `_mtm_diff` (cota_sub_explainers.py) — papel-a-papel
    em wh_posicao_renda_fixa com Δqtd_agregada=0 + |Δvalor|>R$100. Agrega
    por codigo_lastro pra cancelar pares ativo/passivo de operacoes pegadas
    internas (FIDC contabiliza isso isoladamente, mas soma zero).
    """
    prev = await _sum_titulos_publicos(db, tenant_id, ua_id, d_prev)
    d_0 = await _sum_titulos_publicos(db, tenant_id, ua_id, d0)

    # Evidencias MtM (Fase 4b). Lazy import pra evitar circular.
    from app.modules.controladoria.services.cota_sub_explainers import (
        _mtm_diff,
    )

    mtm_evid = await _mtm_diff(
        db,
        tenant_id=tenant_id,
        ua_id=ua_id,
        data_d0=d0,
        data_d1=d_prev,
        threshold_brl=Decimal("100"),
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
    """Senior = -(ΔPL_Sr - caixa_Sr).

    Fase 3c-A (2026-05-18): subtrai fluxo de caixa do dia (entradas - saidas
    + aporte - retirada da classe Senior em d0) do ΔPL bruto, isolando
    APENAS a remuneracao (rendimento da curva contratada). Cash flow vai
    pro driver Sub_Jr (residual do MEC) se for aporte na Sub, ou e neutro
    no PL Sub se for aporte/resgate na propria classe Sr.

    Fase 4b: evidencia rica via `compute_remuneracao_sr_mez_explanation`
    (filtrada pra classe Senior).
    """
    classes_prev = await _mec_classes(db, tenant_id, ua_id, ua_nome, d_prev)
    classes_d0 = await _mec_classes(db, tenant_id, ua_id, ua_nome, d0)
    fluxo_d0 = await _mec_classes_fluxo_caixa(db, tenant_id, ua_id, ua_nome, d0)
    # ΔPL bruto inclui rendimento + caixa. Rendimento = bruto - caixa.
    # PL_Sr rendimento -> Sub paga -> driver negativo.
    delta_pl_sr_bruto = classes_d0["senior"] - classes_prev["senior"]
    delta_pl_sr_remuneracao = delta_pl_sr_bruto - fluxo_d0["senior"]
    rem_evid = await _remuneracao_evidencias_por_classe(
        db, tenant_id, ua_id, ua_nome, d_prev, d0, classe="senior"
    )
    return _result(
        "cota_sub.driver.senior",
        valor=-delta_pl_sr_remuneracao,
        valor_d_prev=classes_prev["senior"],
        valor_d0=classes_d0["senior"],
        remuneracao_evidencias=rem_evid,
    )


async def compute_mezanino(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Mezanino = -(ΔPL_Mz - caixa_Mz) (analogo a Senior — ver Fase 3c-A).

    Fase 4b: evidencia rica filtrada pra classe Mezanino.
    """
    classes_prev = await _mec_classes(db, tenant_id, ua_id, ua_nome, d_prev)
    classes_d0 = await _mec_classes(db, tenant_id, ua_id, ua_nome, d0)
    fluxo_d0 = await _mec_classes_fluxo_caixa(db, tenant_id, ua_id, ua_nome, d0)
    delta_pl_mz_bruto = classes_d0["mezanino"] - classes_prev["mezanino"]
    delta_pl_mz_remuneracao = delta_pl_mz_bruto - fluxo_d0["mezanino"]
    rem_evid = await _remuneracao_evidencias_por_classe(
        db, tenant_id, ua_id, ua_nome, d_prev, d0, classe="mezanino"
    )
    return _result(
        "cota_sub.driver.mezanino",
        valor=-delta_pl_mz_remuneracao,
        valor_d_prev=classes_prev["mezanino"],
        valor_d0=classes_d0["mezanino"],
        remuneracao_evidencias=rem_evid,
    )


async def compute_tesouraria(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Tesouraria = dPosicao (literal ao memo, sem subtrair caixa).

    Decisao 2026-05-18: seguir o memo a risca, aceitando que transferencias
    internas Tesouraria↔Fundos podem gerar residuo (vai pro indeterminado).
    """
    prev = await _sum_tesouraria(db, tenant_id, ua_id, d_prev)
    d_0 = await _sum_tesouraria(db, tenant_id, ua_id, d0)
    return _result(
        "cota_sub.driver.tesouraria",
        valor=d_0 - prev,
        valor_d_prev=prev,
        valor_d0=d_0,
    )


async def compute_op_estruturadas(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Op Estruturadas = 0 hardcoded.

    TECH DEBT (Fase 3c): segregar de wh_posicao_outros_ativos via filtro
    em descricao_tipo_de_ativo. REALINVEST nao tem posicao em estruturadas
    hoje, entao zero e seguro pra esse fundo. Quando outro fundo entrar com
    posicao real, ajustar.
    """
    return _result(
        "cota_sub.driver.op_estruturadas",
        valor=ZERO,
        valor_d_prev=ZERO,
        valor_d0=ZERO,
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
