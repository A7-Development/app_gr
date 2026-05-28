"""Controladoria · Cota Sub · drill "ver origem" (2026-05-28).

Generic drill-to-source for the 9 balance lines that lack a rich drill
(Renda Fixa, Op. Estruturadas, Fundos DI, Compromissada, Outros Ativos,
Tesouraria, Conta Corrente, Cota Senior, Cota Mezanino). It lists the source
rows that compose the line and proves closure: Σ(rows) == line value.

`valor_balanco` is taken from the SAME official `_sum_*` helper that feeds
`compute_balanco_estrutural` (i.e. the number shown on the page); `soma` is the
Σ of the rows reproduced here. `fecha = |valor_balanco - soma| < 0.01` is the
self-guard — if the row reproduction drifts from the helper, the badge flips.

Reads silver only (CLAUDE.md §13.2.1). The rich drills (DC/PDD/CPR) keep their
own services; this covers everything else with a uniform shape.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub_drill import (
    DrillOrigemResponse,
    OrigemLinha,
)
from app.modules.controladoria.services.balanco_patrimonial import (
    _sum_saldo_conta_corrente,
)
from app.modules.controladoria.services.cota_sub import (
    ZERO,
    _driver_for_nome_papel,
    _is_fundo_externo,
    _is_mezanino,
    _is_senior,
    _is_titulo_publico,
    _mec_classes,
    _sum_compromissada,
    _sum_fundos_di,
    _sum_op_estruturadas,
    _sum_outros_ativos_nao_tpf,
    _sum_tesouraria,
    _sum_titulos_publicos,
)
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.posicao_compromissada import PosicaoCompromissada
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
from app.warehouse.posicao_outros_ativos import PosicaoOutrosAtivos
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente
from app.warehouse.saldo_tesouraria import SaldoTesouraria

_TOL = Decimal("0.01")

# line_key -> (label exibido, tabela silver de origem). Apenas as 9 linhas SEM
# drill rico — DC/PDD/CPR sao tratados pelos seus proprios servicos.
_META: dict[str, tuple[str, str]] = {
    "titulos_publicos":     ("Títulos Públicos", "wh_posicao_renda_fixa"),
    "op_estruturadas":      ("Op. Estruturadas", "wh_posicao_renda_fixa"),
    "fundos_di":            ("Fundos DI", "wh_posicao_cota_fundo"),
    "compromissada":        ("Compromissada", "wh_posicao_compromissada"),
    "outros_ativos":        ("Outros Ativos", "wh_posicao_outros_ativos"),
    "tesouraria":           ("Tesouraria", "wh_saldo_tesouraria"),
    "saldo_conta_corrente": ("Saldo Conta Corrente", "wh_saldo_conta_corrente"),
    "senior":               ("Cota Senior", "wh_mec_evolucao_cotas"),
    "mezanino":             ("Cota Mezanino", "wh_mec_evolucao_cotas"),
}

SUPPORTED_KEYS = frozenset(_META)


# ── Row providers — reproduzem o filtro EXATO do helper _sum_* correspondente ──


async def _rows_renda_fixa(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date, driver: str,
) -> list[OrigemLinha]:
    """Linhas-fonte de Titulos Publicos / Op. Estruturadas. Classifica por
    `nome_do_papel` (QiTech) via _driver_for_nome_papel; detalhe = emitente
    (dado real da QiTech, nao COSIF)."""
    stmt = (
        select(
            PosicaoRendaFixa.codigo,
            PosicaoRendaFixa.nome_do_papel,
            PosicaoRendaFixa.emitente,
            PosicaoRendaFixa.codigo_lastro,
            PosicaoRendaFixa.valor_bruto,
        )
        .where(PosicaoRendaFixa.tenant_id == tenant_id)
        .where(PosicaoRendaFixa.unidade_administrativa_id == ua_id)
        .where(PosicaoRendaFixa.data_posicao == data)
    )
    out: list[OrigemLinha] = []
    for codigo, nome, emitente, codigo_lastro, valor_bruto in (await db.execute(stmt)).all():
        if _driver_for_nome_papel(nome, codigo_lastro) != driver:
            continue
        out.append(OrigemLinha(
            identificador=str(codigo or ""),
            descricao=str(nome or ""),
            detalhe=str(emitente or "") or None,
            valor=Decimal(valor_bruto or 0),
        ))
    return out


async def _rows_fundos_di(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, ua_nome: str, data: date,
) -> list[OrigemLinha]:
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
    return [
        OrigemLinha(identificador=str(cod or ""), descricao=str(nome or ""),
                    detalhe=None, valor=Decimal(v or 0))
        for cod, nome, v in (await db.execute(stmt)).all()
        if _is_fundo_externo(nome or "", ua_nome)
    ]


async def _rows_compromissada(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date,
) -> list[OrigemLinha]:
    stmt = (
        select(
            PosicaoCompromissada.codigo,
            PosicaoCompromissada.carteira_cliente_nome,
            PosicaoCompromissada.valor_bruto,
        )
        .where(PosicaoCompromissada.tenant_id == tenant_id)
        .where(PosicaoCompromissada.unidade_administrativa_id == ua_id)
        .where(PosicaoCompromissada.data_posicao == data)
    )
    return [
        OrigemLinha(identificador=str(cod or ""), descricao=str(nome or ""),
                    detalhe=None, valor=Decimal(v or 0))
        for cod, nome, v in (await db.execute(stmt)).all()
    ]


async def _rows_outros_ativos(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date,
) -> list[OrigemLinha]:
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
    return [
        OrigemLinha(identificador=str(cod or ""), descricao=str(tipo or ""),
                    detalhe=None, valor=Decimal(v or 0))
        for cod, tipo, v in (await db.execute(stmt)).all()
        if not _is_titulo_publico(tipo or "")
    ]


async def _rows_tesouraria(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date,
) -> list[OrigemLinha]:
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
    return [
        OrigemLinha(identificador=str(desc or ""), descricao=str(cart or ""),
                    detalhe=None, valor=Decimal(v or 0))
        for desc, cart, v in (await db.execute(stmt)).all()
    ]


async def _rows_conta_corrente(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date,
) -> list[OrigemLinha]:
    # TODAS as contas, inclusive CONCILIA (contra-saldo) — espelha
    # _sum_saldo_conta_corrente (Σ ~ 0 por construcao).
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
    return [
        OrigemLinha(identificador=str(cod or ""), descricao=str(inst or ""),
                    detalhe=None, valor=Decimal(v or 0))
        for cod, inst, v in (await db.execute(stmt)).all()
    ]


async def _rows_mec_classe(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date, classe: str,
) -> list[OrigemLinha]:
    pred = _is_senior if classe == "senior" else _is_mezanino
    stmt = (
        select(
            MecEvolucaoCotas.carteira_cliente_id,
            MecEvolucaoCotas.carteira_cliente_nome,
            MecEvolucaoCotas.patrimonio,
        )
        .where(MecEvolucaoCotas.tenant_id == tenant_id)
        .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
        .where(MecEvolucaoCotas.data_posicao == data)
    )
    return [
        OrigemLinha(identificador=str(cid or ""), descricao=str(nome or ""),
                    detalhe=None, valor=Decimal(pat or 0))
        for cid, nome, pat in (await db.execute(stmt)).all()
        if pred(nome or "")
    ]


async def _rows_for(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, ua_nome: str,
    data: date, line_key: str,
) -> list[OrigemLinha]:
    if line_key in ("titulos_publicos", "op_estruturadas"):
        return await _rows_renda_fixa(db, tenant_id, ua_id, data, line_key)
    if line_key == "fundos_di":
        return await _rows_fundos_di(db, tenant_id, ua_id, ua_nome, data)
    if line_key == "compromissada":
        return await _rows_compromissada(db, tenant_id, ua_id, data)
    if line_key == "outros_ativos":
        return await _rows_outros_ativos(db, tenant_id, ua_id, data)
    if line_key == "tesouraria":
        return await _rows_tesouraria(db, tenant_id, ua_id, data)
    if line_key == "saldo_conta_corrente":
        return await _rows_conta_corrente(db, tenant_id, ua_id, data)
    if line_key in ("senior", "mezanino"):
        return await _rows_mec_classe(db, tenant_id, ua_id, data, line_key)
    raise ValueError(f"line_key sem drill de origem: {line_key!r}")


async def _valor_balanco(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, ua_nome: str,
    data: date, line_key: str,
) -> Decimal:
    """Valor OFICIAL da linha — mesmo helper _sum_* que alimenta o balanco."""
    if line_key == "titulos_publicos":
        return await _sum_titulos_publicos(db, tenant_id, ua_id, data)
    if line_key == "op_estruturadas":
        return await _sum_op_estruturadas(db, tenant_id, ua_id, data)
    if line_key == "fundos_di":
        return await _sum_fundos_di(db, tenant_id, ua_id, ua_nome, data)
    if line_key == "compromissada":
        return await _sum_compromissada(db, tenant_id, ua_id, data)
    if line_key == "outros_ativos":
        return await _sum_outros_ativos_nao_tpf(db, tenant_id, ua_id, data)
    if line_key == "tesouraria":
        return await _sum_tesouraria(db, tenant_id, ua_id, data)
    if line_key == "saldo_conta_corrente":
        return await _sum_saldo_conta_corrente(db, tenant_id=tenant_id, ua_id=ua_id, data=data)
    if line_key in ("senior", "mezanino"):
        classes = await _mec_classes(db, tenant_id, ua_id, ua_nome, data)
        return classes[line_key]
    raise ValueError(f"line_key sem drill de origem: {line_key!r}")


async def compute_drill_origem(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    line_key: str,
) -> DrillOrigemResponse:
    """Lista as linhas-fonte de uma linha do balanco + prova de fechamento."""
    if line_key not in _META:
        raise ValueError(
            f"line_key {line_key!r} nao tem drill de origem. "
            f"Suportados: {', '.join(sorted(_META))}"
        )
    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada")

    label, fonte = _META[line_key]
    linhas = await _rows_for(
        db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome,
        data=data_d0, line_key=line_key,
    )
    linhas.sort(key=lambda r: abs(r.valor), reverse=True)
    soma = sum((r.valor for r in linhas), ZERO)
    valor_balanco = await _valor_balanco(
        db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome,
        data=data_d0, line_key=line_key,
    )
    diferenca = valor_balanco - soma

    return DrillOrigemResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        linha_key=line_key,
        linha_label=label,
        fonte=fonte,
        linhas=linhas,
        soma=soma,
        valor_balanco=valor_balanco,
        diferenca=diferenca,
        fecha=abs(diferenca) < _TOL,
    )
