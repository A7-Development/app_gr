"""Engine do METODO ACRUO: curva composta diaria por titulo (D+1 DU).

Deriva `wh_receita_acruo_dia` 100% de silver (wh_operacao_item + wh_titulo +
wh_operacao + wh_dim_dia_util) -- zero ida ao MSSQL. Sistematica do fundo,
validada na wh_estoque_recebivel QiTech (incrementos compostos, pula
fds/feriado, D0=0, VP congela na face no vencimento ORIGINAL).

Matematica por titulo (ancora: PV = OperacaoItem.ValorPresente, que ja
carrega o rateio de tarifas da operacao -- QiTech valor_compra == PV):

    n   = qtde de DUs em (efetivacao, vencimento]
    f   = (face/PV)^(1/n)
    VP_d = PV x f^d  ->  cota_d = VP_d - VP_{d-1}
    ultima cota fecha EXATO em face - PV (residuo de arredondamento nela)

Saida antecipada (liquidacao/recompra antes do vencimento): cotas correm
ate a vespera e o RESIDUAL INTEIRO apropria no dia da saida (evento
`acruo_antecipacao`) -- mesma semantica da "apropriacao antecipada" do DC
na cota-sub. Titulo vencido sem pagar: curva corre ate o vencimento e para
(desacruo/PDD = fase 2, fora de escopo).

Componentes: proporcao fixa de juros/adval/tarifas no desagio total
(tarifas = residuo face-PV-juros-adval-IOF; IOF excluido = repasse).
Invariante: Σ cotas == desagio_total - IOF por titulo, centavo a centavo.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.warehouse.dim_dia_util import DimDiaUtil
from app.warehouse.operacao import Operacao, OperacaoItem
from app.warehouse.receita_acruo_dia import (
    EVENTO_ACRUO,
    EVENTO_ACRUO_ANTECIPACAO,
    ReceitaAcruoDia,
)
from app.warehouse.titulo import Titulo

ZERO = Decimal("0")
_CENT = Decimal("0.01")

# Situacoes em que o titulo SAIU da carteira (liquidado/recomprado/baixado
# por recompra) -- encerram a curva na data da situacao quando anterior ao
# vencimento. Mapa validado 2026-06-11: 1=liquidado, 2=baixa, 5=recompra.
_SITUACOES_SAIDA = {1, 2, 5}

_FLUSH_EVERY = 40_000


def _q2(v: Decimal) -> Decimal:
    return v.quantize(_CENT)


def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    return v.date() if isinstance(v, datetime) else v


def curva_cotas(
    *, pv: Decimal, face: Decimal, n_dus: int
) -> list[Decimal]:
    """Cotas diarias da curva composta PV -> face em n_dus dias uteis.

    Ultima cota fecha EXATO o desagio total (residuo de arredondamento
    nela). n_dus <= 1 -> cota unica com o desagio inteiro.
    """
    total = _q2(face - pv)
    if total <= ZERO:
        return []
    if n_dus <= 1:
        return [total]
    fator = float(face / pv) ** (1.0 / n_dus)
    cotas: list[Decimal] = []
    vp_ant = pv
    acumulado = ZERO
    vp_f = float(pv)
    for _ in range(n_dus - 1):
        vp_f *= fator
        vp = _q2(Decimal(repr(vp_f)))
        cotas.append(_q2(vp - vp_ant))
        acumulado += cotas[-1]
        vp_ant = vp
    cotas.append(_q2(total - acumulado))  # fecha exato na face
    return cotas


def componentes_titulo(
    *,
    pv: Decimal,
    face: Decimal,
    juros: Decimal,
    adval: Decimal,
    iof: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
    """(total_apropriavel, juros, adval, tarifas) do titulo, ou None.

    total_apropriavel = face - PV - IOF (IOF e repasse, fora da receita).
    tarifas = residuo. Residuo negativo (PV maior que a soma das partes,
    raro/arredondamento da fonte) e absorvido em tarifas >= 0 reduzindo o
    total -- nunca inventa componente.
    """
    desagio_total = _q2(face - pv)
    if desagio_total <= ZERO:
        return None
    tarifas = _q2(desagio_total - juros - adval - iof)
    if tarifas < ZERO:
        tarifas = ZERO
    total = _q2(juros + adval + tarifas)
    return total, _q2(juros), _q2(adval), tarifas


def _abre_componentes(
    cota: Decimal, total: Decimal, juros: Decimal, adval: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """Abre uma cota nas proporcoes (juros, adval, tarifas) do titulo."""
    if total <= ZERO:
        return ZERO, ZERO, ZERO
    c_juros = _q2(cota * juros / total)
    c_adval = _q2(cota * adval / total)
    return c_juros, c_adval, _q2(cota - c_juros - c_adval)


async def sync_receita_acruo(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Reconstroi `wh_receita_acruo_dia` a partir do silver.

    `since=None` -> rebuild full. Com `since`, reprocessa apenas titulos
    cuja curva toca a janela (vencimento >= since ou saida >= since) --
    delete+insert por titulo, idempotente.
    """
    async with AsyncSessionLocal() as db:
        # Calendario de DUs do tenant (lista ordenada p/ bisect).
        dus_rows = (
            await db.execute(
                select(DimDiaUtil.data)
                .where(
                    DimDiaUtil.tenant_id == tenant_id,
                    DimDiaUtil.eh_dia_util.is_(True),
                )
                .order_by(DimDiaUtil.data)
            )
        ).scalars().all()
        dus: list[date] = [_as_date(d) for d in dus_rows]
        if not dus:
            return {"table": "wh_receita_acruo_dia", "rows": 0,
                    "skipped": "wh_dim_dia_util vazio"}

        stmt = (
            select(
                OperacaoItem.titulo_id,
                OperacaoItem.operacao_id,
                OperacaoItem.valor_presente,
                OperacaoItem.valor_de_juros,
                OperacaoItem.valor_do_ad_valorem,
                OperacaoItem.valor_do_iof,
                Titulo.valor.label("face"),
                Titulo.numero,
                Titulo.data_de_vencimento,
                Titulo.data_da_situacao,
                Titulo.situacao,
                Titulo.unidade_administrativa_id,
                Operacao.data_de_efetivacao,
                Operacao.cedente_id,
                Operacao.cedente_nome,
                Operacao.cedente_documento,
            )
            .join(
                Titulo,
                (Titulo.tenant_id == OperacaoItem.tenant_id)
                & (Titulo.titulo_id == OperacaoItem.titulo_id),
            )
            .join(
                Operacao,
                (Operacao.tenant_id == OperacaoItem.tenant_id)
                & (Operacao.operacao_id == OperacaoItem.operacao_id),
            )
            .where(
                OperacaoItem.tenant_id == tenant_id,
                Operacao.efetivada.is_(True),
                Operacao.origem.notin_([2, 4]),
                Operacao.data_de_efetivacao.isnot(None),
                OperacaoItem.valor_presente > 0,
                Titulo.valor > OperacaoItem.valor_presente,
            )
        )
        if since is not None:
            stmt = stmt.where(
                (Titulo.data_de_vencimento >= since)
                | (Titulo.data_da_situacao >= since)
            )
        rows = (await db.execute(stmt)).all()

        # Rebuild idempotente do conjunto reprocessado.
        if since is None:
            await db.execute(
                delete(ReceitaAcruoDia).where(ReceitaAcruoDia.tenant_id == tenant_id)
            )
        else:
            titulo_ids = [r.titulo_id for r in rows]
            if titulo_ids:
                await db.execute(
                    delete(ReceitaAcruoDia).where(
                        ReceitaAcruoDia.tenant_id == tenant_id,
                        ReceitaAcruoDia.titulo_id.in_(titulo_ids),
                    )
                )
        await db.commit()

    # Import tardio (helpers do etl sem ciclo de modulo).
    from app.core.enums import SourceType
    from app.modules.integracoes.adapters.erp.bitfin.etl import (
        _bulk_upsert,
        _provenance,
    )

    out: list[dict] = []
    total_rows = 0
    titulos = 0
    sem_calendario = 0

    async def _flush() -> int:
        nonlocal out
        if not out:
            return 0
        async with AsyncSessionLocal() as db2:
            n = await _bulk_upsert(
                db2, ReceitaAcruoDia, out, ["tenant_id", "source_id"]
            )
        out = []
        return n

    for r in rows:
        pv = Decimal(str(r.valor_presente))
        face = Decimal(str(r.face))
        comp = componentes_titulo(
            pv=pv, face=face,
            juros=Decimal(str(r.valor_de_juros or 0)),
            adval=Decimal(str(r.valor_do_ad_valorem or 0)),
            iof=Decimal(str(r.valor_do_iof or 0)),
        )
        if comp is None:
            continue
        total, juros, adval, _tarifas = comp
        if total <= ZERO:
            continue

        efetivacao = _as_date(r.data_de_efetivacao)
        vencimento = _as_date(r.data_de_vencimento)
        if efetivacao is None or vencimento is None or vencimento < efetivacao:
            continue

        # DUs em (efetivacao, vencimento] -- comeca D+1, validado QiTech.
        i0 = bisect_right(dus, efetivacao)
        i1 = bisect_right(dus, vencimento)
        janela = dus[i0:i1]
        if not janela:
            # Vencimento <= efetivacao em DU (ex.: prazo 0/1 corrido):
            # apropria tudo no primeiro DU >= efetivacao.
            k = bisect_left(dus, efetivacao)
            if k >= len(dus):
                sem_calendario += 1
                continue
            janela = [dus[k]]

        # Saida antecipada encerra a curva no dia da saida.
        data_saida = (
            _as_date(r.data_da_situacao)
            if r.situacao in _SITUACOES_SAIDA
            else None
        )
        antecipado = (
            data_saida is not None and data_saida < janela[-1]
        )

        cotas = curva_cotas(pv=pv, face=face, n_dus=len(janela))
        # Reescala da curva cheia (face-PV) para o total apropriavel
        # (face-PV-IOF): proporcional, fechamento na ultima cota.
        fator_total = total / _q2(face - pv)

        emitidas: list[tuple[date, str, Decimal]] = []
        acumulado = ZERO
        for dia, cota in zip(janela, cotas, strict=True):
            if antecipado and dia >= data_saida:
                break
            valor = _q2(cota * fator_total)
            if valor == ZERO:
                continue
            emitidas.append((dia, EVENTO_ACRUO, valor))
            acumulado += valor
        residual = _q2(total - acumulado)
        if residual != ZERO:
            if antecipado:
                emitidas.append((data_saida, EVENTO_ACRUO_ANTECIPACAO, residual))
            elif emitidas:
                # fechamento de arredondamento na ultima cota normal
                dia, ev, v = emitidas[-1]
                emitidas[-1] = (dia, ev, _q2(v + residual))
            else:
                emitidas.append((janela[0], EVENTO_ACRUO, residual))

        titulos += 1
        for dia, evento, valor in emitidas:
            c_juros, c_adval, c_tarifas = _abre_componentes(
                valor, total, juros, adval
            )
            payload = {
                "tenant_id": tenant_id,
                "data": dia,
                "competencia": date(dia.year, dia.month, 1),
                "evento": evento,
                "titulo_id": r.titulo_id,
                "operacao_id": r.operacao_id,
                "documento": (r.numero or "")[:40] or None,
                "valor_desagio": c_juros,
                "valor_adval": c_adval,
                "valor_tarifas": c_tarifas,
                "valor_total": valor,
                "unidade_administrativa_id": r.unidade_administrativa_id,
                "cedente_entidade_id": r.cedente_id,
                "cedente_nome": r.cedente_nome,
                "cedente_documento": r.cedente_documento,
            }
            source_id = f"{r.titulo_id}:{dia.isoformat()}:{evento}"
            prov = _provenance(source_id, payload, None)
            prov["source_type"] = SourceType.DERIVED
            out.append({**payload, **prov})

        if len(out) >= _FLUSH_EVERY:
            total_rows += await _flush()

    total_rows += await _flush()
    return {
        "table": "wh_receita_acruo_dia",
        "rows": total_rows,
        "titulos": titulos,
        "sem_calendario": sem_calendario,
    }
