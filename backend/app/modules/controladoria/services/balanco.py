"""Controladoria · Cota Sub — service de Balanco Diario.

Monta o balanco patrimonial diario do FIDC sob a otica do cotista subordinado:

    ATIVO
      Tesouraria, Compromissada, Titulos Publicos, Fundos DI,
      Direitos Crediorios, DC estruturada, Outros Ativos, (-) PDD
    PASSIVO  (otica Sub Jr)
      Contas a Pagar, Cota Mezanino, Cota Senior
    = Cota Subordinada (residual = Subtotal Ativo - Subtotal Passivo)

Origem dos dados — APENAS silver canonico (CLAUDE.md §13.2.1):

    Tesouraria        ← wh_saldo_tesouraria + wh_saldo_conta_corrente (≠ CONCILI)
    Compromissada     ← wh_posicao_compromissada
    Titulos Publicos  ← wh_posicao_renda_fixa (papel ∈ NTN-*, LFT, LTN)
    Fundos DI         ← wh_posicao_cota_fundo (codigo ∉ REAL*)
    Direitos Cred.    ← wh_posicao_cota_fundo (codigo ∈ REAL*)
    DC estruturada    ← wh_posicao_renda_fixa (papel ∈ NCPX, VCNC)
    Outros Ativos     ← wh_cpr_movimento (valor>0) + wh_saldo_conta_corrente (CONCILI)
    PDD               ← wh_posicao_outros_ativos (codigo='PDD')
    Contas a Pagar    ← wh_cpr_movimento (valor<0)
    Cota Mezanino     ← wh_posicao_renda_fixa (papel='MEZAN', filtro Sub: clienteId='REALINVEST' negativo)
    Cota Senior       ← wh_posicao_renda_fixa (papel='SRP', idem)

Filtro padrao para POV Sub Jr: usar APENAS rows onde `carteira_cliente_id`
bate com a UA principal do fundo (ex.: 'REALINVEST', sem sufixo SEN/MEZ).
Os cotas Sr/Mez ja vem como NEGATIVO em REALINVEST porque a partida dobrada
do QiTech materializa as duas pontas. Na exibicao, viramos pra positivo no
Passivo (ABS).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub import (
    BalanceRow,
    BalancoResponse,
)
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.posicao_compromissada import PosicaoCompromissada
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
from app.warehouse.posicao_outros_ativos import PosicaoOutrosAtivos
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente
from app.warehouse.saldo_tesouraria import SaldoTesouraria

ZERO = Decimal("0")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers — classificacao
# ─────────────────────────────────────────────────────────────────────────────

"""COSIF 1.3.1.10.07 NOTAS DO TESOURO NACIONAL — apenas titulos puros (NTN-*).

CUIDADO: papeis terminados em ' O' ou sem hifen (ex.: 'NTN O', 'LTNO') sao
operacoes COMPROMISSADAS materializadas tambem na silver de RF (duplicidade
QiTech entre rf e rf-compromissadas). Esses ja entram na linha
'Compromissada' (1.2.1.10.05) — NAO contar duas vezes.

Convencao nos dados QiTech (validada com REALINVEST 2026-04-24):
  - 'NTN-B', 'NTN-F'  -> titulo puro (1.3.1.10.07)
  - 'NTN O', 'LTNO'   -> compromissada (1.2.1.10.05)
