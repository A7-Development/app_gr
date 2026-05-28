"""Auditoria do balanco estrutural (Cota Sub) — conferencia linha a linha.

NIVEL 1 da ferramenta de conferencia (back puro, somente leitura, NAO modifica
servico nenhum). Para um fundo+data:

  1. Roda `compute_balanco_estrutural` -> valor OFICIAL de cada linha (top-down).
  2. Reproduz INDEPENDENTEMENTE o filtro de cada linha (bottom-up), reusando os
     MESMOS predicados/classificacao dos helpers (`_is_*`, `classify`,
     `_driver_gestor_for_cosif`) -> soma + contagem de linhas-fonte.
  3. Compara: bottom-up == top-down? Imprime selo FECHA / DIVERGE por linha.
  4. Imprime a reconciliacao com a fonte MEC (residuo) + nao-reconhecidos.

A reproducao e INDEPENDENTE de proposito: se fosse o mesmo codigo, um bug no
helper passaria silencioso (drill bate com a linha porque ambos erram igual).
Reproduzindo o filtro a parte, divergencia acusa OU bug de montagem OU lacuna
da reproducao — os dois sao informativos.

Uso (dev=prod DB; le DATABASE_URL do .env via app.core.config):

    python -m scripts.audita_balanco_estrutural
    python -m scripts.audita_balanco_estrutural --fundo REALINVEST --data 2026-05-26
    python -m scripts.audita_balanco_estrutural --drill titulos_publicos --top 20

`--drill <key>` lista as linhas-fonte daquela linha do balanco (o "ver origem"
do Nivel 1, via CLI). Keys: dc, pdd, titulos_publicos, op_estruturadas,
fundos_di, compromissada, outros_ativos, tesouraria, saldo_conta_corrente,
cpr_receber, cpr_pagar, senior, mezanino.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, engine
from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.services.balanco_patrimonial import (
    compute_balanco_estrutural,
)
from app.modules.controladoria.services.cosif.classifier import (
    classify,
    load_overrides,
    load_rules_cache,
)
from app.modules.controladoria.services.cota_sub import (
    ZERO,
    _driver_gestor_for_cosif,
    _is_fundo_externo,
    _is_mezanino,
    _is_senior,
    _is_sub_jr,
    _is_titulo_publico,
)
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.posicao_compromissada import PosicaoCompromissada
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
from app.warehouse.posicao_outros_ativos import PosicaoOutrosAtivos
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente
from app.warehouse.saldo_tesouraria import SaldoTesouraria

TOL = Decimal("0.01")


# ──────────────────────────────────────────────────────────────────────────
# Resultado de um "row provider": linhas-fonte + soma na orientacao do balanco.
# ──────────────────────────────────────────────────────────────────────────


class Origem:
    """Linhas-fonte de uma linha do balanco + soma (orientada como o balanco)."""

    def __init__(self, rows: list[dict[str, Any]], soma: Decimal, cols: list[str]):
        self.rows = rows
        self.soma = soma
        self.cols = cols  # ordem de colunas pra impressao no --drill


# Cada provider reproduz o filtro EXATO do helper correspondente.
# ──────────────────────────────────────────────────────────────────────────


async def _origem_estoque(
    db: AsyncSession, *, tenant_id: UUID, cnpj: str, data: date, campo: str,
) -> Origem:
    """DC (valor_presente) e PDD (valor_pdd) — wh_estoque_recebivel ex-WOP."""
    col = getattr(EstoqueRecebivel, campo)
    stmt = (
        select(
            EstoqueRecebivel.seu_numero,
            EstoqueRecebivel.numero_documento,
            EstoqueRecebivel.cedente_nome,
            EstoqueRecebivel.sacado_nome,
            EstoqueRecebivel.faixa_pdd,
            col.label("valor"),
        )
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == cnpj)
        .where(EstoqueRecebivel.data_referencia == data)
        .where(EstoqueRecebivel.faixa_pdd != "WOP")
        .order_by(col.desc())
    )
    rows = [dict(r._mapping) for r in (await db.execute(stmt)).all()]
    soma = sum((Decimal(r["valor"] or 0) for r in rows), ZERO)
    return Origem(
        rows, soma,
        ["seu_numero", "numero_documento", "cedente_nome", "faixa_pdd", "valor"],
    )


async def _origem_renda_fixa(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, data: date, driver: str,
) -> Origem:
    """Titulos Publicos / Op. Estruturadas — wh_posicao_renda_fixa classificado
    via COSIF. Reusa o MESMO classify()/_driver_gestor_for_cosif do helper."""
    rules_cache = await load_rules_cache(db)
    overrides = await load_overrides(db, tenant_id=tenant_id, fundo_id=ua_id)
    stmt = (
        select(
            PosicaoRendaFixa.codigo,
            PosicaoRendaFixa.nome_do_papel,
            PosicaoRendaFixa.codigo_lastro,
            PosicaoRendaFixa.quantidade,
            PosicaoRendaFixa.valor_bruto,
        )
        .where(PosicaoRendaFixa.tenant_id == tenant_id)
        .where(PosicaoRendaFixa.unidade_administrativa_id == ua_id)
        .where(PosicaoRendaFixa.data_posicao == data)
    )
    rows: list[dict[str, Any]] = []
    soma = ZERO
    for codigo, nome, lastro, qtd, valor_bruto in (await db.execute(stmt)).all():
        resolution = classify(
            silver_origin="wh_posicao_renda_fixa",
            row={
                "codigo": codigo, "nome_do_papel": nome,
                "codigo_lastro": lastro, "quantidade": qtd,
            },
            rules_cache=rules_cache,
            overrides=overrides,
        )
        if _driver_gestor_for_cosif(resolution.cosif) != driver:
            continue
        v = Decimal(valor_bruto or 0)
        soma += v
        rows.append({
            "codigo": codigo, "nome_do_papel": nome,
            "cosif": resolution.cosif, "valor": v,
        })
    rows.sort(key=lambda r: r["valor"], reverse=True)
    return Origem(rows, soma, ["codigo", "nome_do_papel", "cosif", "valor"])


async def _origem_fundos_di(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, ua_nome: str, data: date,
) -> Origem:
    """Fundos DI — wh_posicao_cota_fundo, externos (exclui cotas internas)."""
    stmt = (
        select(
            PosicaoCotaFundo.ativo_codigo,
            PosicaoCotaFundo.ativo_nome,
            PosicaoCotaFundo.valor_liquido,
        )
        .where(PosicaoCotaFundo.tenant_id == tenant_id)
        .where(PosicaoCotaFundo.unidade_administrativa_id == ua_id)
        .where(PosicaoCotaFundo.data_posicao == data)
    )
    rows: list[dict[str, Any]] = []
    soma = ZERO
    for cod, nome, valor in (await db.execute(stmt)).all():
        if not _is_fundo_externo(nome or "", ua_nome):
            continue
        v = Decimal(valor or 0)
        soma += v
        rows.append({"ativo_codigo": cod, "ativo_nome": nome, "valor": v})
    rows.sort(key=lambda r: r["valor"], reverse=True)
    return Origem(rows, soma, ["ativo_codigo", "ativo_nome", "valor"])


async def _origem_compromissada(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, data: date,
) -> Origem:
    stmt = (
        select(
            PosicaoCompromissada.codigo,
            PosicaoCompromissada.carteira_cliente_nome,
            PosicaoCompromissada.valor_bruto,
        )
        .where(PosicaoCompromissada.tenant_id == tenant_id)
        .where(PosicaoCompromissada.unidade_administrativa_id == ua_id)
        .where(PosicaoCompromissada.data_posicao == data)
        .order_by(PosicaoCompromissada.valor_bruto.desc())
    )
    rows = [
        {"codigo": c, "carteira": n, "valor": Decimal(v or 0)}
        for c, n, v in (await db.execute(stmt)).all()
    ]
    soma = sum((r["valor"] for r in rows), ZERO)
    return Origem(rows, soma, ["codigo", "carteira", "valor"])


async def _origem_outros_ativos(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, data: date,
) -> Origem:
    """Outros Ativos — wh_posicao_outros_ativos exceto PDD e exceto TPF."""
    stmt = (
        select(
            PosicaoOutrosAtivos.codigo,
            PosicaoOutrosAtivos.descricao_tipo_de_ativo,
            PosicaoOutrosAtivos.valor_total,
        )
        .where(PosicaoOutrosAtivos.tenant_id == tenant_id)
        .where(PosicaoOutrosAtivos.unidade_administrativa_id == ua_id)
        .where(PosicaoOutrosAtivos.data_posicao == data)
        .where(PosicaoOutrosAtivos.codigo != "PDD")
    )
    rows: list[dict[str, Any]] = []
    soma = ZERO
    for cod, tipo, valor in (await db.execute(stmt)).all():
        if _is_titulo_publico(tipo or ""):
            continue
        v = Decimal(valor or 0)
        soma += v
        rows.append({"codigo": cod, "tipo": tipo, "valor": v})
    rows.sort(key=lambda r: r["valor"], reverse=True)
    return Origem(rows, soma, ["codigo", "tipo", "valor"])


async def _origem_tesouraria(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, data: date,
) -> Origem:
    """Tesouraria — wh_saldo_tesouraria classe Sub (exclui MEZANINO/SENIOR)."""
    stmt = (
        select(
            SaldoTesouraria.descricao,
            SaldoTesouraria.carteira_cliente_nome,
            SaldoTesouraria.valor,
        )
        .where(SaldoTesouraria.tenant_id == tenant_id)
        .where(SaldoTesouraria.unidade_administrativa_id == ua_id)
        .where(SaldoTesouraria.data_posicao == data)
        .where(SaldoTesouraria.carteira_cliente_nome.notilike("%MEZANINO%"))
        .where(SaldoTesouraria.carteira_cliente_nome.notilike("%SENIOR%"))
    )
    rows = [
        {"descricao": d, "carteira": n, "valor": Decimal(v or 0)}
        for d, n, v in (await db.execute(stmt)).all()
    ]
    soma = sum((r["valor"] for r in rows), ZERO)
    return Origem(rows, soma, ["descricao", "carteira", "valor"])


async def _origem_conta_corrente(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, data: date,
) -> Origem:
    """Conta Corrente — wh_saldo_conta_corrente TODAS as contas (inclui CONCILIA;
    soma ~0 por construcao — ver _sum_saldo_conta_corrente)."""
    stmt = (
        select(
            SaldoContaCorrente.codigo,
            SaldoContaCorrente.instituicao,
            SaldoContaCorrente.valor_total,
        )
        .where(SaldoContaCorrente.tenant_id == tenant_id)
        .where(SaldoContaCorrente.unidade_administrativa_id == ua_id)
        .where(SaldoContaCorrente.data_posicao == data)
    )
    rows = [
        {"codigo": c, "instituicao": i, "valor": Decimal(v or 0)}
        for c, i, v in (await db.execute(stmt)).all()
    ]
    soma = sum((r["valor"] for r in rows), ZERO)
    return Origem(rows, soma, ["codigo", "instituicao", "valor"])


async def _origem_cpr(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, data: date, sinal: str,
) -> Origem:
    """Contas a Receber (valor>0) / a Pagar (valor<0). Para 'pagar' devolve a
    MAGNITUDE positiva (orientacao do balanco: passivo)."""
    stmt = (
        select(
            CprMovimento.descricao,
            CprMovimento.historico_traduzido,
            CprMovimento.valor,
        )
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data)
        .where(CprMovimento.valor > 0 if sinal == "receber" else CprMovimento.valor < 0)
    )
    raw = [
        {"descricao": d, "historico": h, "valor": Decimal(v or 0)}
        for d, h, v in (await db.execute(stmt)).all()
    ]
    raw.sort(key=lambda r: abs(r["valor"]), reverse=True)
    soma_raw = sum((r["valor"] for r in raw), ZERO)
    soma = -soma_raw if sinal == "pagar" else soma_raw  # passivo = magnitude +
    return Origem(raw, soma, ["descricao", "historico", "valor"])


async def _origem_mec_classe(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, data: date, classe: str,
) -> Origem:
    """Cota Senior / Mezanino — wh_mec_evolucao_cotas patrimonio da classe."""
    pred = _is_senior if classe == "senior" else _is_mezanino
    stmt = (
        select(
            MecEvolucaoCotas.carteira_cliente_nome,
            MecEvolucaoCotas.carteira_cliente_id,
            MecEvolucaoCotas.patrimonio,
        )
        .where(MecEvolucaoCotas.tenant_id == tenant_id)
        .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
        .where(MecEvolucaoCotas.data_posicao == data)
    )
    rows: list[dict[str, Any]] = []
    soma = ZERO
    for nome, cid, pat in (await db.execute(stmt)).all():
        if not pred(nome or ""):
            continue
        v = Decimal(pat or 0)
        soma += v
        rows.append({"cliente_id": cid, "carteira": nome, "valor": v})
    rows.sort(key=lambda r: r["valor"], reverse=True)
    return Origem(rows, soma, ["cliente_id", "carteira", "valor"])


# Registry: line_key -> provider (recebe contexto, devolve Origem).
def _build_providers(
    *, tenant_id: UUID, ua_id: UUID, ua_nome: str, cnpj: str, data: date,
) -> dict[str, Callable[[AsyncSession], Awaitable[Origem]]]:
    return {
        "dc_bruto": lambda db: _origem_estoque(
            db, tenant_id=tenant_id, cnpj=cnpj, data=data, campo="valor_presente"),
        "pdd": lambda db: _origem_estoque(
            db, tenant_id=tenant_id, cnpj=cnpj, data=data, campo="valor_pdd"),
        "titulos_publicos": lambda db: _origem_renda_fixa(
            db, tenant_id=tenant_id, ua_id=ua_id, data=data, driver="titulos_publicos"),
        "op_estruturadas": lambda db: _origem_renda_fixa(
            db, tenant_id=tenant_id, ua_id=ua_id, data=data, driver="op_estruturadas"),
        "fundos_di": lambda db: _origem_fundos_di(
            db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua_nome, data=data),
        "compromissada": lambda db: _origem_compromissada(
            db, tenant_id=tenant_id, ua_id=ua_id, data=data),
        "outros_ativos": lambda db: _origem_outros_ativos(
            db, tenant_id=tenant_id, ua_id=ua_id, data=data),
        "tesouraria": lambda db: _origem_tesouraria(
            db, tenant_id=tenant_id, ua_id=ua_id, data=data),
        "saldo_conta_corrente": lambda db: _origem_conta_corrente(
            db, tenant_id=tenant_id, ua_id=ua_id, data=data),
        "cpr_receber": lambda db: _origem_cpr(
            db, tenant_id=tenant_id, ua_id=ua_id, data=data, sinal="receber"),
        "cpr_pagar": lambda db: _origem_cpr(
            db, tenant_id=tenant_id, ua_id=ua_id, data=data, sinal="pagar"),
        "senior": lambda db: _origem_mec_classe(
            db, tenant_id=tenant_id, ua_id=ua_id, data=data, classe="senior"),
        "mezanino": lambda db: _origem_mec_classe(
            db, tenant_id=tenant_id, ua_id=ua_id, data=data, classe="mezanino"),
    }


def _fmt(v: Decimal | float | None) -> str:
    return f"{float(v or 0):>16,.2f}"


async def _resolve_ua(db: AsyncSession, fundo: str) -> UnidadeAdministrativa:
    ua = (
        await db.execute(
            select(UnidadeAdministrativa).where(
                UnidadeAdministrativa.nome.ilike(f"%{fundo}%")
            )
        )
    ).scalars().first()
    if ua is None:
        raise SystemExit(f"UA contendo {fundo!r} nao encontrada")
    return ua


async def _resolve_data(
    db: AsyncSession, *, tenant_id: UUID, cnpj: str, data_arg: str | None,
) -> date:
    if data_arg:
        return date.fromisoformat(data_arg)
    d = (
        await db.execute(
            select(func.max(EstoqueRecebivel.data_referencia))
            .where(EstoqueRecebivel.tenant_id == tenant_id)
            .where(EstoqueRecebivel.fundo_doc == cnpj)
        )
    ).scalar()
    if d is None:
        raise SystemExit("Sem estoque para o fundo — passe --data explicitamente")
    return d


async def _scan(
    db: AsyncSession, ua: UnidadeAdministrativa, n: int, tol: Decimal,
) -> None:
    """Roda o balanco pros ultimos N dias com MEC e mostra residuo por dia.

    `tol` separa ruido de arredondamento (centavos) de divergencia material.
    Default R$ 1 espelha `_TOL_RESIDUO_DIA` do proprio servico.
    """
    datas = (
        await db.execute(
            select(MecEvolucaoCotas.data_posicao)
            .where(MecEvolucaoCotas.tenant_id == ua.tenant_id)
            .where(MecEvolucaoCotas.unidade_administrativa_id == ua.id)
            .distinct()
            .order_by(MecEvolucaoCotas.data_posicao.desc())
            .limit(n)
        )
    ).scalars().all()
    datas = sorted(datas)

    print(f"\n{'='*72}")
    print(f" SCAN BALANCO — {ua.nome} — {len(datas)} dias (residuo de NIVEL por dia)")
    print(f"{'='*72}")
    print(f"\n{'DATA':<12}{'PL DEDUZIDO':>17}{'PL FONTE MEC':>17}{'RESIDUO':>13}  SELO")
    print(f"{'-'*72}")
    n_ok = n_div = 0
    piores: list[tuple[date, Decimal]] = []
    for d0 in datas:
        bal = await compute_balanco_estrutural(
            db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=d0,
        )
        res = Decimal(bal.reconciliacao.residuo_d0)
        ok = abs(res) < tol
        n_ok += ok
        n_div += not ok
        piores.append((d0, res))
        selo = "OK" if ok else ("centavos" if abs(res) < Decimal("1") else "MATERIAL")
        print(f"{d0.isoformat():<12}{_fmt(bal.pl_sub_d0):>17}"
              f"{_fmt(bal.reconciliacao.pl_fonte_d0):>17}{_fmt(res):>13}  {selo}")
    print(f"{'-'*72}")
    print(f"  {n_ok} fecham / {n_div} divergem (tolerancia R$ {tol})")
    piores.sort(key=lambda t: abs(t[1]), reverse=True)
    materiais = [(d, r) for d, r in piores if abs(r) >= tol]
    if materiais:
        print(f"\n  Divergencias materiais (>= R$ {tol}):")
        for d0, res in materiais:
            print(f"    {d0.isoformat()}  R$ {_fmt(res)}")
    print()


async def _compare(db: AsyncSession, ua: UnidadeAdministrativa, datas: list[date]) -> None:
    """Lado a lado: valor + contagem de linhas-fonte de cada linha entre dias.

    Localiza a linha/tabela anomala num dia (ex.: linha que afunda e volta =
    endpoint que nao publicou OU linha-fonte descartada por filtro)."""
    cnpj = ua.cnpj or ""
    vals: dict[str, dict[date, Decimal]] = {}
    cnts: dict[str, dict[date, int]] = {}
    recon: dict[date, tuple[Decimal, Decimal, Decimal]] = {}
    ordem: list[tuple[str, str, str]] = []

    for d in datas:
        bal = await compute_balanco_estrutural(
            db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=d,
        )
        provs = _build_providers(
            tenant_id=ua.tenant_id, ua_id=ua.id, ua_nome=ua.nome, cnpj=cnpj, data=d,
        )
        if not ordem:
            ordem = [(ln.key, ln.label, ln.natureza) for ln in [*bal.ativos, *bal.passivos]]
        for ln in [*bal.ativos, *bal.passivos]:
            vals.setdefault(ln.key, {})[d] = Decimal(ln.d0)
        for key, _, _ in ordem:
            org = await provs[key](db)
            cnts.setdefault(key, {})[d] = len(org.rows)
        recon[d] = (
            Decimal(bal.pl_sub_d0),
            Decimal(bal.reconciliacao.pl_fonte_d0),
            Decimal(bal.reconciliacao.residuo_d0),
        )

    dh = [d.strftime("%m-%d") for d in datas]
    print(f"\n{'='*74}")
    print(f" COMPARA — {ua.nome} — {', '.join(d.isoformat() for d in datas)}")
    print(f"{'='*74}")
    print("\n VALOR (D0) por linha")
    print(f"{'LINHA':<24}" + "".join(f"{h:>17}" for h in dh))
    print(f"{'-'*(24+17*len(datas))}")
    for key, label, natureza in ordem:
        tag = "" if natureza == "ativo" else "*"
        print(f"{label[:23]+tag:<24}" + "".join(f"{_fmt(vals[key][d]):>17}" for d in datas))
    print("\n CONTAGEM de linhas-fonte por linha")
    print(f"{'LINHA':<24}" + "".join(f"{h:>17}" for h in dh))
    print(f"{'-'*(24+17*len(datas))}")
    for key, label, _ in ordem:
        print(f"{label[:23]:<24}" + "".join(f"{cnts[key][d]:>17}" for d in datas))
    print(f"\n{'PL DEDUZIDO':<24}" + "".join(f"{_fmt(recon[d][0]):>17}" for d in datas))
    print(f"{'PL FONTE MEC':<24}" + "".join(f"{_fmt(recon[d][1]):>17}" for d in datas))
    print(f"{'RESIDUO':<24}" + "".join(f"{_fmt(recon[d][2]):>17}" for d in datas))
    print()


def _print_cov(
    tabela: str, destino: str, total: Decimal, claimed: Decimal,
    n_total: int, unclaimed: list[dict[str, Any]], cols: list[str],
    *, nota: str = "", list_rows: bool = True,
) -> None:
    nao = total - claimed
    leak = "VAZA" if abs(nao) >= Decimal("1") else "ok"
    print(f"\n  {tabela}  -> {destino}")
    print(f"    total ........ R$ {_fmt(total)}  ({n_total} linhas)")
    print(f"    reivindicado . R$ {_fmt(claimed)}")
    print(f"    NAO-reivind. . R$ {_fmt(nao)}  ({len(unclaimed)} linhas)  [{leak}]")
    if nota:
        print(f"    nota: {nota}")
    if list_rows and unclaimed:
        for r in unclaimed[:10]:
            cells = "  ".join(
                (f"{float(r[c]):>14,.2f}" if c == "valor" else f"{str(r.get(c) or '')[:26]}")
                for c in cols
            )
            print(f"      - {cells}")


async def _coverage(db: AsyncSession, ua: UnidadeAdministrativa, data: date) -> None:
    """Prova de fechamento por tabela-fonte: Σ(tabela) = reivindicado + NAO.

    As linhas NAO-reivindicadas sao o "dado desconsiderado" — passam por NENHUM
    filtro de linha do balanco. Algumas exclusoes sao ESPERADAS (WOP, PDD que
    vai pro granular); outras sao VAZAMENTO real (COSIF nao classificado, classe
    MEC desconhecida)."""
    tid, ua_id, cnpj, ua_nome = ua.tenant_id, ua.id, ua.cnpj or "", ua.nome
    print(f"\n{'='*74}")
    print(f" COBERTURA POR TABELA-FONTE — {ua.nome} — {data.isoformat()}")
    print(f"{'='*74}")

    # 1. Renda Fixa -> Titulos Publicos + Op. Estruturadas (via COSIF)
    rules = await load_rules_cache(db)
    ov = await load_overrides(db, tenant_id=tid, fundo_id=ua_id)
    rf = (await db.execute(
        select(PosicaoRendaFixa.codigo, PosicaoRendaFixa.nome_do_papel,
               PosicaoRendaFixa.codigo_lastro, PosicaoRendaFixa.quantidade,
               PosicaoRendaFixa.valor_bruto)
        .where(PosicaoRendaFixa.tenant_id == tid)
        .where(PosicaoRendaFixa.unidade_administrativa_id == ua_id)
        .where(PosicaoRendaFixa.data_posicao == data)
    )).all()
    total = claimed = ZERO
    unclaimed: list[dict[str, Any]] = []
    for cod, nome, lastro, qtd, vb in rf:
        res = classify(silver_origin="wh_posicao_renda_fixa",
                       row={"codigo": cod, "nome_do_papel": nome,
                            "codigo_lastro": lastro, "quantidade": qtd},
                       rules_cache=rules, overrides=ov)
        drv = _driver_gestor_for_cosif(res.cosif)
        v = Decimal(vb or 0)
        total += v
        if drv in ("titulos_publicos", "op_estruturadas"):
            claimed += v
        else:
            unclaimed.append({"codigo": cod, "nome_do_papel": nome,
                              "cosif": res.cosif, "driver": str(drv), "valor": v})
    unclaimed.sort(key=lambda r: abs(r["valor"]), reverse=True)
    _print_cov("wh_posicao_renda_fixa", "Titulos Publicos + Op. Estruturadas",
               total, claimed, len(rf), unclaimed,
               ["codigo", "nome_do_papel", "cosif", "driver", "valor"],
               nota="NAO-reivindicado aqui = COSIF que nao mapeia pra TPF/Op.Estr "
                    "(debenture, CRI, cota emitida, nao classificado) = VAZAMENTO real")

    # 2. Cota Fundo -> Fundos DI (externos). Internos deveriam estar na DC.
    cf = (await db.execute(
        select(PosicaoCotaFundo.ativo_codigo, PosicaoCotaFundo.ativo_nome,
               PosicaoCotaFundo.valor_liquido)
        .where(PosicaoCotaFundo.tenant_id == tid)
        .where(PosicaoCotaFundo.unidade_administrativa_id == ua_id)
        .where(PosicaoCotaFundo.data_posicao == data)
    )).all()
    total = claimed = ZERO
    unclaimed = []
    for cod, nome, vl in cf:
        v = Decimal(vl or 0)
        total += v
        if _is_fundo_externo(nome or "", ua_nome):
            claimed += v
        else:
            unclaimed.append({"ativo_codigo": cod, "ativo_nome": nome, "valor": v})
    _print_cov("wh_posicao_cota_fundo", "Fundos DI (externos)",
               total, claimed, len(cf), unclaimed,
               ["ativo_codigo", "ativo_nome", "valor"],
               nota="NAO-reivindicado = fundos INTERNOS (carteira DC vista como cota) "
                    "— ESPERADO, contado na DC granular (nao vaza se DC os captura)")

    # 3. Outros Ativos -> linha Outros Ativos (exclui PDD e TPF)
    oa = (await db.execute(
        select(PosicaoOutrosAtivos.codigo, PosicaoOutrosAtivos.descricao_tipo_de_ativo,
               PosicaoOutrosAtivos.valor_total)
        .where(PosicaoOutrosAtivos.tenant_id == tid)
        .where(PosicaoOutrosAtivos.unidade_administrativa_id == ua_id)
        .where(PosicaoOutrosAtivos.data_posicao == data)
    )).all()
    total = claimed = ZERO
    unclaimed = []
    for cod, tipo, vt in oa:
        v = Decimal(vt or 0)
        total += v
        if cod != "PDD" and not _is_titulo_publico(tipo or ""):
            claimed += v
        else:
            motivo = "PDD->granular" if cod == "PDD" else "TPF->renda_fixa"
            unclaimed.append({"codigo": cod, "tipo": f"{tipo} ({motivo})", "valor": v})
    _print_cov("wh_posicao_outros_ativos", "Outros Ativos",
               total, claimed, len(oa), unclaimed,
               ["codigo", "tipo", "valor"],
               nota="NAO-reivindicado = PDD (vai pro granular) ou TPF (vem da renda_fixa) "
                    "— ESPERADO se a contagem dupla nao acontecer")

    # 4. Estoque -> DC + PDD (exclui WOP). WOP e exclusao ESPERADA.
    est = (await db.execute(
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_presente), ZERO),
               func.count())
        .where(EstoqueRecebivel.tenant_id == tid)
        .where(EstoqueRecebivel.fundo_doc == cnpj)
        .where(EstoqueRecebivel.data_referencia == data)
    )).one()
    wop = (await db.execute(
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_presente), ZERO),
               func.count())
        .where(EstoqueRecebivel.tenant_id == tid)
        .where(EstoqueRecebivel.fundo_doc == cnpj)
        .where(EstoqueRecebivel.data_referencia == data)
        .where(EstoqueRecebivel.faixa_pdd == "WOP")
    )).one()
    _print_cov("wh_estoque_recebivel", "Direitos Creditorios (valor_presente)",
               Decimal(est[0]), Decimal(est[0]) - Decimal(wop[0]), int(est[1]),
               [{"x": "WOP", "valor": Decimal(wop[0])}] if wop[0] else [],
               ["x", "valor"], list_rows=bool(wop[0]),
               nota=f"NAO-reivindicado = WOP ({int(wop[1])} linhas) — ESPERADO "
                    "(write-off 100% provisionado, efeito liquido 0)")

    # 5. CPR -> Contas a Receber (>0) + a Pagar (<0). So valor==0 fica de fora.
    cpr_tot = (await db.execute(
        select(func.coalesce(func.sum(CprMovimento.valor), ZERO), func.count())
        .where(CprMovimento.tenant_id == tid)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data)
    )).one()
    cpr_zero = (await db.execute(
        select(func.count())
        .where(CprMovimento.tenant_id == tid)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data)
        .where(CprMovimento.valor == 0)
    )).scalar()
    _print_cov("wh_cpr_movimento", "Contas a Receber + a Pagar (net)",
               Decimal(cpr_tot[0]), Decimal(cpr_tot[0]), int(cpr_tot[1]), [],
               ["x"], nota=f"cobertura total (>0 e <0); {cpr_zero} linhas valor==0")

    # 6. MEC -> Senior + Mezanino (passivo) + Sub (fonte). Classe nao reconhecida = VAZA.
    mec = (await db.execute(
        select(MecEvolucaoCotas.carteira_cliente_nome, MecEvolucaoCotas.carteira_cliente_id,
               MecEvolucaoCotas.patrimonio)
        .where(MecEvolucaoCotas.tenant_id == tid)
        .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
        .where(MecEvolucaoCotas.data_posicao == data)
    )).all()
    total = classified = ZERO
    unclaimed = []
    for nome, cid, pat in mec:
        v = Decimal(pat or 0)
        total += v
        if _is_sub_jr(nome or "", ua_nome) or _is_mezanino(nome or "") or _is_senior(nome or ""):
            classified += v
        else:
            unclaimed.append({"cliente_id": cid, "carteira": nome, "valor": v})
    _print_cov("wh_mec_evolucao_cotas", "Sub (fonte) + Senior + Mezanino",
               total, classified, len(mec), unclaimed,
               ["cliente_id", "carteira", "valor"],
               nota="NAO-classificado = clienteNome que nao casa Sub/Mez/Sen = VAZAMENTO "
                    "(classe invisivel ao balanco E a fonte MEC)")
    print()


async def run(
    fundo: str, data_arg: str | None, drill: str | None, top: int,
    scan: int | None, scan_tol: Decimal, compare: str | None, coverage: bool,
) -> None:
    async with AsyncSessionLocal() as db:
        ua = await _resolve_ua(db, fundo)
        cnpj = ua.cnpj or ""
        if compare:
            await _compare(db, ua, [date.fromisoformat(s.strip()) for s in compare.split(",")])
            return
        if scan:
            await _scan(db, ua, scan, scan_tol)
            return
        if coverage:
            data_cov = await _resolve_data(db, tenant_id=ua.tenant_id, cnpj=cnpj, data_arg=data_arg)
            await _coverage(db, ua, data_cov)
            return
        data_d0 = await _resolve_data(db, tenant_id=ua.tenant_id, cnpj=cnpj, data_arg=data_arg)
        d1 = await dia_util_anterior_qitech(
            db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=data_d0,
        )

        bal = await compute_balanco_estrutural(
            db, tenant_id=ua.tenant_id, ua_id=ua.id, data_d0=data_d0,
        )
        oficial = {
            ln.key: (ln.label, ln.natureza, Decimal(ln.d0))
            for ln in [*bal.ativos, *bal.passivos]
        }
        providers = _build_providers(
            tenant_id=ua.tenant_id, ua_id=ua.id, ua_nome=ua.nome, cnpj=cnpj, data=data_d0,
        )

        print(f"\n{'='*78}")
        print(f" AUDITORIA BALANCO ESTRUTURAL — {ua.nome} (doc {cnpj})")
        print(f" D0 = {data_d0}   D-1 = {d1}")
        print(f"{'='*78}")

        if drill:
            await _print_drill(db, providers, oficial, drill, top)
            return

        print(f"\n{'LINHA':<26}{'BALANCO':>17}{'RECOMPUTADO':>17}{'n':>6}  SELO")
        print(f"{'-'*78}")
        total_div = ZERO
        for key, (label, natureza, val_bal) in oficial.items():
            prov = providers.get(key)
            if prov is None:
                print(f"{label:<26}{_fmt(val_bal):>17}{'(sem provider)':>17}")
                continue
            org = await prov(db)
            diff = val_bal - org.soma
            total_div += abs(diff)
            selo = "OK" if abs(diff) < TOL else f"DIVERGE {_fmt(diff).strip()}"
            tag = "" if natureza == "ativo" else f" [{natureza}]"
            print(f"{label+tag:<26}{_fmt(val_bal):>17}{_fmt(org.soma):>17}"
                  f"{len(org.rows):>6}  {selo}")

        print(f"{'-'*78}")
        print(f"{'TOTAL ATIVO':<26}{_fmt(bal.total_ativo_d0):>17}")
        print(f"{'TOTAL PASSIVO':<26}{_fmt(bal.total_passivo_d0):>17}")
        print(f"{'PL SUB (deduzido)':<26}{_fmt(bal.pl_sub_d0):>17}")

        rec = bal.reconciliacao
        print(f"\n{'RECONCILIACAO vs MEC':<26}")
        print(f"  PL Sub fonte (MEC) D0 ....... R$ {_fmt(rec.pl_fonte_d0)}")
        print(f"  PL Sub deduzido D0 .......... R$ {_fmt(bal.pl_sub_d0)}")
        print(f"  Residuo nivel D0 ............ R$ {_fmt(rec.residuo_d0)}")
        print(f"  Residuo do DIA (dD0-dD-1) ... R$ {_fmt(rec.residuo_delta)}"
              f"   ({'dentro tol' if rec.dentro_tolerancia else 'FORA tol'})")
        print(f"\n  Soma |divergencias bottom-up| das linhas: R$ {_fmt(total_div)}")

        if bal.nao_reconhecidos:
            print(f"\n  NAO-RECONHECIDOS ({len(bal.nao_reconhecidos)}):")
            for i in bal.nao_reconhecidos[:15]:
                print(f"    - [{i.fonte}/{i.endpoint}] {i.label}: "
                      f"D-1 {_fmt(i.valor_d_prev)} -> D0 {_fmt(i.valor_d0)} "
                      f"({i.modo}, afeta {i.driver_afetado})")
        print()


async def _print_drill(
    db: AsyncSession,
    providers: dict[str, Callable[[AsyncSession], Awaitable[Origem]]],
    oficial: dict[str, tuple[str, str, Decimal]],
    key: str,
    top: int,
) -> None:
    prov = providers.get(key)
    if prov is None:
        raise SystemExit(f"Linha {key!r} nao tem provider. Keys: {', '.join(providers)}")
    label, natureza, val_bal = oficial.get(key, (key, "?", ZERO))
    org = await prov(db)
    diff = val_bal - org.soma
    print(f"\n DRILL: {label} ({key}) [{natureza}]")
    print(f" Balanco: R$ {_fmt(val_bal).strip()}   "
          f"Recomputado: R$ {_fmt(org.soma).strip()}   "
          f"{'OK' if abs(diff) < TOL else f'DIVERGE R$ {_fmt(diff).strip()}'}")
    print(f" {len(org.rows)} linhas-fonte (top {top} por valor):\n")
    header = "".join(f"{c:<24}" if c not in ("valor",) else f"{'valor':>16}"
                     for c in org.cols)
    print(header)
    print("-" * len(header))
    for r in org.rows[:top]:
        line = ""
        for c in org.cols:
            if c == "valor":
                line += f"{float(r[c] or 0):>16,.2f}"
            else:
                line += f"{str(r.get(c) or '')[:22]:<24}"
        print(line)
    print()


def main() -> None:
    p = argparse.ArgumentParser(description="Auditoria do balanco estrutural Cota Sub")
    p.add_argument("--fundo", default="REALINVEST", help="substring do nome da UA")
    p.add_argument("--data", default=None, help="YYYY-MM-DD (default: ultima com estoque)")
    p.add_argument("--drill", default=None, help="line_key pra listar linhas-fonte")
    p.add_argument("--top", type=int, default=15, help="linhas no drill")
    p.add_argument("--scan", type=int, default=None, metavar="N",
                   help="roda o balanco nos ultimos N dias e mostra residuo por dia")
    p.add_argument("--tol", type=float, default=1.0,
                   help="tolerancia BRL do scan (default 1.0 = _TOL_RESIDUO_DIA)")
    p.add_argument("--compare", default=None, metavar="D1,D2,...",
                   help="compara as 13 linhas (valor+contagem) entre datas")
    p.add_argument("--coverage", action="store_true",
                   help="prova de fechamento por tabela-fonte (lista dado desconsiderado)")
    args = p.parse_args()
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    async def _main() -> None:
        try:
            await run(args.fundo, args.data, args.drill, args.top,
                      args.scan, Decimal(str(args.tol)), args.compare, args.coverage)
        finally:
            await engine.dispose()

    asyncio.run(_main())


if __name__ == "__main__":
    main()
