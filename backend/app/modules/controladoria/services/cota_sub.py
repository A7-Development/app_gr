"""Controladoria · Cota Sub — service de Variacao Diaria.

Computa a decomposicao da variacao do PL da cota subordinada junior entre
D-1 e D0, espelhando a logica da planilha
`VariacaoDeCota_Preenchida.xlsx` (aba Analise).

Origem dos dados — apenas tabelas canonicas (silver) do warehouse:

    - PL Sub Jr           ← wh_mec_evolucao_cotas (`patrimonio` da classe Sub Jr)
    - Compromissada       ← wh_posicao_compromissada (sum `valor_bruto`)
    - Mezanino/Senior     ← wh_mec_evolucao_cotas (`patrimonio` da classe Mez/Sr x -1)
    - Titulos Publicos    ← wh_posicao_outros_ativos (filtro TPF em `descricao_tipo_de_ativo`)
    - Fundos DI           ← wh_posicao_cota_fundo (filtro DI em `ativo_nome`)
    - DC                  ← wh_estoque_recebivel (`valor_presente`, ja liquido de PDD)
    - Op Estruturadas /   ← wh_posicao_outros_ativos (demais tipos — segregacao
      Outros Ativos          fica para o frontend via `descricao_tipo_de_ativo`)
    - PDD                 ← wh_estoque_recebivel (sum `valor_pdd`, valor absoluto)
    - CPR                 ← wh_cpr_movimento (sum `valor` agregado)
    - Tesouraria          ← wh_saldo_tesouraria + wh_saldo_conta_corrente
    - Apropriacao DC      ← derivado: G - (D + E + F) sobre wh_estoque_recebivel
                              + wh_aquisicao_recebivel + wh_liquidacao_recebivel
    - Apropriacao despesas ← derivado de wh_cpr_movimento (delta total liquido)

Identificacao da classe de cota (Sub Jr / Mezanino / Senior) e feita por
heuristica sobre `carteira_cliente_nome`. Se um fundo nao seguir essa
convencao de naming, a heuristica precisa ser estendida.

Filtro de UA: usado quando a tabela tem `unidade_administrativa_id`. Para
EstoqueRecebivel/AquisicaoRecebivel/LiquidacaoRecebivel (que tambem expoem
`fundo_doc`), preferimos `unidade_administrativa_id` quando presente.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub import (
    ApropriacaoDc,
    ApropriacaoDcLinha,
    CprDetalhado,
    CprMovimentoItem,
    DecomposicaoItem,
    PlCategoria,
    VariacaoDiariaResponse,
)
from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.posicao_compromissada import PosicaoCompromissada
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
from app.warehouse.posicao_outros_ativos import PosicaoOutrosAtivos
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente
from app.warehouse.saldo_tesouraria import SaldoTesouraria

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────────────
# Heuristicas de classificacao
# ─────────────────────────────────────────────────────────────────────────────


def _norm(s: str | None) -> str:
    return (s or "").strip().upper()


def _is_mezanino(carteira_nome: str) -> bool:
    """Classe Mezanino: o `clienteNome` da QiTech contem 'MEZANINO'."""
    return "MEZANINO" in _norm(carteira_nome)


def _is_senior(carteira_nome: str) -> bool:
    """Classe Senior: o `clienteNome` da QiTech contem 'SENIOR'."""
    return "SENIOR" in _norm(carteira_nome)


def _is_sub_jr(carteira_nome: str, ua_nome: str) -> bool:
    """Classe Sub Jr (subordinada junior).

    Convencao QiTech (validada com REALINVEST FIDC, 2026-04-23):
        - Sub Jr:    `clienteNome` == nome do fundo cru (ex.: "REALINVEST FIDC")
        - Mezanino:  `clienteNome` == nome + " MEZANINO N" (ex.: "REALINVEST FIDC MEZANINO 1")
        - Senior:    `clienteNome` == nome + " SENIOR N"
    Identificacao POSITIVA: nome normalizado bate com o nome da UA.
    """
    return _norm(carteira_nome) == _norm(ua_nome)


def _is_titulo_publico(descricao_tipo: str) -> bool:
    n = (descricao_tipo or "").lower()
    # TPF / LFT / LTN / NTN / Tesouro
    return any(k in n for k in ("titulo publico", "tpf", "lft", "ltn", "ntn", "tesouro"))


def _is_fundo_di(ativo_nome: str, ativo_instituicao: str) -> bool:
    a = (ativo_nome or "").lower()
    i = (ativo_instituicao or "").lower()
    return " di" in a or "renda fixa" in a or "renda fixa" in i or a.startswith("di ")


def _dia_util_anterior(d: date) -> date:
    """D-1 simples: dia util anterior considerando apenas finais de semana.

    TODO: usar calendario B3/Anbima quando integrarmos `holidays_br`.
    """
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:  # 5=sab, 6=dom
        prev -= timedelta(days=1)
    return prev


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers — cada um devolve Decimal
# ─────────────────────────────────────────────────────────────────────────────


async def _sum_compromissada(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(PosicaoCompromissada.valor_bruto), ZERO))
        .where(PosicaoCompromissada.tenant_id == tenant_id)
        .where(PosicaoCompromissada.unidade_administrativa_id == ua_id)
        .where(PosicaoCompromissada.data_posicao == data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _mec_classes(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    data: date,
) -> dict[str, Decimal]:
    """Devolve {sub_jr, mezanino, senior} → patrimonio classificando pela `carteira_cliente_nome`."""
    stmt = (
        select(MecEvolucaoCotas.carteira_cliente_nome, MecEvolucaoCotas.patrimonio)
        .where(MecEvolucaoCotas.tenant_id == tenant_id)
        .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
        .where(MecEvolucaoCotas.data_posicao == data)
    )
    rows = (await db.execute(stmt)).all()
    out: dict[str, Decimal] = {"sub_jr": ZERO, "mezanino": ZERO, "senior": ZERO}
    for nome, patrimonio in rows:
        v = Decimal(patrimonio or 0)
        if _is_sub_jr(nome, ua_nome):
            out["sub_jr"] += v
        elif _is_mezanino(nome):
            out["mezanino"] += v
        elif _is_senior(nome):
            out["senior"] += v
    return out


async def _sum_titulos_publicos(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    stmt = (
        select(
            PosicaoOutrosAtivos.descricao_tipo_de_ativo,
            PosicaoOutrosAtivos.valor_total,
        )
        .where(PosicaoOutrosAtivos.tenant_id == tenant_id)
        .where(PosicaoOutrosAtivos.unidade_administrativa_id == ua_id)
        .where(PosicaoOutrosAtivos.data_posicao == data)
    )
    rows = (await db.execute(stmt)).all()
    total = ZERO
    for tipo, valor in rows:
        if _is_titulo_publico(tipo or ""):
            total += Decimal(valor or 0)
    return total


async def _sum_outros_ativos_nao_tpf(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    """Outros ativos + Op Estruturadas (planilha trata juntos no MVP)."""
    stmt = (
        select(
            PosicaoOutrosAtivos.descricao_tipo_de_ativo,
            PosicaoOutrosAtivos.valor_total,
        )
        .where(PosicaoOutrosAtivos.tenant_id == tenant_id)
        .where(PosicaoOutrosAtivos.unidade_administrativa_id == ua_id)
        .where(PosicaoOutrosAtivos.data_posicao == data)
    )
    rows = (await db.execute(stmt)).all()
    total = ZERO
    for tipo, valor in rows:
        if not _is_titulo_publico(tipo or ""):
            total += Decimal(valor or 0)
    return total


async def _sum_fundos_di(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    stmt = (
        select(
            PosicaoCotaFundo.ativo_nome,
            PosicaoCotaFundo.ativo_instituicao,
            PosicaoCotaFundo.valor_liquido,
        )
        .where(PosicaoCotaFundo.tenant_id == tenant_id)
        .where(PosicaoCotaFundo.unidade_administrativa_id == ua_id)
        .where(PosicaoCotaFundo.data_posicao == data)
    )
    rows = (await db.execute(stmt)).all()
    total = ZERO
    for nome, instituicao, valor in rows:
        if _is_fundo_di(nome or "", instituicao or ""):
            total += Decimal(valor or 0)
    return total


async def _sum_dc(
    db: AsyncSession, tenant_id: UUID, fundo_doc: str, data: date
) -> Decimal:
    """DC = sum(valor_presente) sobre estoque (ja liquido de PDD)."""
    stmt = (
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_presente), ZERO))
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _sum_pdd(
    db: AsyncSession, tenant_id: UUID, fundo_doc: str, data: date
) -> Decimal:
    """PDD = sum(valor_pdd) — convencao da planilha exibe como negativo."""
    stmt = (
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_pdd), ZERO))
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data)
    )
    raw = Decimal((await db.execute(stmt)).scalar() or 0)
    # Se o adapter grava sempre positivo, normalizamos para negativo (passivo).
    return -abs(raw)


async def _sum_cpr_snapshot(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(CprMovimento.valor), ZERO))
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _sum_tesouraria(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    """Tesouraria = wh_saldo_tesouraria + wh_saldo_conta_corrente.

    Convencao: somamos os dois (planilha trata como uma unica linha).
    """
    s_tes = (
        select(func.coalesce(func.sum(SaldoTesouraria.valor), ZERO))
        .where(SaldoTesouraria.tenant_id == tenant_id)
        .where(SaldoTesouraria.unidade_administrativa_id == ua_id)
        .where(SaldoTesouraria.data_posicao == data)
    )
    s_cc = (
        select(func.coalesce(func.sum(SaldoContaCorrente.valor_total), ZERO))
        .where(SaldoContaCorrente.tenant_id == tenant_id)
        .where(SaldoContaCorrente.unidade_administrativa_id == ua_id)
        .where(SaldoContaCorrente.data_posicao == data)
    )
    v_tes = Decimal((await db.execute(s_tes)).scalar() or 0)
    v_cc = Decimal((await db.execute(s_cc)).scalar() or 0)
    return v_tes + v_cc


async def _pl_sub_jr(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, ua_nome: str, data: date
) -> Decimal:
    classes = await _mec_classes(db, tenant_id, ua_id, ua_nome, data)
    return classes["sub_jr"]


# ─────────────────────────────────────────────────────────────────────────────
# Apropriacao DC — bloco a vencer e bloco vencidos
# ─────────────────────────────────────────────────────────────────────────────


async def _estoque_a_vencer(
    db: AsyncSession, tenant_id: UUID, fundo_doc: str, data: date
) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_presente), ZERO))
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data)
        .where(EstoqueRecebivel.data_vencimento_ajustada >= data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _estoque_vencidos(
    db: AsyncSession, tenant_id: UUID, fundo_doc: str, data: date
) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_presente), ZERO))
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data)
        .where(EstoqueRecebivel.data_vencimento_ajustada < data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _aquisicoes(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    d1: date,
    d0: date,
    a_vencer_ref_data: date | None = None,
) -> Decimal:
    """Aquisicoes consolidadas no periodo (d1, d0].

    Se `a_vencer_ref_data` e dado, filtra aquisicoes com vencimento > a_vencer_ref_data
    (subset 'a vencer no momento de referencia').
    Se None, retorna todas (subset 'vencidos' = total - a_vencer; aqui retorna 0
    pois aquisicoes a vencer nao se sobrepoem com vencidos no mesmo periodo).
    """
    stmt = (
        select(func.coalesce(func.sum(AquisicaoRecebivel.valor_compra), ZERO))
        .where(AquisicaoRecebivel.tenant_id == tenant_id)
        .where(AquisicaoRecebivel.unidade_administrativa_id == ua_id)
        .where(AquisicaoRecebivel.data_aquisicao > d1)
        .where(AquisicaoRecebivel.data_aquisicao <= d0)
    )
    if a_vencer_ref_data is not None:
        stmt = stmt.where(AquisicaoRecebivel.data_vencimento > a_vencer_ref_data)
    else:
        # bloco "vencidos" — aquisicoes ja vencidas no momento da aquisicao
        stmt = stmt.where(AquisicaoRecebivel.data_vencimento <= d0)
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _liquidados(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    d1: date,
    d0: date,
    *,
    apenas_vencidos: bool,
) -> Decimal:
    """Liquidados no periodo (d1, d0]. Sinal: NEGATIVO (saida do estoque).

    Heuristica: se `apenas_vencidos`, filtra `data_vencimento < data_posicao`
    (titulo ja estava vencido quando foi liquidado). Caso contrario, o restante
    (a vencer no momento da liquidacao).
    """
    stmt = (
        select(func.coalesce(func.sum(LiquidacaoRecebivel.valor_pago), ZERO))
        .where(LiquidacaoRecebivel.tenant_id == tenant_id)
        .where(LiquidacaoRecebivel.unidade_administrativa_id == ua_id)
        .where(LiquidacaoRecebivel.data_posicao > d1)
        .where(LiquidacaoRecebivel.data_posicao <= d0)
    )
    if apenas_vencidos:
        stmt = stmt.where(
            LiquidacaoRecebivel.data_vencimento < LiquidacaoRecebivel.data_posicao,
        )
    else:
        stmt = stmt.where(
            LiquidacaoRecebivel.data_vencimento >= LiquidacaoRecebivel.data_posicao,
        )
    raw = Decimal((await db.execute(stmt)).scalar() or 0)
    return -raw  # negativo = saida


async def _apropriacao_dc(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, fundo_doc: str, d1: date, d0: date
) -> ApropriacaoDc:
    # A vencer
    av_d1 = await _estoque_a_vencer(db, tenant_id, fundo_doc, d1)
    av_d0 = await _estoque_a_vencer(db, tenant_id, fundo_doc, d0)
    av_aq = await _aquisicoes(db, tenant_id, ua_id, d1, d0, a_vencer_ref_data=d0)
    av_li = await _liquidados(db, tenant_id, ua_id, d1, d0, apenas_vencidos=False)
    av_apr = av_d0 - (av_d1 + av_aq + av_li)

    # Vencidos
    ve_d1 = await _estoque_vencidos(db, tenant_id, fundo_doc, d1)
    ve_d0 = await _estoque_vencidos(db, tenant_id, fundo_doc, d0)
    ve_aq = await _aquisicoes(db, tenant_id, ua_id, d1, d0, a_vencer_ref_data=None)
    ve_li = await _liquidados(db, tenant_id, ua_id, d1, d0, apenas_vencidos=True)
    ve_apr = ve_d0 - (ve_d1 + ve_aq + ve_li)

    return ApropriacaoDc(
        a_vencer=ApropriacaoDcLinha(
            estoque_d1=av_d1, aquisicoes=av_aq, liquidados=av_li,
            estoque_d0=av_d0, apropriacao=av_apr,
        ),
        vencidos=ApropriacaoDcLinha(
            estoque_d1=ve_d1, aquisicoes=ve_aq, liquidados=ve_li,
            estoque_d0=ve_d0, apropriacao=ve_apr,
        ),
        total=av_apr + ve_apr,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CPR detalhado
# ─────────────────────────────────────────────────────────────────────────────


async def _cpr_lista(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date, *, receber: bool
) -> list[CprMovimentoItem]:
    """Lista de itens CPR por sinal de `valor` (receber=positivo, pagar=negativo).

    Heuristica de segregacao: pelo sinal numerico do `valor`. Se o adapter grava
    todos os valores como positivos e usa `historico_traduzido` para indicar
    direcao, este filtro precisa ser estendido para olhar o historico.
    """
    cond = CprMovimento.valor > 0 if receber else CprMovimento.valor < 0
    stmt = (
        select(CprMovimento.descricao, CprMovimento.valor)
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data)
        .where(cond)
        .order_by(CprMovimento.valor.desc() if receber else CprMovimento.valor.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        CprMovimentoItem(descricao=desc or "", valor=Decimal(val or 0))
        for desc, val in rows
    ]


async def _cpr_detalhado(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, d1: date, d0: date
) -> CprDetalhado:
    receber_d1 = await _cpr_lista(db, tenant_id, ua_id, d1, receber=True)
    receber_d0 = await _cpr_lista(db, tenant_id, ua_id, d0, receber=True)
    pagar_d1   = await _cpr_lista(db, tenant_id, ua_id, d1, receber=False)
    pagar_d0   = await _cpr_lista(db, tenant_id, ua_id, d0, receber=False)

    total_d1 = sum((m.valor for m in receber_d1), ZERO) + sum((m.valor for m in pagar_d1), ZERO)
    total_d0 = sum((m.valor for m in receber_d0), ZERO) + sum((m.valor for m in pagar_d0), ZERO)

    return CprDetalhado(
        receber_d1=receber_d1,
        receber_d0=receber_d0,
        pagar_d1=pagar_d1,
        pagar_d0=pagar_d0,
        total_d1=total_d1,
        total_d0=total_d0,
        variacao=total_d0 - total_d1,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Orquestracao principal
# ─────────────────────────────────────────────────────────────────────────────


def _categoria(
    key: str, label: str, d1: Decimal, d0: Decimal, source: str
) -> PlCategoria:
    return PlCategoria(
        key=key, label=label, d1=d1, d0=d0, delta=d0 - d1, source=source,
    )


def _signal(valor: Decimal) -> str:
    if valor > 0:
        return "ganho"
    if valor < 0:
        return "prejuizo"
    return "neutro"


async def compute_variacao_diaria(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    *,
    data_d1: date | None = None,
) -> VariacaoDiariaResponse:
    """Computa a resposta completa do endpoint."""

    # Resolve UA + dia anterior
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
    d1 = data_d1 or _dia_util_anterior(data_d0)

    # Categorias D-1 e D0
    compromissada_d1 = await _sum_compromissada(db, tenant_id, ua_id, d1)
    compromissada_d0 = await _sum_compromissada(db, tenant_id, ua_id, data_d0)
    classes_d1 = await _mec_classes(db, tenant_id, ua_id, ua.nome, d1)
    classes_d0 = await _mec_classes(db, tenant_id, ua_id, ua.nome, data_d0)
    titulos_d1 = await _sum_titulos_publicos(db, tenant_id, ua_id, d1)
    titulos_d0 = await _sum_titulos_publicos(db, tenant_id, ua_id, data_d0)
    outros_d1 = await _sum_outros_ativos_nao_tpf(db, tenant_id, ua_id, d1)
    outros_d0 = await _sum_outros_ativos_nao_tpf(db, tenant_id, ua_id, data_d0)
    fundos_di_d1 = await _sum_fundos_di(db, tenant_id, ua_id, d1)
    fundos_di_d0 = await _sum_fundos_di(db, tenant_id, ua_id, data_d0)
    dc_d1 = await _sum_dc(db, tenant_id, fundo_doc, d1)
    dc_d0 = await _sum_dc(db, tenant_id, fundo_doc, data_d0)
    pdd_d1 = await _sum_pdd(db, tenant_id, fundo_doc, d1)
    pdd_d0 = await _sum_pdd(db, tenant_id, fundo_doc, data_d0)
    cpr_snap_d1 = await _sum_cpr_snapshot(db, tenant_id, ua_id, d1)
    cpr_snap_d0 = await _sum_cpr_snapshot(db, tenant_id, ua_id, data_d0)
    teso_d1 = await _sum_tesouraria(db, tenant_id, ua_id, d1)
    teso_d0 = await _sum_tesouraria(db, tenant_id, ua_id, data_d0)

    # Mezanino e Senior — sinal invertido (passivo do Sub Jr)
    mezanino_d1 = -classes_d1["mezanino"]
    mezanino_d0 = -classes_d0["mezanino"]
    senior_d1 = -classes_d1["senior"]
    senior_d0 = -classes_d0["senior"]

    pl_d1 = classes_d1["sub_jr"]
    pl_d0 = classes_d0["sub_jr"]
    pl_delta = pl_d0 - pl_d1
    pl_delta_pct = (pl_delta / pl_d1) if pl_d1 != 0 else ZERO

    categorias = [
        _categoria("compromissada",    "Compromissada",    compromissada_d1, compromissada_d0, "wh_posicao_compromissada"),
        _categoria("mezanino",         "Mezanino",         mezanino_d1,      mezanino_d0,      "wh_mec_evolucao_cotas (classe Mez x -1)"),
        _categoria("senior",           "Senior",           senior_d1,        senior_d0,        "wh_mec_evolucao_cotas (classe Sr x -1)"),
        _categoria("titulos_publicos", "Titulos Publicos", titulos_d1,       titulos_d0,       "wh_posicao_outros_ativos (TPF)"),
        _categoria("fundos_di",        "Fundos DI",        fundos_di_d1,     fundos_di_d0,     "wh_posicao_cota_fundo (DI)"),
        _categoria("dc",               "DC",               dc_d1,            dc_d0,            "wh_estoque_recebivel.valor_presente"),
        _categoria("op_estruturadas",  "Op Estruturadas",  ZERO,             ZERO,             "wh_posicao_outros_ativos (segregacao TODO)"),
        _categoria("outros_ativos",    "Outros Ativos",    outros_d1,        outros_d0,        "wh_posicao_outros_ativos (demais)"),
        _categoria("pdd",              "PDD",              pdd_d1,           pdd_d0,           "wh_estoque_recebivel.valor_pdd"),
        _categoria("cpr",              "CPR",              cpr_snap_d1,      cpr_snap_d0,      "wh_cpr_movimento (sum valor)"),
        _categoria("tesouraria",       "Tesouraria",       teso_d1,          teso_d0,          "wh_saldo_tesouraria + wh_saldo_conta_corrente"),
    ]

    # Apropriacao DC + CPR detalhado
    apr_dc = await _apropriacao_dc(db, tenant_id, ua_id, fundo_doc, d1, data_d0)
    cpr_det = await _cpr_detalhado(db, tenant_id, ua_id, d1, data_d0)

    # Decomposicao (painel C27:D35 da planilha)
    delta_pdd = pdd_d0 - pdd_d1
    delta_compromissada = compromissada_d0 - compromissada_d1
    delta_senior = senior_d0 - senior_d1
    delta_mezanino = mezanino_d0 - mezanino_d1
    delta_titulos = titulos_d0 - titulos_d1
    delta_fundos_di = fundos_di_d0 - fundos_di_d1

    decomposicao = [
        DecomposicaoItem(key="pdd",              label="PDD",                  valor=delta_pdd,        sinal=_signal(delta_pdd)),
        DecomposicaoItem(key="apropriacao_dc",   label="Apropriacao de DC",    valor=apr_dc.total,     sinal=_signal(apr_dc.total)),
        DecomposicaoItem(key="fundos_di",        label="Fundos DI",            valor=delta_fundos_di,  sinal=_signal(delta_fundos_di)),
        DecomposicaoItem(key="apropriacao_dsp",  label="Apropriacao despesas", valor=cpr_det.variacao, sinal=_signal(cpr_det.variacao)),
        DecomposicaoItem(key="compromissada",    label="Compromissada",        valor=delta_compromissada, sinal=_signal(delta_compromissada)),
        DecomposicaoItem(key="senior",           label="Senior",               valor=delta_senior,     sinal=_signal(delta_senior)),
        DecomposicaoItem(key="mezanino",         label="Mezanino",             valor=delta_mezanino,   sinal=_signal(delta_mezanino)),
        DecomposicaoItem(key="titulos",          label="Titulos Publicos",     valor=delta_titulos,    sinal=_signal(delta_titulos)),
        DecomposicaoItem(key="tarifas",          label="Tarifas",              valor=ZERO,             sinal="neutro"),
    ]
    decomposicao_total = sum((d.valor for d in decomposicao), ZERO)

    return VariacaoDiariaResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        pl_d1=pl_d1,
        pl_d0=pl_d0,
        pl_delta=pl_delta,
        pl_delta_pct=pl_delta_pct,
        categorias=categorias,
        decomposicao=decomposicao,
        decomposicao_total=decomposicao_total,
        divergencia=decomposicao_total - pl_delta,
        apropriacao_dc=apr_dc,
        cpr_detalhado=cpr_det,
    )