"""


def _is_titulo_publico(papel: str | None) -> bool:
    p = (papel or "").upper()
    # Apenas papeis com hifen (titulo puro). Exclui 'NTN O', 'LTNO' (compromissadas).
    return p.startswith("NTN-")


def _is_dc_estruturada(papel: str | None) -> bool:
    return (papel or "").upper() in ("NCPX", "VCNC")


def _dia_util_anterior(d: date) -> date:
    """D-1 simples (apenas finais de semana). TODO: calendario B3/Anbima."""
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


def _row(
    rid:       str,
    rtype:     str,
    label:     str,
    *,
    cosif:     str | None             = None,
    descricao: str | None             = None,
    source:    str | None             = None,
    d1:        Decimal | None         = None,
    d0:        Decimal | None         = None,
    sub_rows:  list[BalanceRow] | None = None,
) -> BalanceRow:
    """Builder helper. delta = d0 - d1 quando ambos presentes."""
    delta: Decimal | None = None
    if d1 is not None and d0 is not None:
        delta = d0 - d1
    return BalanceRow(
        id        = rid,
        type      = rtype,  # type: ignore[arg-type]
        label     = label,
        cosif     = cosif,
        descricao = descricao,
        source    = source,
        d1        = d1,
        d0        = d0,
        delta     = delta,
        sub_rows  = sub_rows or None,
    )


def _filter_nonzero(subs: list[BalanceRow]) -> list[BalanceRow]:
    """Remove sub-rows com d1=0, d0=0 e delta=0 (ruido visual)."""
    return [
        r for r in subs
        if (r.d1 and r.d1 != 0) or (r.d0 and r.d0 != 0) or (r.delta and r.delta != 0)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers — cada um devolve {data: Decimal} para D-1 e D0
# ─────────────────────────────────────────────────────────────────────────────


async def _sum_bancos_privados(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, datas: list[date]
) -> dict[date, Decimal]:
    """BANCOS PRIVADOS - CONTA (1.1.2.80.00) — POV Sub Jr.

    Soma:
      - SaldoTesouraria (todas as classes; 001 BANCOS CONTA MOVIMENTO)
      - SaldoContaCorrente filtrando codigo != 'CONCILIA' (002 BRADESCO + 007 SINGULARE)

    Filtro 'codigo != CONCILIA' (em vez de 'descricao NOT LIKE CONCILI') eh
    proposital: 'SOCOPA-CONCILIAÇÃO' tem 'CONCILI' no descricao mas eh a CC
    da SINGULARE (CC bancaria real, vai pra Ativo). Ja 'CREDITOS A CONCILIAR'
    tem codigo='CONCILIA' e vai pra Passivo (4.9.9.30.90).
    """
    out: dict[date, Decimal] = dict.fromkeys(datas, ZERO)

    # 001 BANCOS CONTA MOVIMENTO ← wh_saldo_tesouraria
    stmt_tes = (
        select(SaldoTesouraria.data_posicao,
               func.coalesce(func.sum(SaldoTesouraria.valor), ZERO))
        .where(SaldoTesouraria.tenant_id == tenant_id)
        .where(SaldoTesouraria.unidade_administrativa_id == ua_id)
        .where(SaldoTesouraria.data_posicao.in_(datas))
        .group_by(SaldoTesouraria.data_posicao)
    )
    for d, v in (await db.execute(stmt_tes)).all():
        out[d] = out.get(d, ZERO) + Decimal(v or 0)

    # 002 BRADESCO + 007 SINGULARE ← wh_saldo_conta_corrente (codigo != CONCILIA)
    stmt_cc = (
        select(SaldoContaCorrente.data_posicao,
               func.coalesce(func.sum(SaldoContaCorrente.valor_total), ZERO))
        .where(SaldoContaCorrente.tenant_id == tenant_id)
        .where(SaldoContaCorrente.unidade_administrativa_id == ua_id)
        .where(SaldoContaCorrente.data_posicao.in_(datas))
        .where(SaldoContaCorrente.codigo != "CONCILIA")
        .group_by(SaldoContaCorrente.data_posicao)
    )
    for d, v in (await db.execute(stmt_cc)).all():
        out[d] = out.get(d, ZERO) + Decimal(v or 0)

    return out


async def _sum_compromissada(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, datas: list[date]
) -> dict[date, Decimal]:
    out: dict[date, Decimal] = dict.fromkeys(datas, ZERO)
    stmt = (
        select(PosicaoCompromissada.data_posicao,
               func.coalesce(func.sum(PosicaoCompromissada.valor_bruto), ZERO))
        .where(PosicaoCompromissada.tenant_id == tenant_id)
        .where(PosicaoCompromissada.unidade_administrativa_id == ua_id)
        .where(PosicaoCompromissada.data_posicao.in_(datas))
        .group_by(PosicaoCompromissada.data_posicao)
    )
    for d, v in (await db.execute(stmt)).all():
        out[d] = Decimal(v or 0)
    return out


async def _renda_fixa_breakdown(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    datas: list[date],
) -> dict[date, dict[str, Decimal]]:
    """Le wh_posicao_renda_fixa filtrando carteira_cliente_id = nome cru da UA
    (POV Sub Jr) e classifica por nome_do_papel.

    Retorna:
        {
          data: {
            'titulos_publicos': Decimal,  # NTN-*, LFT, LTN
            'dc_estruturada':   Decimal,  # NCPX, VCNC
            'cota_mezanino':    Decimal,  # MEZAN (vem negativo, manter)
            'cota_senior':      Decimal,  # SRP (idem)
            'nao_classificado': Decimal,  # qualquer papel novo
          }
        }
    """
    out: dict[date, dict[str, Decimal]] = {
        d: {
            "titulos_publicos": ZERO,
            "dc_estruturada":   ZERO,
            "cota_mezanino":    ZERO,
            "cota_senior":      ZERO,
            "nao_classificado": ZERO,
        }
        for d in datas
    }
    # POV Sub Jr: carteira_cliente_id == primeiro token do nome da UA.
    # Ex.: UA 'REALINVEST FIDC' -> clienteId Sub Jr = 'REALINVEST'
    #      UA 'XPTO FIDC NP'    -> clienteId Sub Jr = 'XPTO'
    # As pontas contrarias (' SEN', ' MEZ') sao descartadas porque sao espelhos.
    cliente_id_principal = (ua_nome or "").upper().strip().split(" ", 1)[0]

    stmt = (
        select(
            PosicaoRendaFixa.data_posicao,
            PosicaoRendaFixa.nome_do_papel,
            func.coalesce(func.sum(PosicaoRendaFixa.valor_bruto), ZERO),
        )
        .where(PosicaoRendaFixa.tenant_id == tenant_id)
        .where(PosicaoRendaFixa.unidade_administrativa_id == ua_id)
        .where(PosicaoRendaFixa.data_posicao.in_(datas))
        .where(func.upper(PosicaoRendaFixa.carteira_cliente_id) == cliente_id_principal)
        .group_by(PosicaoRendaFixa.data_posicao, PosicaoRendaFixa.nome_do_papel)
    )
    for d, papel, valor in (await db.execute(stmt)).all():
        v = Decimal(valor or 0)
        bucket = out[d]
        if _is_titulo_publico(papel):
            bucket["titulos_publicos"] += v
        elif _is_dc_estruturada(papel):
            bucket["dc_estruturada"] += v
        elif (papel or "").upper() == "MEZAN":
            bucket["cota_mezanino"] += v
        elif (papel or "").upper() == "SRP":
            bucket["cota_senior"] += v
        else:
            bucket["nao_classificado"] += v
    return out


async def _cota_fundo_breakdown(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    datas: list[date],
) -> dict[date, dict[str, Decimal]]:
    """Le wh_posicao_cota_fundo e separa REAL* (DC) de outros (Fundos DI).

    Retorna {data: {'dc': Decimal, 'fundos_di': Decimal}}.
    """
    out: dict[date, dict[str, Decimal]] = {
        d: {"dc": ZERO, "fundos_di": ZERO} for d in datas
    }
    stmt = (
        select(
            PosicaoCotaFundo.data_posicao,
            PosicaoCotaFundo.ativo_codigo,
            PosicaoCotaFundo.valor_atual,
        )
        .where(PosicaoCotaFundo.tenant_id == tenant_id)
        .where(PosicaoCotaFundo.unidade_administrativa_id == ua_id)
        .where(PosicaoCotaFundo.data_posicao.in_(datas))
    )
    for d, ativo_codigo, valor in (await db.execute(stmt)).all():
        v = Decimal(valor or 0)
        if (ativo_codigo or "").upper().startswith("REAL"):
            out[d]["dc"] += v
        else:
            out[d]["fundos_di"] += v
    return out


async def _outros_ativos_pdd(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, datas: list[date]
) -> dict[date, dict[str, Decimal]]:
    """Le wh_posicao_outros_ativos. PDD vai pra linha PDD; resto pra Outros Ativos."""
    out: dict[date, dict[str, Decimal]] = {
        d: {"pdd": ZERO, "outros": ZERO} for d in datas
    }
    stmt = (
        select(
            PosicaoOutrosAtivos.data_posicao,
            PosicaoOutrosAtivos.codigo,
            PosicaoOutrosAtivos.valor_total,
        )
        .where(PosicaoOutrosAtivos.tenant_id == tenant_id)
        .where(PosicaoOutrosAtivos.unidade_administrativa_id == ua_id)
        .where(PosicaoOutrosAtivos.data_posicao.in_(datas))
    )
    for d, codigo, valor in (await db.execute(stmt)).all():
        v = Decimal(valor or 0)
        if (codigo or "").upper() == "PDD":
            out[d]["pdd"] += v
        else:
            out[d]["outros"] += v
    return out


async def _cpr_by_cosif(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, datas: list[date]
) -> dict[str, dict[date, dict[str, Decimal]]]:
    """Le wh_cpr_movimento e classifica cada item em conta COSIF analitica.

    Retorna estrutura aninhada:
        { cosif: { data: { historico_traduzido: valor } } }

    Para contas de Passivo (4.9.x), valores ja vem ABS (positivo na exibicao).
    Para contas de Ativo (1.8.x, 1.9.x), valores mantem sinal original
    (positivo = cripto a receber/diferimento; negativo = redutor, ex.: baixa).
    """
    out: dict[str, dict[date, dict[str, Decimal]]] = {}
    stmt = (
        select(
            CprMovimento.data_posicao,
            CprMovimento.historico_traduzido,
            CprMovimento.valor,
        )
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao.in_(datas))
    )
    for d, historico, v in (await db.execute(stmt)).all():
        valor = Decimal(v or 0)
        cosif = _classify_cpr_cosif(historico, valor)
        is_passivo = CPR_COSIF_META.get(cosif, ("", "A"))[1] == "P"
        v_display = abs(valor) if is_passivo else valor

        if cosif not in out:
            out[cosif] = {}
        if d not in out[cosif]:
            out[cosif][d] = {}
        key = historico or "(sem histórico)"
        out[cosif][d][key] = Decimal(out[cosif][d].get(key, ZERO) or 0) + v_display
    return out


def _sum_cosif_at(
    table: dict[str, dict[date, dict[str, Decimal]]],
    cosif: str,
    d: date,
) -> Decimal:
    """Total da conta COSIF na data d."""
    return Decimal(sum(
        (Decimal(v or 0) for v in table.get(cosif, {}).get(d, {}).values()),
        start=ZERO,
    ))


async def _conta_corrente_concili(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, datas: list[date]
) -> dict[date, Decimal]:
    """Soma da CC com codigo='CONCILIA' (CREDITOS A CONCILIAR) — entra
    provisoriamente em Outros Ativos (sinal original mantido). TODO mover
    para Passivo 4.9.9.30.90 OUTROS PAGAMENTOS.

    NOTA: filtro por codigo, NAO por descricao. 'SOCOPA-CONCILIAÇÃO' tambem
    contem 'CONCILI' mas eh a CC SINGULARE (codigo='SOCOPA') — ja vai pra
    BANCOS PRIVADOS - CONTA via _sum_bancos_privados.
    """
    out: dict[date, Decimal] = dict.fromkeys(datas, ZERO)
    stmt = (
        select(
            SaldoContaCorrente.data_posicao,
            func.coalesce(func.sum(SaldoContaCorrente.valor_total), ZERO),
        )
        .where(SaldoContaCorrente.tenant_id == tenant_id)
        .where(SaldoContaCorrente.unidade_administrativa_id == ua_id)
        .where(SaldoContaCorrente.data_posicao.in_(datas))
        .where(SaldoContaCorrente.codigo == "CONCILIA")
        .group_by(SaldoContaCorrente.data_posicao)
    )
    for d, v in (await db.execute(stmt)).all():
        out[d] = Decimal(v or 0)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Breakdown helpers — geram sub_rows (1 nivel de detalhamento por linha)
# Cada um devolve list[BalanceRow] com type='line' (subitens reaproveitam
# o mesmo schema, hierarquia distinguida por depth no frontend).
# ─────────────────────────────────────────────────────────────────────────────


def _build_breakdown_rows(
    parent_id: str,
    items_by_data: dict[date, dict[str, Decimal]],
    d_d1: date,
    data_d0: date,
    *,
    abs_value: bool = False,
    sort_by_d0: bool = True,
    label_map: dict[str, str] | None = None,
    keep_zero: bool = False,
) -> list[BalanceRow]:
    """Util: recebe {data: {chave: Decimal}} para D-1 e D0, devolve sub-rows
    BalanceRow (type='line') por chave, ordenadas por |d0| desc.

    label_map: opcional, remapeia chaves cruas (ex.: 'NCPX' → 'A vencer').
    keep_zero: por default filtra sub-rows com d1=d0=delta=0; passe True para
               manter (ex.: VCNC zerado servindo como sinalizacao).
    """
    keys: set[str] = set()
    keys.update(items_by_data.get(d_d1, {}).keys())
    keys.update(items_by_data.get(data_d0, {}).keys())

    rows: list[BalanceRow] = []
    for key in keys:
        d1_val = Decimal(items_by_data.get(d_d1, {}).get(key, ZERO) or 0)
        d0_val = Decimal(items_by_data.get(data_d0, {}).get(key, ZERO) or 0)
        if abs_value:
            d1_val, d0_val = abs(d1_val), abs(d0_val)
        label = label_map.get(key, key) if label_map else key
        rows.append(_row(
            f"{parent_id}.{_safe_id(key)}", "line", label,
            d1=d1_val, d0=d0_val,
        ))

    if sort_by_d0:
        rows.sort(key=lambda r: abs(float(r.d0 or 0)), reverse=True)
    return rows if keep_zero else _filter_nonzero(rows)


def _safe_id(s: str) -> str:
    """Gera id estavel a partir de label livre (ASCII, sem espacos)."""
    return "".join(c if c.isalnum() else "_" for c in (s or "").lower())[:40]


async def _breakdown_bancos_privados(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    d_d1: date,
    data_d0: date,
) -> list[BalanceRow]:
    """SubRows analiticas para BANCOS PRIVADOS - CONTA (1.1.2.80.00).

    Mapeia codigos QiTech -> contas COSIF analiticas:
      wh_saldo_tesouraria         -> 1.1.2.80.00.001 BANCOS CONTA MOVIMENTO
      wh_saldo_conta_corrente
        codigo='BRADESCO'         -> 1.1.2.80.00.002 BANCO BRADESCO S/A
        codigo='SOCOPA'           -> 1.1.2.80.00.007 SINGULARE CORRETORA
        codigo='CONCILIA'         -> NAO entra aqui (vai pra Passivo)
        codigo desconhecido       -> "(nao classificado)" pra defesa
    """
    datas = [d_d1, data_d0]

    # Bucket id -> (cosif, label)
    buckets: dict[str, tuple[str, str]] = {
        "001":   ("1.1.2.80.00.001", "BANCOS CONTA MOVIMENTO"),
        "002":   ("1.1.2.80.00.002", "BANCO BRADESCO S/A"),
        "007":   ("1.1.2.80.00.007", "SINGULARE CORRETORA"),
        "999":   ("",                "Não classificado"),
    }
    values: dict[str, dict[date, Decimal]] = {b: dict.fromkeys(datas, ZERO) for b in buckets}
    # `descricao` da silver por bucket — agregada via set pra evitar duplicacao
    # quando o mesmo bucket recebe varias contas (ex.: 999 nao classificado).
    descricoes_silver: dict[str, set[str]] = {b: set() for b in buckets}

    # 001 ← wh_saldo_tesouraria (todas as classes; soma)
    stmt_tes = (
        select(SaldoTesouraria.data_posicao,
               SaldoTesouraria.descricao,
               func.coalesce(func.sum(SaldoTesouraria.valor), ZERO))
        .where(SaldoTesouraria.tenant_id == tenant_id)
        .where(SaldoTesouraria.unidade_administrativa_id == ua_id)
        .where(SaldoTesouraria.data_posicao.in_(datas))
        .group_by(SaldoTesouraria.data_posicao, SaldoTesouraria.descricao)
    )
    for d, descricao, v in (await db.execute(stmt_tes)).all():
        values["001"][d] += Decimal(v or 0)
        if descricao:
            descricoes_silver["001"].add(descricao)

    # 002 / 007 / 999 ← wh_saldo_conta_corrente (codigo != CONCILIA)
    stmt_cc = (
        select(SaldoContaCorrente.data_posicao,
               SaldoContaCorrente.codigo,
               SaldoContaCorrente.descricao,
               func.coalesce(func.sum(SaldoContaCorrente.valor_total), ZERO))
        .where(SaldoContaCorrente.tenant_id == tenant_id)
        .where(SaldoContaCorrente.unidade_administrativa_id == ua_id)
        .where(SaldoContaCorrente.data_posicao.in_(datas))
        .where(SaldoContaCorrente.codigo != "CONCILIA")
        .group_by(
            SaldoContaCorrente.data_posicao,
            SaldoContaCorrente.codigo,
            SaldoContaCorrente.descricao,
        )
    )
    for d, codigo, descricao, v in (await db.execute(stmt_cc)).all():
        c = (codigo or "").upper()
        if c == "BRADESCO":
            values["002"][d] += Decimal(v or 0)
            if descricao:
                descricoes_silver["002"].add(descricao)
        elif c == "SOCOPA":
            values["007"][d] += Decimal(v or 0)
            if descricao:
                descricoes_silver["007"].add(descricao)
        else:
            # codigo novo / desconhecido — defesa pra nao perder dado.
            values["999"][d] += Decimal(v or 0)
            if descricao:
                descricoes_silver["999"].add(descricao)

    rows: list[BalanceRow] = []
    for bucket_id, (cosif, label) in buckets.items():
        d1_val = values[bucket_id][d_d1]
        d0_val = values[bucket_id][data_d0]
        if d1_val == ZERO and d0_val == ZERO:
            continue
        # Descricao da silver vai pra coluna propria (nao concatena no label)
        descs = sorted(descricoes_silver[bucket_id])
        descricao = " / ".join(descs) if descs else None
        rows.append(_row(
            f"bp.{bucket_id}", "line", label,
            cosif=cosif or None,
            descricao=descricao,
            d1=d1_val, d0=d0_val,
        ))
    return rows


async def _breakdown_compromissada(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, datas: list[date]
) -> dict[date, dict[str, Decimal]]:
    """Breakdown por papel + codigo."""
    out: dict[date, dict[str, Decimal]] = {d: {} for d in datas}
    stmt = (
        select(
            PosicaoCompromissada.data_posicao,
            PosicaoCompromissada.papel,
            PosicaoCompromissada.codigo,
            func.coalesce(func.sum(PosicaoCompromissada.valor_bruto), ZERO),
        )
        .where(PosicaoCompromissada.tenant_id == tenant_id)
        .where(PosicaoCompromissada.unidade_administrativa_id == ua_id)
        .where(PosicaoCompromissada.data_posicao.in_(datas))
        .group_by(
            PosicaoCompromissada.data_posicao,
            PosicaoCompromissada.papel,
            PosicaoCompromissada.codigo,
        )
    )
    for d, papel, codigo, v in (await db.execute(stmt)).all():
        label = f"{papel or '?'} {codigo or ''}".strip()
        out[d][label] = Decimal(v or 0)
    return out


async def _breakdown_renda_fixa_por_papel(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    cliente_id_principal: str,
    datas: list[date],
    papeis_filter: list[str] | None = None,
    papel_starts_with: str | None = None,
) -> dict[date, dict[str, Decimal]]:
    """Breakdown da renda fixa filtrando por papel (TPF, DC estruturada, etc).
    Agrupa por nome_do_papel."""
    out: dict[date, dict[str, Decimal]] = {d: {} for d in datas}
    stmt = (
        select(
            PosicaoRendaFixa.data_posicao,
            PosicaoRendaFixa.nome_do_papel,
            func.coalesce(func.sum(PosicaoRendaFixa.valor_bruto), ZERO),
        )
        .where(PosicaoRendaFixa.tenant_id == tenant_id)
        .where(PosicaoRendaFixa.unidade_administrativa_id == ua_id)
        .where(PosicaoRendaFixa.data_posicao.in_(datas))
        .where(func.upper(PosicaoRendaFixa.carteira_cliente_id) == cliente_id_principal)
        .group_by(PosicaoRendaFixa.data_posicao, PosicaoRendaFixa.nome_do_papel)
    )
    for d, papel, v in (await db.execute(stmt)).all():
        p = (papel or "").upper()
        if papeis_filter and p not in papeis_filter:
            continue
        if papel_starts_with and not p.startswith(papel_starts_with):
            continue
        out[d][papel or "(sem papel)"] = Decimal(v or 0)
    return out


async def _breakdown_renda_fixa_por_emitente(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    cliente_id_principal: str,
    datas: list[date],
    papel: str,
) -> dict[date, dict[str, Decimal]]:
    """Breakdown da renda fixa para um papel especifico (MEZAN/SRP), por emitente."""
    out: dict[date, dict[str, Decimal]] = {d: {} for d in datas}
    stmt = (
        select(
            PosicaoRendaFixa.data_posicao,
            PosicaoRendaFixa.emitente,
            func.coalesce(func.sum(PosicaoRendaFixa.valor_bruto), ZERO),
        )
        .where(PosicaoRendaFixa.tenant_id == tenant_id)
        .where(PosicaoRendaFixa.unidade_administrativa_id == ua_id)
        .where(PosicaoRendaFixa.data_posicao.in_(datas))
        .where(func.upper(PosicaoRendaFixa.carteira_cliente_id) == cliente_id_principal)
        .where(func.upper(PosicaoRendaFixa.nome_do_papel) == papel.upper())
        .group_by(PosicaoRendaFixa.data_posicao, PosicaoRendaFixa.emitente)
    )
    for d, emitente, v in (await db.execute(stmt)).all():
        out[d][emitente or "(sem emitente)"] = Decimal(v or 0)
    return out


async def _breakdown_cota_fundo(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    datas: list[date],
    real_only: bool,
) -> dict[date, dict[str, Decimal]]:
    """Breakdown de wh_posicao_cota_fundo. Se real_only, filtra so REAL* (DC).
    Senao, exclui REAL* (Fundos DI). Agrupa por ativo_nome."""
    out: dict[date, dict[str, Decimal]] = {d: {} for d in datas}
    stmt = (
        select(
            PosicaoCotaFundo.data_posicao,
            PosicaoCotaFundo.ativo_codigo,
            PosicaoCotaFundo.ativo_nome,
            func.coalesce(func.sum(PosicaoCotaFundo.valor_atual), ZERO),
        )
        .where(PosicaoCotaFundo.tenant_id == tenant_id)
        .where(PosicaoCotaFundo.unidade_administrativa_id == ua_id)
        .where(PosicaoCotaFundo.data_posicao.in_(datas))
        .group_by(
            PosicaoCotaFundo.data_posicao,
            PosicaoCotaFundo.ativo_codigo,
            PosicaoCotaFundo.ativo_nome,
        )
    )
    for d, codigo, nome, v in (await db.execute(stmt)).all():
        is_real = (codigo or "").upper().startswith("REAL")
        if real_only and not is_real:
            continue
        if (not real_only) and is_real:
            continue
        # Pra DC (REAL*), label preferido eh o nome do "fundo virtual" (ex.: REALINVEST A VENCER)
        # Pra Fundos DI, label = ativo_nome.
        label = nome or codigo or "(sem nome)"
        out[d][label] = Decimal(v or 0)
    return out


def _classify_cpr_cosif(historico: str, valor: Decimal) -> str:
    """Mapeia item do CPR para conta COSIF analitica baseada em historico_traduzido.

    Retorna 1 das 5 contas:
      ATIVO:
        '1.8.4.30.00'  Devedores - Conta Liquidacoes Pendentes
        '1.9.9.10'     Despesas antecipadas (diferimentos)
      PASSIVO:
        '4.9.1.10'     IOF a Recolher
        '4.9.9.30'     Provisao para pagamentos a efetuar
        '4.9.9.83'     Valores a Pagar Sociedade Administradora

    PRECEDENCIA importa: alguns padroes sao substring uns dos outros.
    Ex.: 'BANCO LIQUIDANTE' contem 'LIQUIDA' — checar 'BANCO LIQ' antes.
    """
    h = (historico or "").upper()

    # 1) Banco Liquidante (despesa adm) — checar ANTES de qualquer pattern de "LIQUID*"
    if "BANCO LIQ" in h:
        return "4.9.9.30"

    # 2) Diferimentos (Ativo - Despesas Antecipadas)
    if "DIFER" in h:
        return "1.9.9.10"

    # 3) IOF / tributos
    if "IOF" in h:
        return "4.9.1.10"

    # 4) Liquidacoes em transito / TED / Baixa / Compensacao / Aquisicao
    #    (Ativo - 1.8.4.30.00). Use 'LIQUIDADO' (não 'LIQUIDA') para evitar
    #    falso match em 'LIQUIDANTE'.
    if any(k in h for k in (
        "LIQUIDADO", "LIQUIDAÇÃO", "LIQUIDACAO",  # snapshots de operações já liquidadas
        "TED",                                     # transferencias em transito
        "BAIXA",                                   # baixas operacionais
        "AQUISIC",                                 # TED para aquisicao de ativos
        "COMPENSAÇÃO", "COMPENSACAO",              # ajuste de compensacao de cotas
        "DEVOLUÇÃO", "DEVOLUCAO",                  # devolucao de pagamento em duplicidade
    )):
        return "1.8.4.30.00"

    # 5) Taxas correntes apropriadas (4.9.9.83)
    if "TAXA" in h and any(k in h for k in ("ADMINISTRA", "CUSTODIA", "CUSTÓDIA", "GESTAO", "GESTÃO")):
        return "4.9.9.83"

    # 6) Despesas administrativas pontuais (4.9.9.30)
    if any(k in h for k in ("AUDITOR", "CONSULTOR", "COBRAN", "SELIC", "ANBIMA", "CVM")):
        return "4.9.9.30"

    # Defaults pelo sinal — conservadores
    return "4.9.9.30" if valor < 0 else "1.8.4.30.00"


# Metadados das contas COSIF derivadas do CPR (label oficial + natureza)
CPR_COSIF_META: dict[str, tuple[str, str]] = {
    # cosif: (label, natureza_atual_no_balanco — 'A'=Ativo, 'P'=Passivo)
    "1.8.4.30.00": ("DEVEDORES - CONTA LIQUIDAÇÕES PENDENTES", "A"),
    "1.9.9.10":    ("DESPESAS ANTECIPADAS",                    "A"),
    "4.9.1.10":    ("IOF A RECOLHER",                          "P"),
    "4.9.9.30":    ("PROVISÃO PARA PAGAMENTOS A EFETUAR",      "P"),
    "4.9.9.83":    ("VALORES A PAGAR À SOCIEDADE ADMINISTRADORA", "P"),
}


# Sub-cosif analiticos para 1.8.4.30.00 DEVEDORES - CONTA LIQUIDAÇÕES PENDENTES
# Cada entrada eh (pattern_uppercase_no_historico, sub_cosif, label_oficial).
# Items que nao matcharem viram sub-row "Não classificado" (sem cosif).
LIQUIDACAO_PENDENTES_SUBCOSIF: list[tuple[str, str, str]] = [
    ("LIQUIDADOS TOTAL",       "1.8.4.30.00.001", "RECEBÍVEIS - TÍTULOS"),
    ("COMPENSAÇÃO",            "1.8.4.30.00.005", "AJUSTE DE COMPENSACAO"),
    ("COMPENSACAO",            "1.8.4.30.00.005", "AJUSTE DE COMPENSACAO"),
    # Reservado pro futuro (se aparecer "COTAS A LIQUIDAR" em historico):
    ("COTAS A LIQUIDAR",       "1.8.4.30.00.008", "COTAS A LIQUIDAR"),
]


def _build_cpr_analytic_subrows(
    parent_id:           str,
    items_by_data:       dict[date, dict[str, Decimal]],
    d_d1:                date,
    data_d0:             date,
    sub_cosif_map:       list[tuple[str, str, str]],
    *,
    keep_zero:           bool = False,
) -> list[BalanceRow]:
    """Mapeia cada item do CPR num sub-cosif analitico do COSIF pai.

    sub_cosif_map: lista [(pattern_upper, sub_cosif, label_oficial), ...].
    Items que nao matcham nenhum pattern entram como sub-rows "Não classificado"
    (sem cosif analitico, label = historico cru).

    Sub-rows com sub_cosif populam a coluna 'descricao' com os historicos de
    origem (defesa-em-profundidade pra auditoria).
    """
    def classify(historico: str) -> tuple[str, str] | None:
        h = (historico or "").upper()
        for pattern, sc, lbl in sub_cosif_map:
            if pattern in h:
                return (sc, lbl)
        return None

    # Agrupar (sub_cosif, label) -> {date: value}; preservar historicos pra descricao
    groups: dict[tuple[str, str], dict[date, Decimal]] = {}
    historicos: dict[tuple[str, str], set[str]] = {}

    for d in (d_d1, data_d0):
        for historico, valor in items_by_data.get(d, {}).items():
            # Não classificado: usa o historico como label proprio, sem cosif.
            key = classify(historico) or ("", historico)
            if key not in groups:
                groups[key] = {d_d1: ZERO, data_d0: ZERO}
                historicos[key] = set()
            groups[key][d] = Decimal(groups[key].get(d, ZERO) or 0) + Decimal(valor or 0)
            historicos[key].add(historico)

    rows: list[BalanceRow] = []
    # Ordem: COSIF analiticos primeiro (.001, .005, .008...), depois nao-classificados.
    sorted_keys = sorted(groups.keys(), key=lambda k: (not k[0], k[0], k[1]))

    for sub_cosif, label in sorted_keys:
        d1_v = groups[(sub_cosif, label)][d_d1]
        d0_v = groups[(sub_cosif, label)][data_d0]
        if not keep_zero and d1_v == ZERO and d0_v == ZERO:
            continue
        # Descricao so quando ha sub_cosif (caso classificado): mostra historicos
        descricao_str = None
        if sub_cosif and historicos[(sub_cosif, label)]:
            descricao_str = " / ".join(sorted(historicos[(sub_cosif, label)]))
        rows.append(_row(
            f"{parent_id}.{_safe_id(sub_cosif or label)}",
            "line",
            label,
            cosif=sub_cosif or None,
            descricao=descricao_str,
            d1=d1_v, d0=d0_v,
        ))
    return rows


async def _breakdown_outros_ativos_residual(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, datas: list[date]
) -> dict[date, dict[str, Decimal]]:
    """Linha 'Outros Ativos' temporaria — apenas CC CONCILI e PosicaoOutrosAtivos
    nao-PDD (residual apos a reclassificacao do CPR em contas COSIF proprias).

    TODO: mover CC CONCILI para Passivo (4.9.9.30.x OUTROS PAGAMENTOS) quando
    decidido com o usuario."""
    out: dict[date, dict[str, Decimal]] = {d: {} for d in datas}

    # CC CONCILI (codigo='CONCILIA')
    stmt_cc = (
        select(
            SaldoContaCorrente.data_posicao,
            func.coalesce(func.sum(SaldoContaCorrente.valor_total), ZERO),
        )
        .where(SaldoContaCorrente.tenant_id == tenant_id)
        .where(SaldoContaCorrente.unidade_administrativa_id == ua_id)
        .where(SaldoContaCorrente.data_posicao.in_(datas))
        .where(SaldoContaCorrente.codigo == "CONCILIA")
        .group_by(SaldoContaCorrente.data_posicao)
    )
    for d, v in (await db.execute(stmt_cc)).all():
        if v and Decimal(v) != ZERO:
            out[d]["CREDITOS A CONCILIAR (mover p/ Passivo)"] = Decimal(v or 0)

    # outros-ativos non-PDD (geralmente vazio para REALINVEST)
    stmt_oa = (
        select(
            PosicaoOutrosAtivos.data_posicao,
            PosicaoOutrosAtivos.descricao,
            PosicaoOutrosAtivos.valor_total,
        )
        .where(PosicaoOutrosAtivos.tenant_id == tenant_id)
        .where(PosicaoOutrosAtivos.unidade_administrativa_id == ua_id)
        .where(PosicaoOutrosAtivos.data_posicao.in_(datas))
        .where(func.upper(PosicaoOutrosAtivos.codigo) != "PDD")
    )
    for d, desc, v in (await db.execute(stmt_oa)).all():
        out[d][desc or "(sem descrição)"] = Decimal(v or 0)

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Service principal
# ─────────────────────────────────────────────────────────────────────────────


async def compute_balanco(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id:     UUID,
    data_d0:   date,
    data_d1:   date | None = None,
) -> BalancoResponse:
    """Monta o balanco diario para D-1 → D0.

    Lanca ValueError se a UA nao for encontrada ou nao pertencer ao tenant.
    """
    # 1. Carregar UA pra pegar nome (usado como filtro POV Sub Jr).
    ua = await db.get(UnidadeAdministrativa, ua_id)
    if ua is None or ua.tenant_id != tenant_id:
        raise ValueError(f"Unidade administrativa {ua_id} nao encontrada para o tenant.")

    d_d1 = data_d1 or _dia_util_anterior(data_d0)
    datas = [d_d1, data_d0]
    cliente_id_principal = (ua.nome or "").upper().strip().split(" ", 1)[0]

    # 2. Aggregates (linha-mae)
    bp        = await _sum_bancos_privados(db, tenant_id, ua_id, datas)
    comp      = await _sum_compromissada(db, tenant_id, ua_id, datas)
    rf        = await _renda_fixa_breakdown(db, tenant_id, ua_id, ua.nome, datas)
    cf        = await _cota_fundo_breakdown(db, tenant_id, ua_id, datas)
    oa        = await _outros_ativos_pdd(db, tenant_id, ua_id, datas)
    cpr_cosif = await _cpr_by_cosif(db, tenant_id, ua_id, datas)

    # 2b. Breakdowns (sub-rows por linha)
    bp_subs = await _breakdown_bancos_privados(db, tenant_id, ua_id, d_d1, data_d0)
    bd_comp = await _breakdown_compromissada(db, tenant_id, ua_id, datas)
    # NOTAS DO TESOURO NACIONAL (1.3.1.10.07): apenas papeis com hifen (NTN-*).
    # 'NTN O' / 'LTNO' SAO compromissadas — nao entram aqui (vao p/ 1.2.1.10.05).
    bd_tp   = await _breakdown_renda_fixa_por_papel(
        db, tenant_id, ua_id, cliente_id_principal, datas, papel_starts_with="NTN-"
    )
    bd_fdi  = await _breakdown_cota_fundo(db, tenant_id, ua_id, datas, real_only=False)
    bd_dc   = await _breakdown_cota_fundo(db, tenant_id, ua_id, datas, real_only=True)
    bd_dce  = await _breakdown_renda_fixa_por_papel(
        db, tenant_id, ua_id, cliente_id_principal, datas, papeis_filter=["NCPX", "VCNC"]
    )
    bd_oa_residual = await _breakdown_outros_ativos_residual(db, tenant_id, ua_id, datas)
    bd_mez  = await _breakdown_renda_fixa_por_emitente(
        db, tenant_id, ua_id, cliente_id_principal, datas, papel="MEZAN"
    )
    bd_sr   = await _breakdown_renda_fixa_por_emitente(
        db, tenant_id, ua_id, cliente_id_principal, datas, papel="SRP"
    )

    # 3. Helpers para pegar valor com fallback ZERO.
    def at(table: dict[date, Decimal], d: date) -> Decimal:
        return Decimal(table.get(d, ZERO) or 0)

    def at_b(table: dict[date, dict[str, Decimal]], d: date, key: str) -> Decimal:
        return Decimal(table.get(d, {}).get(key, ZERO) or 0)

    # 4. ATIVO — montado como subRows de um no-raiz "1 ATIVO" (3 niveis)
    ativo_subrows: list[BalanceRow] = [
        # 1.1.x DISPONIBILIDADES
        _row(
            "bancos_privados", "line", "BANCOS PRIVADOS - CONTA",
            cosif="1.1.2.80.00",
            source="wh_saldo_tesouraria + wh_saldo_conta_corrente (codigo != CONCILIA)",
            d1=at(bp, d_d1), d0=at(bp, data_d0),
            sub_rows=bp_subs,
        ),
        # 1.2.x APLICAÇÕES INTERFINANCEIRAS DE LIQUIDEZ
        _row(
            "compromissada", "line", "LETRAS DO TESOURO NACIONAL",
            cosif="1.2.1.10.05",
            source="wh_posicao_compromissada",
            d1=at(comp, d_d1), d0=at(comp, data_d0),
            sub_rows=_build_breakdown_rows("compromissada", bd_comp, d_d1, data_d0),
        ),
        # 1.3.x TÍTULOS E VALORES MOBILIÁRIOS
        _row(
            "tp", "line", "NOTAS DO TESOURO NACIONAL",
            cosif="1.3.1.10.07",
            source="wh_posicao_renda_fixa · papel LIKE 'NTN-%' (titulos puros)",
            d1=at_b(rf, d_d1, "titulos_publicos"),
            d0=at_b(rf, data_d0, "titulos_publicos"),
            sub_rows=_build_breakdown_rows("tp", bd_tp, d_d1, data_d0),
        ),
        _row(
            "dce", "line", "NOTA COMERCIAL",
            cosif="1.3.1.10.16.001",
            source="wh_posicao_renda_fixa · papel ∈ (NCPX, VCNC)",
            d1=at_b(rf, d_d1, "dc_estruturada"),
            d0=at_b(rf, data_d0, "dc_estruturada"),
            sub_rows=_build_breakdown_rows(
                "dce", bd_dce, d_d1, data_d0,
                label_map={"NCPX": "A vencer", "VCNC": "Vencidos"},
                keep_zero=True,
            ),
        ),
        _row(
            "fdi", "line", "COTAS DE FUNDOS MÚTUOS",
            cosif="1.3.1.15.30",
            source="wh_posicao_cota_fundo · código ∉ REAL*",
            d1=at_b(cf, d_d1, "fundos_di"), d0=at_b(cf, data_d0, "fundos_di"),
            sub_rows=_build_breakdown_rows("fdi", bd_fdi, d_d1, data_d0),
        ),
        # 1.6.x OPERAÇÕES DE CRÉDITO (DC + PDD redutor logo abaixo)
        _row(
            "dc", "line", "Direitos Creditórios",
            cosif="1.6.1.30",
            source="wh_posicao_cota_fundo · código ∈ REAL*",
            d1=at_b(cf, d_d1, "dc"), d0=at_b(cf, data_d0, "dc"),
            sub_rows=_build_breakdown_rows("dc", bd_dc, d_d1, data_d0),
        ),
        _row(
            "pdd", "line", "(-) PDD",
            cosif="1.6.9",
            source="wh_posicao_outros_ativos · código = PDD",
            d1=at_b(oa, d_d1, "pdd"), d0=at_b(oa, data_d0, "pdd"),
        ),
        # 1.8.x OUTROS CRÉDITOS
        _row(
            "liquidacoes", "line", CPR_COSIF_META["1.8.4.30.00"][0],
            cosif="1.8.4.30.00",
            source="wh_cpr_movimento · LIQUIDADOS / TED / Baixa / Compensação",
            d1=_sum_cosif_at(cpr_cosif, "1.8.4.30.00", d_d1),
            d0=_sum_cosif_at(cpr_cosif, "1.8.4.30.00", data_d0),
            sub_rows=_build_cpr_analytic_subrows(
                "liq", cpr_cosif.get("1.8.4.30.00", {}), d_d1, data_d0,
                sub_cosif_map=LIQUIDACAO_PENDENTES_SUBCOSIF,
            ),
        ),
        # 1.9.x OUTROS VALORES E BENS
        _row(
            "desp_antecip", "line", CPR_COSIF_META["1.9.9.10"][0],
            cosif="1.9.9.10",
            source="wh_cpr_movimento · Diferimentos",
            d1=_sum_cosif_at(cpr_cosif, "1.9.9.10", d_d1),
            d0=_sum_cosif_at(cpr_cosif, "1.9.9.10", data_d0),
            sub_rows=_build_breakdown_rows("da", cpr_cosif.get("1.9.9.10", {}), d_d1, data_d0),
        ),
        # Outros Ativos residual (CC CONCILI provisorio — futuramente vai pra Passivo)
        _row(
            "oa_residual", "line", "Outros Ativos",
            cosif="1.8 / 1.9",
            source="wh_saldo_conta_corrente (codigo=CONCILIA) + wh_posicao_outros_ativos (≠ PDD)",
            d1=Decimal(sum((Decimal(v or 0) for v in bd_oa_residual.get(d_d1, {}).values()), start=ZERO)),
            d0=Decimal(sum((Decimal(v or 0) for v in bd_oa_residual.get(data_d0, {}).values()), start=ZERO)),
            sub_rows=_build_breakdown_rows("oa", bd_oa_residual, d_d1, data_d0),
        ),
    ]
    sub_ativo_d1 = sum((r.d1 or ZERO for r in ativo_subrows), start=ZERO)
    sub_ativo_d0 = sum((r.d0 or ZERO for r in ativo_subrows), start=ZERO)
    ativo_root = _row(
        "ativo", "line", "ATIVO",
        cosif="1",
        d1=sub_ativo_d1, d0=sub_ativo_d0,
        sub_rows=ativo_subrows,
    )

    # 5. PASSIVO CONTÁBIL — montado como subRows do no-raiz "4.9 PASSIVO CONTÁBIL"
    passivo_subrows: list[BalanceRow] = [
        _row(
            "iof", "line", CPR_COSIF_META["4.9.1.10"][0],
            cosif="4.9.1.10",
            source="wh_cpr_movimento · IOF",
            d1=_sum_cosif_at(cpr_cosif, "4.9.1.10", d_d1),
            d0=_sum_cosif_at(cpr_cosif, "4.9.1.10", data_d0),
            sub_rows=_build_breakdown_rows("iof", cpr_cosif.get("4.9.1.10", {}), d_d1, data_d0),
        ),
        _row(
            "prov_pgto", "line", CPR_COSIF_META["4.9.9.30"][0],
            cosif="4.9.9.30",
            source="wh_cpr_movimento · Auditoria/Consultoria/Cobranca/etc.",
            d1=_sum_cosif_at(cpr_cosif, "4.9.9.30", d_d1),
            d0=_sum_cosif_at(cpr_cosif, "4.9.9.30", data_d0),
            sub_rows=_build_breakdown_rows("pp", cpr_cosif.get("4.9.9.30", {}), d_d1, data_d0),
        ),
        _row(
            "val_adm", "line", CPR_COSIF_META["4.9.9.83"][0],
            cosif="4.9.9.83",
            source="wh_cpr_movimento · Taxa Adm/Custodia/Gestao apropriada",
            d1=_sum_cosif_at(cpr_cosif, "4.9.9.83", d_d1),
            d0=_sum_cosif_at(cpr_cosif, "4.9.9.83", data_d0),
            sub_rows=_build_breakdown_rows("va", cpr_cosif.get("4.9.9.83", {}), d_d1, data_d0),
        ),
    ]
    sub_passivo_d1 = sum((r.d1 or ZERO for r in passivo_subrows), start=ZERO)
    sub_passivo_d0 = sum((r.d0 or ZERO for r in passivo_subrows), start=ZERO)
    passivo_root = _row(
        "passivo-contabil", "line", "PASSIVO CONTÁBIL",
        cosif="4.9",
        d1=sub_passivo_d1, d0=sub_passivo_d0,
        sub_rows=passivo_subrows,
    )

    # 6. PL TOTAL intermediario
    pl_total_d1 = sub_ativo_d1 - sub_passivo_d1
    pl_total_d0 = sub_ativo_d0 - sub_passivo_d0
    pl_total_row = _row(
        "pl-total", "total", "= PL TOTAL",
        d1=pl_total_d1, d0=pl_total_d0,
    )

    # 7. EQUITY DE OUTRAS CLASSES — montado como subRows do no-raiz "6.1.1 EQUITY"
    equity_subrows: list[BalanceRow] = [
        _row(
            "mez", "line", "Cota Mezanino",
            cosif="6.1.1.x",
            source="wh_posicao_renda_fixa · papel = MEZAN",
            d1=abs(at_b(rf, d_d1, "cota_mezanino")),
            d0=abs(at_b(rf, data_d0, "cota_mezanino")),
            sub_rows=_build_breakdown_rows("mez", bd_mez, d_d1, data_d0, abs_value=True),
        ),
        _row(
            "sr", "line", "Cota Senior",
            cosif="6.1.1.x",
            source="wh_posicao_renda_fixa · papel = SRP",
            d1=abs(at_b(rf, d_d1, "cota_senior")),
            d0=abs(at_b(rf, data_d0, "cota_senior")),
            sub_rows=_build_breakdown_rows("sr", bd_sr, d_d1, data_d0, abs_value=True),
        ),
    ]
    sub_equity_d1 = sum((r.d1 or ZERO for r in equity_subrows), start=ZERO)
    sub_equity_d0 = sum((r.d0 or ZERO for r in equity_subrows), start=ZERO)
    equity_root = _row(
        "equity", "line", "EQUITY DE OUTRAS CLASSES",
        cosif="6.1.1",
        d1=sub_equity_d1, d0=sub_equity_d0,
        sub_rows=equity_subrows,
    )

    # 8. Cota Subordinada residual
    cota_sub_row = _row(
        "total", "total", "= COTA SUBORDINADA",
        d1=pl_total_d1 - sub_equity_d1,
        d0=pl_total_d0 - sub_equity_d0,
    )

    return BalancoResponse(
        fundo_id      = str(ua_id),
        fundo_nome    = ua.nome,
        data          = data_d0,
        data_anterior = d_d1,
        rows          = [ativo_root, passivo_root, pl_total_row, equity_root, cota_sub_row],
    )
