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
    BalancoEstruturalResponse,
    BalancoLinhaEstrutural,
    ReconciliacaoMec,
)
from app.modules.controladoria.services.cota_sub import (
    ZERO,
    _is_mezanino,
    _is_senior,
    _is_sub_jr,
    _mec_classes,
    _sum_compromissada,
    _sum_cpr_por_sinal,
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
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
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


# ─────────────────────────────────────────────────────────────────────────────
# Decomposicao por classe de cota — capital (aporte/resgate) vs valorizacao
# ─────────────────────────────────────────────────────────────────────────────

_TOL_CAPITAL = Decimal("1.0")  # abaixo disso, Δqtd e ruido de arredondamento


def _classe_de(carteira_nome: str, ua_nome: str) -> str | None:
    """Roteia `carteira_cliente_nome` -> sub_jr | mezanino | senior | None."""
    if _is_sub_jr(carteira_nome, ua_nome):
        return "sub_jr"
    if _is_mezanino(carteira_nome):
        return "mezanino"
    if _is_senior(carteira_nome):
        return "senior"
    return None


async def compute_decomposicao_classes_mec(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> dict:
    """Decompoe o ΔPL de CADA classe de cota (Sub Jr / Mezanino / Senior) entre
    D-1 e D0 em efeito-CAPITAL (aporte/resgate) vs efeito-VALORIZACAO
    (remuneracao/custo da cota).

    Motivacao (2026-05-26): na otica do PL Sub Jr, Senior e Mezanino sao
    PASSIVOS. Quando o PL de uma dessas classes sobe, o agente de variacao
    precisa distinguir (a) APORTE de cotistas (evento de capital — aumenta o
    passivo e dilui a Sub) de (b) apenas REMUNERACAO da cota (custo financeiro
    do dia). Sem isso, +R$ 121k na Mezanino e indistinguivel de custo. Caso
    canonico: REALINVEST 20/05/2026 (Mezanino +R$ 121.499,89 = aporte R$
    119.545,73 + remuneracao R$ 1.954,16).

    Decomposicao (robusta a multiplas series por classe):

        efeito_capital      = Σ(entradas - saidas + aporte - retirada)  [fluxo QiTech D0]
        efeito_valorizacao  = Δpatrimonio - efeito_capital             [residuo]
        cross-check (qtd)   = (Σq0 - Σq1) * valor_cota_d0  ≈ efeito_capital

    O efeito_capital usa os fluxos reportados pela QiTech no MEC (verdade do
    evento de capital); a decomposicao por quantidade entra so como conferencia.

    Returns:
        dict com `data`, `data_anterior`, `fundo_nome` e `classes` (lista de
        dicts por classe, ordenada por |Δpatrimonio| decrescente). Cada classe:
        patrimonio/quantidade/valor_cota (d1/d0/delta), fluxos, efeito_capital,
        efeito_valorizacao, classificacao (`aporte`|`resgate`|`apenas_valorizacao`),
        houve_evento_capital, e cross_check_qtd.
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

    def _empty() -> dict[str, Decimal | int]:
        return {
            "patrimonio": ZERO, "quantidade": ZERO, "n_rows": 0,
            "entradas": ZERO, "saidas": ZERO, "aporte": ZERO, "retirada": ZERO,
        }

    async def _load(data: date) -> dict[str, dict]:
        stmt = (
            select(
                MecEvolucaoCotas.carteira_cliente_nome,
                MecEvolucaoCotas.patrimonio,
                MecEvolucaoCotas.quantidade,
                MecEvolucaoCotas.entradas,
                MecEvolucaoCotas.saidas,
                MecEvolucaoCotas.aporte,
                MecEvolucaoCotas.retirada,
            )
            .where(MecEvolucaoCotas.tenant_id == tenant_id)
            .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
            .where(MecEvolucaoCotas.data_posicao == data)
        )
        acc = {"sub_jr": _empty(), "mezanino": _empty(), "senior": _empty()}
        for nome, pat, qtd, ent, sai, ap, ret in (await db.execute(stmt)).all():
            classe = _classe_de(nome, ua.nome)
            if classe is None:
                continue
            a = acc[classe]
            a["patrimonio"] += Decimal(pat or 0)
            a["quantidade"] += Decimal(qtd or 0)
            a["entradas"] += Decimal(ent or 0)
            a["saidas"] += Decimal(sai or 0)
            a["aporte"] += Decimal(ap or 0)
            a["retirada"] += Decimal(ret or 0)
            a["n_rows"] += 1
        return acc

    snap_d1 = await _load(d1)
    snap_d0 = await _load(data_d0)

    labels = {"sub_jr": "Cota Sub Jr", "mezanino": "Cota Mezanino", "senior": "Cota Senior"}
    classes_out: list[dict] = []
    for key in ("sub_jr", "mezanino", "senior"):
        a1, a0 = snap_d1[key], snap_d0[key]
        if a1["n_rows"] == 0 and a0["n_rows"] == 0:
            continue  # classe inexistente neste fundo

        pat_d1, pat_d0 = a1["patrimonio"], a0["patrimonio"]
        qtd_d1, qtd_d0 = a1["quantidade"], a0["quantidade"]
        delta_pl = pat_d0 - pat_d1
        delta_qtd = qtd_d0 - qtd_d1

        vcota_d1 = (pat_d1 / qtd_d1) if qtd_d1 else ZERO
        vcota_d0 = (pat_d0 / qtd_d0) if qtd_d0 else ZERO

        # Efeito CAPITAL = fluxo de cotistas reportado pela QiTech no dia D0.
        efeito_capital = a0["entradas"] - a0["saidas"] + a0["aporte"] - a0["retirada"]
        # Efeito VALORIZACAO = o que sobra (remuneracao/custo da cota).
        efeito_valorizacao = delta_pl - efeito_capital

        if abs(efeito_capital) < _TOL_CAPITAL:
            classificacao = "apenas_valorizacao"
        elif efeito_capital > 0:
            classificacao = "aporte"
        else:
            classificacao = "resgate"

        classes_out.append({
            "classe": key,
            "label": labels[key],
            "patrimonio_d1": pat_d1,
            "patrimonio_d0": pat_d0,
            "delta_pl": delta_pl,
            "quantidade_d1": qtd_d1,
            "quantidade_d0": qtd_d0,
            "delta_quantidade": delta_qtd,
            "valor_cota_d1": vcota_d1,
            "valor_cota_d0": vcota_d0,
            "entradas": a0["entradas"],
            "saidas": a0["saidas"],
            "aporte": a0["aporte"],
            "retirada": a0["retirada"],
            "efeito_capital": efeito_capital,
            "efeito_valorizacao": efeito_valorizacao,
            "classificacao": classificacao,
            "houve_evento_capital": abs(efeito_capital) >= _TOL_CAPITAL,
            "cross_check_capital_por_qtd": delta_qtd * vcota_d0,
            "cross_check_residuo": efeito_capital - (delta_qtd * vcota_d0),
        })

    classes_out.sort(key=lambda c: abs(c["delta_pl"]), reverse=True)
    return {
        "fundo_nome": ua.nome,
        "data": data_d0,
        "data_anterior": d1,
        "classes": classes_out,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Balanco ESTRUTURAL (redesign 2026-05-27) — coerencia por natureza + sinal
# ─────────────────────────────────────────────────────────────────────────────
# Reusa os MESMOS _snapshot/_sum_* do balanco antigo + a divisao de CPR por
# sinal. So muda classificacao/apresentacao — PL Sub e ALGEBRICAMENTE identico
# ao pl_deduzido de compute_balanco_patrimonial (provado em smoke). Funcao
# ADITIVA: nao toca em compute_balanco_patrimonial (que serve a tool do agente).

_TOL_RESIDUO_DIA = Decimal("1.0")


def _linha_estrutural(
    *, key: str, label: str, natureza: str, grupo: str, grupo_label: str,
    source: str, v1: Decimal, v0: Decimal, drill_key: str | None = None,
) -> BalancoLinhaEstrutural:
    delta = v0 - v1
    # Impacto no PL Sub com sinal corrigido: ativo soma; contra_ativo (PDD) e
    # passivo subtraem (crescer reduz o PL Sub). Alimenta o ranking de ofensores.
    impacto = delta if natureza == "ativo" else -delta
    return BalancoLinhaEstrutural(
        key=key, label=label,
        natureza=natureza,  # type: ignore[arg-type]
        grupo=grupo,  # type: ignore[arg-type]
        grupo_label=grupo_label,
        d1=v1, d0=v0, delta=delta,
        impacto_pl_sub=impacto,
        source=source,
        drill_key=drill_key,  # type: ignore[arg-type]
    )


async def compute_balanco_estrutural(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> BalancoEstruturalResponse:
    """Balanco gerencial otica Sub Jr, coerente por natureza + sinal.

    - PDD vira contra-ativo (abate DC -> "DC liquido"), nao passivo.
    - CPR dividido por sinal: a receber (Σ>0, ativo) / a pagar (Σ<0, passivo).
    - Tesouraria/Caixa fica no ativo mesmo negativa (reduz o ativo).
    - Senior + Mezanino agrupados como "Cotas Prioritarias" no passivo.
    - PL Sub = Σ Ativo - Σ Passivo (fecha por construcao). Reconciliacao com a
      fonte MEC vai em bloco separado.
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

    s1 = await _snapshot(db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome, data=d1)
    s0 = await _snapshot(db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome, data=data_d0)

    # CPR por sinal (substitui o net do snapshot). cpr_pag* vem <= 0.
    cpr_rec_d1, cpr_pag_d1 = await _sum_cpr_por_sinal(db, tenant_id, ua_id, d1)
    cpr_rec_d0, cpr_pag_d0 = await _sum_cpr_por_sinal(db, tenant_id, ua_id, data_d0)

    ativos: list[BalancoLinhaEstrutural] = [
        _linha_estrutural(
            key="dc_bruto", label="Direitos Creditórios", natureza="ativo",
            grupo="direitos_creditorios", grupo_label="Direitos Creditórios",
            source="wh_estoque_recebivel (Σ valor_presente, exclui WOP)",
            v1=s1["dc"], v0=s0["dc"], drill_key="dc",
        ),
        _linha_estrutural(
            key="pdd", label="PDD", natureza="contra_ativo",
            grupo="direitos_creditorios", grupo_label="Direitos Creditórios",
            source="wh_estoque_recebivel (Σ valor_pdd, exclui WOP)",
            v1=s1["pdd"], v0=s0["pdd"], drill_key="pdd",
        ),
        _linha_estrutural(
            key="titulos_publicos", label="Títulos Públicos", natureza="ativo",
            grupo="aplicacoes", grupo_label="Aplicações",
            source="wh_posicao_renda_fixa (COSIF TPF)",
            v1=s1["titulos_publicos"], v0=s0["titulos_publicos"],
            drill_key="titulos_publicos",
        ),
        _linha_estrutural(
            key="op_estruturadas", label="Op. Estruturadas", natureza="ativo",
            grupo="aplicacoes", grupo_label="Aplicações",
            source="wh_posicao_renda_fixa (COSIF Nota Comercial)",
            v1=s1["op_estruturadas"], v0=s0["op_estruturadas"],
            drill_key="op_estruturadas",
        ),
        _linha_estrutural(
            key="fundos_di", label="Fundos DI", natureza="ativo",
            grupo="aplicacoes", grupo_label="Aplicações",
            source="wh_posicao_cota_fundo (externos)",
            v1=s1["fundos_di"], v0=s0["fundos_di"],
            drill_key="fundos_di",
        ),
        _linha_estrutural(
            key="compromissada", label="Compromissada", natureza="ativo",
            grupo="aplicacoes", grupo_label="Aplicações",
            source="wh_posicao_compromissada",
            v1=s1["compromissada"], v0=s0["compromissada"],
            drill_key="compromissada",
        ),
        _linha_estrutural(
            key="outros_ativos", label="Outros Ativos", natureza="ativo",
            grupo="aplicacoes", grupo_label="Aplicações",
            source="wh_posicao_outros_ativos (exclui PDD + TPF)",
            v1=s1["outros_ativos"], v0=s0["outros_ativos"],
            drill_key="outros_ativos",
        ),
        _linha_estrutural(
            key="tesouraria", label="Tesouraria", natureza="ativo",
            grupo="disponibilidades", grupo_label="Disponibilidades",
            source="wh_saldo_tesouraria (classe Sub)",
            v1=s1["tesouraria"], v0=s0["tesouraria"],
            drill_key="tesouraria",
        ),
        _linha_estrutural(
            key="saldo_conta_corrente", label="Saldo Conta Corrente", natureza="ativo",
            grupo="disponibilidades", grupo_label="Disponibilidades",
            source="wh_saldo_conta_corrente (todas as contas, inclui CONCILIA)",
            v1=s1["saldo_conta_corrente"], v0=s0["saldo_conta_corrente"],
            drill_key="saldo_conta_corrente",
        ),
        _linha_estrutural(
            key="cpr_receber", label="Contas a Receber", natureza="ativo",
            grupo="disponibilidades", grupo_label="Disponibilidades",
            source="wh_cpr_movimento (Σ valor > 0: floating + diferidos)",
            v1=cpr_rec_d1, v0=cpr_rec_d0, drill_key="cpr_receber",
        ),
    ]

    passivos: list[BalancoLinhaEstrutural] = [
        _linha_estrutural(
            key="cpr_pagar", label="Contas a Pagar", natureza="passivo",
            grupo="operacional", grupo_label="Operacional",
            source="wh_cpr_movimento (Σ valor < 0: despesas/taxas/IOF a recolher)",
            v1=-cpr_pag_d1, v0=-cpr_pag_d0, drill_key="cpr_pagar",
        ),
        _linha_estrutural(
            key="senior", label="Cota Senior", natureza="passivo",
            grupo="cotas_prioritarias", grupo_label="Cotas Prioritárias",
            source="wh_mec_evolucao_cotas (classe Senior)",
            v1=s1["senior"], v0=s0["senior"],
            drill_key="senior",
        ),
        _linha_estrutural(
            key="mezanino", label="Cota Mezanino", natureza="passivo",
            grupo="cotas_prioritarias", grupo_label="Cotas Prioritárias",
            source="wh_mec_evolucao_cotas (classe Mezanino)",
            v1=s1["mezanino"], v0=s0["mezanino"],
            drill_key="mezanino",
        ),
    ]

    # Subtotais. Ativo: ativo(+) - contra_ativo(-). Passivo: Σ magnitudes.
    def _tot_ativo(attr: str) -> Decimal:
        return sum(
            (getattr(ln, attr) if ln.natureza == "ativo" else -getattr(ln, attr) for ln in ativos),
            ZERO,
        )

    dc_liq_d1 = s1["dc"] - s1["pdd"]
    dc_liq_d0 = s0["dc"] - s0["pdd"]

    total_ativo_d1 = _tot_ativo("d1")
    total_ativo_d0 = _tot_ativo("d0")
    total_passivo_d1 = sum((ln.d1 for ln in passivos), ZERO)
    total_passivo_d0 = sum((ln.d0 for ln in passivos), ZERO)

    pl_sub_d1 = total_ativo_d1 - total_passivo_d1
    pl_sub_d0 = total_ativo_d0 - total_passivo_d0

    pl_fonte_d1 = s1["pl_sub_fonte"]
    pl_fonte_d0 = s0["pl_sub_fonte"]
    residuo_delta = (pl_sub_d0 - pl_sub_d1) - (pl_fonte_d0 - pl_fonte_d1)

    # Detector de nao-reconhecidos (2026-05-27, pos-VCNC). Lazy import: o modulo
    # completude importa helpers de cota_sub.py; no topo poderia formar ciclo
    # via os imports de schema. Itens vaza_residuo explicam parte do residuo.
    from app.modules.controladoria.schemas.cota_sub import ItemNaoReconhecidoOut
    from app.modules.controladoria.services.cota_sub_completude import (
        scan_nao_reconhecidos,
    )

    completude = await scan_nao_reconhecidos(
        db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome,
        fundo_doc=ua.cnpj or "", data_d0=data_d0, data_d_prev=d1,
    )
    nao_reconhecidos_out = [
        ItemNaoReconhecidoOut(
            fonte=i.fonte, endpoint=i.endpoint, campo=i.campo,
            identificador=i.identificador, label=i.label,
            valor_d0=i.valor_d0, valor_d_prev=i.valor_d_prev,
            modo=i.modo, driver_afetado=i.driver_afetado, motivo=i.motivo,
        )
        for i in completude.itens
    ]

    return BalancoEstruturalResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        ativos=ativos,
        passivos=passivos,
        dc_liquido_d1=dc_liq_d1,
        dc_liquido_d0=dc_liq_d0,
        dc_liquido_delta=dc_liq_d0 - dc_liq_d1,
        total_ativo_d1=total_ativo_d1,
        total_ativo_d0=total_ativo_d0,
        total_ativo_delta=total_ativo_d0 - total_ativo_d1,
        total_passivo_d1=total_passivo_d1,
        total_passivo_d0=total_passivo_d0,
        total_passivo_delta=total_passivo_d0 - total_passivo_d1,
        pl_sub_d1=pl_sub_d1,
        pl_sub_d0=pl_sub_d0,
        pl_sub_delta=pl_sub_d0 - pl_sub_d1,
        reconciliacao=ReconciliacaoMec(
            pl_fonte_d1=pl_fonte_d1,
            pl_fonte_d0=pl_fonte_d0,
            pl_fonte_delta=pl_fonte_d0 - pl_fonte_d1,
            residuo_d1=pl_sub_d1 - pl_fonte_d1,
            residuo_d0=pl_sub_d0 - pl_fonte_d0,
            residuo_delta=residuo_delta,
            dentro_tolerancia=abs(residuo_delta) < _TOL_RESIDUO_DIA,
        ),
        nao_reconhecidos=nao_reconhecidos_out,
    )
