"""Controladoria · Cota Sub — serie diaria da variacao da cota por competencia.

MASTER do master-detail da aba "Resumo do dia" (handoff Strata 2026-06-05). Em
vez de N chamadas ao /variacao/resumo (uma por dia util, cada uma rodando o
balanco + 6 drills), esta serie e BARATA: le o PL Sub MEC (oficial) de
`wh_mec_evolucao_cotas` para todos os dias da competencia numa unica passada e
diferencia dias uteis consecutivos.

Por que MEC (oficial) e nao o calc (metodo gestor): a serie e uma visao geral
para SELECIONAR o dia. O numero oficial e o do MEC (cota auditada). O drill do
dia escolhido (VariacaoWaterfall) decompoe o calc e expoe a reconciliacao
calc vs MEC no rodape — la o residuo (normalmente ~0) fica explicito. Mantem o
endpoint leve e a fonte da "variacao do dia" coerente com a cota oficial.
"""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.variacao_diaria import VariacaoDiariaSeriePonto
from app.modules.controladoria.services.cota_sub import ZERO, _is_sub_jr
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas


async def _pl_e_capital_sub_mec_por_data(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    inicio: date,
    fim: date,
) -> dict[date, tuple[Decimal, Decimal]]:
    """(PL Sub MEC, capital liquido do Sub) agregados por `data_posicao`.

    Uma unica query sobre `wh_mec_evolucao_cotas`; classifica a carteira pela
    mesma regra do balanco (`_is_sub_jr`). Retorna por data:
      - patrimonio (PL Sub)
      - capital liquido do Sub = entradas - saidas + aporte - retirada (mesma
        formula do `efeito_capital` em compute_decomposicao_classes_mec). E o
        aporte/resgate do COTISTA subordinado no dia — NEUTRO na rentabilidade,
        precisa ser segregado da variacao da cota (senao a serie mostra um pico
        de "valorizacao" que e capital, nao resultado — bug 18/06).
    """
    stmt = (
        select(
            MecEvolucaoCotas.data_posicao,
            MecEvolucaoCotas.carteira_cliente_nome,
            MecEvolucaoCotas.patrimonio,
            MecEvolucaoCotas.entradas,
            MecEvolucaoCotas.saidas,
            MecEvolucaoCotas.aporte,
            MecEvolucaoCotas.retirada,
        )
        .where(MecEvolucaoCotas.tenant_id == tenant_id)
        .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
        .where(MecEvolucaoCotas.data_posicao >= inicio)
        .where(MecEvolucaoCotas.data_posicao <= fim)
    )
    rows = (await db.execute(stmt)).all()
    pl: dict[date, Decimal] = {}
    cap: dict[date, Decimal] = {}
    for data_posicao, nome, patrimonio, ent, sai, ap, ret in rows:
        if not _is_sub_jr(nome, ua_nome):
            continue
        pl[data_posicao] = pl.get(data_posicao, ZERO) + Decimal(patrimonio or 0)
        cap[data_posicao] = cap.get(data_posicao, ZERO) + (
            Decimal(ent or 0) - Decimal(sai or 0) + Decimal(ap or 0) - Decimal(ret or 0)
        )
    return {d: (pl[d], cap.get(d, ZERO)) for d in pl}


async def compute_variacao_diaria_serie(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    competencia: str,  # "YYYY-MM"
) -> list[VariacaoDiariaSeriePonto]:
    """Serie diaria da variacao do PL Sub MEC na competencia.

    Retorna UM ponto por dia-calendario do mes (CLAUDE.md §14.6: nada e cortado).
    Dias sem snapshot (fim de semana, feriado, futuro, falha de ETL) entram com
    `variacao_cota=None`. O delta do primeiro dia util usa como D-1 a ultima data
    com snapshot ANTES do mes (ancora), buscada separadamente.
    """
    try:
        year_s, month_s = competencia.split("-")
        year, month = int(year_s), int(month_s)
        primeiro = date(year, month, 1)
        ultimo = date(year, month, monthrange(year, month)[1])
    except (ValueError, IndexError) as exc:
        raise ValueError(f"competencia invalida: {competencia!r} (esperado YYYY-MM)") from exc

    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada")

    raw = await _pl_e_capital_sub_mec_por_data(
        db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome,
        inicio=primeiro, fim=ultimo,
    )
    pl_por_data = {d: v[0] for d, v in raw.items()}
    cap_por_data = {d: v[1] for d, v in raw.items()}

    # Ancora = ultima data com PL Sub MEC nos ~60 dias ANTES do mes (cobre
    # feriados prolongados/paradas curtas; gap maior ainda zera o 1o delta, o
    # que e correto — nao ha D-1 conhecido).
    ancora_pl: Decimal | None = None
    pre = await _pl_e_capital_sub_mec_por_data(
        db, tenant_id=tenant_id, ua_id=ua_id, ua_nome=ua.nome,
        inicio=primeiro - timedelta(days=60), fim=primeiro - timedelta(days=1),
    )
    if pre:
        ancora_pl = pre[max(pre)][0]

    # Dias com snapshot, em ordem — alimentam a cadeia de D-1.
    datas_com_dado = sorted(pl_por_data.keys())

    # Para cada data com dado, qual o PL do dia util anterior (D-1).
    prev_pl: dict[date, Decimal | None] = {}
    anterior = ancora_pl
    for d in datas_com_dado:
        prev_pl[d] = anterior
        anterior = pl_por_data[d]

    hoje = date.today()
    serie: list[VariacaoDiariaSeriePonto] = []
    dia = primeiro
    while dia <= ultimo:
        eh_futuro = dia > hoje
        if dia in pl_por_data and not eh_futuro:
            pl_d = pl_por_data[dia]
            d1_pl = prev_pl.get(dia)
            # Variacao da cota = RENTABILIDADE = ΔPL - capital do Sub no dia. O
            # aporte/resgate do cotista subordinado nao e valorizacao (entra caixa
            # e cota juntos); segregamos pra serie nao mostrar pico de capital.
            variacao = (pl_d - d1_pl - cap_por_data.get(dia, ZERO)) if d1_pl is not None else None
            pct = (
                (variacao / d1_pl * Decimal(100))
                if (variacao is not None and d1_pl not in (None, ZERO))
                else None
            )
            serie.append(
                VariacaoDiariaSeriePonto(
                    data=dia, variacao_cota=variacao, variacao_pct=pct,
                    eh_dia_util=True, eh_futuro=False,
                )
            )
        else:
            serie.append(
                VariacaoDiariaSeriePonto(
                    data=dia, variacao_cota=None, variacao_pct=None,
                    eh_dia_util=dia.weekday() < 5, eh_futuro=eh_futuro,
                )
            )
        dia += timedelta(days=1)

    return serie
