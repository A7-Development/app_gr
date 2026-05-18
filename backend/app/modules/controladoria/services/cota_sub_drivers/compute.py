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
| senior           | -ΔPL_Sr            | implementado completo  | -                                  |
| mezanino         | -ΔPL_Mz            | implementado completo  | -                                  |
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
    _sum_compromissada,
    _sum_fundos_di,
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
    """PDD = -Δvalor_pdd (PDD sobe -> Sub cai)."""
    pdd_prev = await _sum_pdd(db, tenant_id, fundo_doc, d_prev)
    pdd_d0 = await _sum_pdd(db, tenant_id, fundo_doc, d0)
    # _sum_pdd ja retorna o valor negativado (PDD eh tratado como passivo
    # na implementacao atual). Delta direto: -(|PDD_d0| - |PDD_d_prev|).
    delta = pdd_d0 - pdd_prev
    return _result(
        "cota_sub.driver.pdd",
        valor=delta,
        valor_d_prev=pdd_prev,
        valor_d0=pdd_d0,
    )


async def compute_apropriacao_dc(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Apropriacao DC = dEstoque - Aquisicoes + Liquidacoes (a_vencer + vencidos)."""
    apr = await _apropriacao_dc(db, tenant_id, ua_id, fundo_doc, d_prev, d0)
    return _result(
        "cota_sub.driver.apropriacao_dc",
        valor=apr.total,
    )


async def compute_apropriacao_despesas(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Apropriacao despesas = ΔCPR liquido (receber - pagar)."""
    cpr = await _cpr_detalhado(db, tenant_id, ua_id, d_prev, d0)
    return _result(
        "cota_sub.driver.apropriacao_despesas",
        valor=cpr.variacao,
        valor_d_prev=cpr.total_d1,
        valor_d0=cpr.total_d0,
    )


async def compute_fundos_di(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Fundos DI = dPosicao (subtracao de mov caixa em Fase 3c).

    TECH DEBT (Fase 3c): subtrair movimento de caixa especifico (aplicacao /
    resgate) pra isolar rendimento. Hoje retorna dPosicao bruta — pode
    superestimar o impacto quando ha movimento de caixa no dia.
    """
    prev = await _sum_fundos_di(db, tenant_id, ua_id, d_prev)
    d_0 = await _sum_fundos_di(db, tenant_id, ua_id, d0)
    return _result(
        "cota_sub.driver.fundos_di",
        valor=d_0 - prev,
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
    """
    prev = await _sum_titulos_publicos(db, tenant_id, ua_id, d_prev)
    d_0 = await _sum_titulos_publicos(db, tenant_id, ua_id, d0)
    return _result(
        "cota_sub.driver.titulos_publicos",
        valor=d_0 - prev,
        valor_d_prev=prev,
        valor_d0=d_0,
    )


async def compute_senior(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Senior = -ΔPL_Sr (Sub paga subordinacao a classe Senior)."""
    classes_prev = await _mec_classes(db, tenant_id, ua_id, ua_nome, d_prev)
    classes_d0 = await _mec_classes(db, tenant_id, ua_id, ua_nome, d0)
    # PL_Sr cresceu -> Sub paga -> driver negativo.
    delta_pl_sr = classes_d0["senior"] - classes_prev["senior"]
    return _result(
        "cota_sub.driver.senior",
        valor=-delta_pl_sr,
        valor_d_prev=classes_prev["senior"],
        valor_d0=classes_d0["senior"],
    )


async def compute_mezanino(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    fundo_doc: str, ua_nome: str, d_prev: date, d0: date,
) -> DriverResult:
    """Mezanino = -ΔPL_Mz (analogo a Senior)."""
    classes_prev = await _mec_classes(db, tenant_id, ua_id, ua_nome, d_prev)
    classes_d0 = await _mec_classes(db, tenant_id, ua_id, ua_nome, d0)
    delta_pl_mz = classes_d0["mezanino"] - classes_prev["mezanino"]
    return _result(
        "cota_sub.driver.mezanino",
        valor=-delta_pl_mz,
        valor_d_prev=classes_prev["mezanino"],
        valor_d0=classes_d0["mezanino"],
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
