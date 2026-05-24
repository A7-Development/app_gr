"""Controladoria · Cota Sub — Balanco Patrimonial (F1 do redesign, 2026-05-22).

Endpoint novo dedicado ao Balance hero do redesign. Difere de
`compute_variacao_diaria` (legado) em duas dimensoes:

  1. Shape voltado pra apresentacao patrimonial (Ativos / Passivos /
     PL deduzido / Identidade contabil), nao pra waterfall de variacao.
  2. Sinais absolutos: passivos (Mez, Sr, PDD) vem POSITIVOS no payload —
     a secao do balance comunica o sinal contabil.

Reusa os helpers de `cota_sub.py` (metodo gestor REALINVEST) via import
direto dos `_sum_*` privados. Convencao adotada em todo o modulo
controladoria — ver `cota_sub_drivers/compute.py` (Fase 3b) para
precedente.

Identidade contabil esperada:

    PL Sub Jr (deduzido)    = Σ Ativos - Σ Passivos
    PL Sub Jr (na fonte)    = wh_mec_evolucao_cotas, classe Sub
    Residuo (consistencia)  = PL deduzido - PL na fonte  (esperado ~0)

Quando residuo != 0, ha desalinhamento entre o calculo do gestor (consolidado
via 11 categorias) e o publicado pela QiTech no MEC. Sinaliza problema
de fonte (snapshot parcial, mutacao silenciosa no estoque, etc.) e merece
investigacao. Endpoint expoe o residuo cru — UI decide threshold de severidade.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub import (
    BalancoPatrimonialResponse,
    CategoriaPatrimonial,
)
from app.modules.controladoria.services.cota_sub import (
    ZERO,
    _mec_classes,
    _sum_compromissada,
    _sum_cpr_snapshot,
    _sum_dc,
    _sum_fundos_di,
    _sum_op_estruturadas,
    _sum_outros_ativos_nao_tpf,
    _sum_pdd,
    _sum_tesouraria,
    _sum_titulos_publicos,
)
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente


async def _sum_saldo_conta_corrente(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date,
) -> Decimal:
    """Saldo CONSOLIDADO de conta corrente do fundo (TODAS as contas).

    Descoberta empirica (2026-05-22, durante construcao deste service):
    `wh_saldo_conta_corrente` carrega 3 linhas typical em REALINVEST:

      - codigo='BRADESCO': R$ +X     (saldo bancario em Bradesco)
      - codigo='SOCOPA':   R$ +Y     (saldo bancario em Socopa)
      - codigo='CONCILIA': R$ -(X+Y) (contra-saldo de conciliacao)

    Σ das 3 = R$ 0,00. O CONCILIA NAO e "passagem ignoravel" — e a
    contrapartida contabil das outras duas. Excluir CONCILIA quebra
    a identidade do balanco em ~R$ 500k. Documentado aqui pra impedir
    quem vier depois de "limpar" a CONCILIA do filtro.

    Hoje o metodo gestor de `cota_sub.py` nao expoe esta linha (so usa
    `wh_saldo_tesouraria` classe Sub). Aqui exibimos como categoria
    propria — visivel ao usuario quando deixar de ser zero.
    """
    stmt = (
        select(func.coalesce(func.sum(SaldoContaCorrente.valor_total), ZERO))
        .where(SaldoContaCorrente.tenant_id == tenant_id)
        .where(SaldoContaCorrente.unidade_administrativa_id == ua_id)
        .where(SaldoContaCorrente.data_posicao == data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _snapshot(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    data: date,
) -> dict[str, Decimal]:
    """Captura todos os saldos da data alvo numa unica passada.

    Retorna dict com chaves canonicas (key da CategoriaPatrimonial). Sinais:

      - Ativos        : sinal natural (positivo quando ha saldo)
      - mezanino / sr : valor absoluto positivo (cota da QiTech ja vem positiva)
      - pdd           : valor absoluto positivo (QiTech publica negativo, normalizamos)
    """
    classes = await _mec_classes(db, tenant_id, ua_id, ua_nome, data)
    pdd_raw = await _sum_pdd(db, tenant_id, ua_id, data)

    return {
        # ── Ativos ────────────────────────────────────────────────────────
        "compromissada":         await _sum_compromissada(db, tenant_id, ua_id, data),
        "titulos_publicos":      await _sum_titulos_publicos(db, tenant_id, ua_id, data),
        "fundos_di":             await _sum_fundos_di(db, tenant_id, ua_id, ua_nome, data),
        "dc":                    await _sum_dc(db, tenant_id, ua_id, ua_nome, data),
        "op_estruturadas":       await _sum_op_estruturadas(db, tenant_id, ua_id, data),
        "outros_ativos":         await _sum_outros_ativos_nao_tpf(db, tenant_id, ua_id, data),
        "cpr":                   await _sum_cpr_snapshot(db, tenant_id, ua_id, data),
        "tesouraria":            await _sum_tesouraria(db, tenant_id, ua_id, data),
        "saldo_conta_corrente":  await _sum_saldo_conta_corrente(db, tenant_id, ua_id, data),
        # ── Passivos (absolutos) ──────────────────────────────────────────
        "mezanino":              classes["mezanino"],
        "senior":                classes["senior"],
        "pdd":                   abs(pdd_raw),
        # ── Fonte (referencia) ────────────────────────────────────────────
        "pl_sub_fonte":          classes["sub_jr"],
    }


_ATIVO_KEYS_LABELS_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("dc",                    "Direitos Creditórios",   "wh_estoque_recebivel (Σ valor_presente, exclui WOP)"),
    ("titulos_publicos",      "Títulos Públicos",       "wh_posicao_renda_fixa (COSIF TPF)"),
    ("op_estruturadas",       "Op. Estruturadas",       "wh_posicao_renda_fixa (COSIF Nota Comercial)"),
    ("fundos_di",             "Fundos DI",              "wh_posicao_cota_fundo (externos)"),
    ("compromissada",         "Compromissada",          "wh_posicao_compromissada"),
    ("outros_ativos",         "Outros Ativos",          "wh_posicao_outros_ativos (exclui PDD + TPF)"),
    ("cpr",                   "CPR (líquido)",          "wh_cpr_movimento (sum valor)"),
    ("tesouraria",            "Tesouraria",             "wh_saldo_tesouraria (classe Sub)"),
    ("saldo_conta_corrente",  "Saldo Conta Corrente",   "wh_saldo_conta_corrente (exclui CONCILIA)"),
)


_PASSIVO_KEYS_LABELS_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("senior",   "Cota Senior",   "wh_mec_evolucao_cotas (classe Senior)"),
    ("mezanino", "Cota Mezanino", "wh_mec_evolucao_cotas (classe Mezanino)"),
    ("pdd",      "PDD",           "wh_estoque_recebivel (Σ valor_pdd, exclui WOP)"),
)


def _categoria(
    key: str, label: str, source: str, tipo: str, d1_val: Decimal, d0_val: Decimal,
) -> CategoriaPatrimonial:
    return CategoriaPatrimonial(
        key=key,  # type: ignore[arg-type]
        label=label,
        tipo=tipo,  # type: ignore[arg-type]
        d1=d1_val,
        d0=d0_val,
        delta=d0_val - d1_val,
        source=source,
    )


async def compute_balanco_patrimonial(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> BalancoPatrimonialResponse:
    """Computa o balanco patrimonial otica Sub Jr para D-1 e D0.

    Args:
        tenant_id: escopo multi-tenant.
        ua_id: UUID da Unidade Administrativa (FIDC).
        data_d0: dia analisado.
        data_d1: override opcional do D-1 (default: dia util anterior pelo
                 calendario QiTech).

    Raises:
        ValueError: quando a UA nao existe ou nao tem dados em D-1/D0.
    """
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

    snap_d1 = await _snapshot(db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome, data=d1)
    snap_d0 = await _snapshot(db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome, data=data_d0)

    ativos = [
        _categoria(key, label, source, "ativo", snap_d1[key], snap_d0[key])
        for key, label, source in _ATIVO_KEYS_LABELS_SOURCES
    ]
    passivos = [
        _categoria(key, label, source, "passivo", snap_d1[key], snap_d0[key])
        for key, label, source in _PASSIVO_KEYS_LABELS_SOURCES
    ]

    soma_ativos_d1 = sum((a.d1 for a in ativos), ZERO)
    soma_ativos_d0 = sum((a.d0 for a in ativos), ZERO)
    soma_passivos_d1 = sum((p.d1 for p in passivos), ZERO)
    soma_passivos_d0 = sum((p.d0 for p in passivos), ZERO)

    pl_deduzido_d1 = soma_ativos_d1 - soma_passivos_d1
    pl_deduzido_d0 = soma_ativos_d0 - soma_passivos_d0
    pl_fonte_d1 = snap_d1["pl_sub_fonte"]
    pl_fonte_d0 = snap_d0["pl_sub_fonte"]

    return BalancoPatrimonialResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        ativos=ativos,
        passivos=passivos,
        soma_ativos_d1=soma_ativos_d1,
        soma_ativos_d0=soma_ativos_d0,
        soma_ativos_delta=soma_ativos_d0 - soma_ativos_d1,
        soma_passivos_d1=soma_passivos_d1,
        soma_passivos_d0=soma_passivos_d0,
        soma_passivos_delta=soma_passivos_d0 - soma_passivos_d1,
        pl_deduzido_d1=pl_deduzido_d1,
        pl_deduzido_d0=pl_deduzido_d0,
        pl_deduzido_delta=pl_deduzido_d0 - pl_deduzido_d1,
        pl_fonte_d1=pl_fonte_d1,
        pl_fonte_d0=pl_fonte_d0,
        pl_fonte_delta=pl_fonte_d0 - pl_fonte_d1,
        residuo_identidade_d1=pl_deduzido_d1 - pl_fonte_d1,
        residuo_identidade_d0=pl_deduzido_d0 - pl_fonte_d0,
    )
