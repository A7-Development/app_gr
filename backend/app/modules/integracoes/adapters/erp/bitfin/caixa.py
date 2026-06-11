"""Engine do METODO CAIXA: desagio do titulo apropriado na SAIDA.

Deriva `wh_receita_caixa` 100% de silver. Regra (Ricardo 2026-06-12):
todo o carrego de desagio + tarifas diretas/rateadas do titulo apropria
QUANDO O TITULO E LIQUIDADO — inclusive recompra (cobrada pelo VN cheio +
encargos; "em dinheiro ou com outro titulo nao muda a logica"). Titulo em
aberto/vencido sem pagar: nada.

Reusa `componentes_titulo` do acruo (cap no desagio observavel) e a mesma
semantica de vidas para titulo RE-OPERADO: a vida i sai na efetivacao da
vida i+1 (evento 'reoperacao').
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType
from app.modules.integracoes.adapters.erp.bitfin.acruo import (
    _as_date,
    componentes_titulo,
)
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.warehouse.operacao import Operacao, OperacaoItem
from app.warehouse.receita_caixa import (
    EVENTO_CAIXA_BAIXA,
    EVENTO_CAIXA_LIQUIDACAO,
    EVENTO_CAIXA_RECOMPRA,
    EVENTO_CAIXA_REOPERACAO,
    ReceitaCaixa,
)
from app.warehouse.titulo import Titulo

ZERO = Decimal("0")

_EVENTO_POR_SITUACAO = {
    1: EVENTO_CAIXA_LIQUIDACAO,
    2: EVENTO_CAIXA_BAIXA,
    5: EVENTO_CAIXA_RECOMPRA,
}


async def sync_receita_caixa(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Reconstroi `wh_receita_caixa` a partir do silver.

    `since=None` -> rebuild full; com `since`, reprocessa titulos com saida
    na janela (delete+insert por titulo, idempotente).
    """
    async with AsyncSessionLocal() as db:
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
            .order_by(
                OperacaoItem.titulo_id,
                Operacao.data_de_efetivacao,
                OperacaoItem.operacao_id,
            )
        )
        if since is not None:
            stmt = stmt.where(Titulo.data_da_situacao >= since)
        rows = (await db.execute(stmt)).all()

        if since is None:
            await db.execute(
                delete(ReceitaCaixa).where(ReceitaCaixa.tenant_id == tenant_id)
            )
        else:
            titulo_ids = [r.titulo_id for r in rows]
            if titulo_ids:
                await db.execute(
                    delete(ReceitaCaixa).where(
                        ReceitaCaixa.tenant_id == tenant_id,
                        ReceitaCaixa.titulo_id.in_(titulo_ids),
                    )
                )
        await db.commit()

    from app.modules.integracoes.adapters.erp.bitfin.etl import (
        _bulk_upsert,
        _provenance,
    )

    # Vidas de titulo re-operado: (titulo, operacao_i) -> efetivacao da vida
    # seguinte (= data de saida da vida i, evento reoperacao).
    proximas: dict[tuple[int, int], date] = {}
    anterior = None
    for r in rows:
        if anterior is not None and anterior.titulo_id == r.titulo_id:
            ef = _as_date(r.data_de_efetivacao)
            if ef is not None:
                proximas[(anterior.titulo_id, anterior.operacao_id)] = ef
        anterior = r

    out: list[dict] = []
    titulos = 0
    em_aberto = 0
    for r in rows:
        comp = componentes_titulo(
            pv=Decimal(str(r.valor_presente)),
            face=Decimal(str(r.face)),
            juros=Decimal(str(r.valor_de_juros or 0)),
            adval=Decimal(str(r.valor_do_ad_valorem or 0)),
            iof=Decimal(str(r.valor_do_iof or 0)),
        )
        if comp is None:
            continue
        total, juros, adval, tarifas = comp
        if total <= ZERO:
            continue

        corte = proximas.get((r.titulo_id, r.operacao_id))
        if corte is not None:
            data_saida, evento = corte, EVENTO_CAIXA_REOPERACAO
        elif r.situacao in _EVENTO_POR_SITUACAO:
            data_saida = _as_date(r.data_da_situacao)
            evento = _EVENTO_POR_SITUACAO[r.situacao]
        else:
            em_aberto += 1  # titulo vivo: caixa ainda nao realizou nada
            continue
        if data_saida is None:
            em_aberto += 1
            continue

        titulos += 1
        payload = {
            "tenant_id": tenant_id,
            "data": data_saida,
            "competencia": date(data_saida.year, data_saida.month, 1),
            "evento": evento,
            "titulo_id": r.titulo_id,
            "operacao_id": r.operacao_id,
            "documento": (r.numero or "")[:40] or None,
            "valor_desagio": juros,
            "valor_adval": adval,
            "valor_tarifas": tarifas,
            "valor_total": total,
            "unidade_administrativa_id": r.unidade_administrativa_id,
            "cedente_entidade_id": r.cedente_id,
            "cedente_nome": r.cedente_nome,
            "cedente_documento": r.cedente_documento,
        }
        source_id = f"{r.titulo_id}:{r.operacao_id}"
        hash_payload = {k: v for k, v in payload.items() if k != "tenant_id"}
        prov = _provenance(source_id, hash_payload, None)
        prov["source_type"] = SourceType.DERIVED
        out.append({**payload, **prov})

    count = 0
    if out:
        async with AsyncSessionLocal() as db2:
            count = await _bulk_upsert(
                db2, ReceitaCaixa, out, ["tenant_id", "source_id"]
            )
    return {
        "table": "wh_receita_caixa",
        "rows": count,
        "titulos_apropriados": titulos,
        "titulos_em_aberto": em_aberto,
    }
