"""ETL do catalogo de receitas operacionais caixa-fiel (PR 2: familias mora).

Materializa `wh_receita_operacional` a partir das fontes nativas Bitfin que
refletem liquidacao financeira REAL, dirigido pelo catalogo
`wh_bitfin_receita_stream` (global + override por tenant):

    mora_liquidacao  -> Titulo (caixa = ValorDoPagamento - ValorLiquido;
                        split juros x multa PROPORCIONAL aos teoricos do
                        ProcedimentoDeCobranca — parametro, nunca valor)
    grafica          -> ContaCorrenteLancamento (todo stream lancamento-grain
                        do catalogo: prorrogacao 028/151, cartorio 024,
                        acerto 025, tarifas, repasses, financeira 031 com
                        filtro de descricao)
    recompra         -> RecompraItem/Recompra Efetivada=1 (juros/multa/
                        desagio por titulo)

NUNCA le DemonstrativoDeResultado (mora teorica — decisao 2026-06-10).

Idempotencia: upsert por (tenant_id, source_id); source_id sintetico por
stream + id-origem + natureza. Re-rodar nao duplica.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig
from app.modules.integracoes.adapters.erp.bitfin.connection import fetch_rows
from app.modules.integracoes.adapters.erp.bitfin.queries import bitfin
from app.warehouse.bitfin_receita_stream import WhBitfinReceitaStream
from app.warehouse.receita_operacional import ReceitaOperacional

ZERO = Decimal("0")
_CENT = Decimal("0.01")
EPOCH = date(1900, 1, 1)

# ComplementoInterno dos lancamentos por-titulo: 'DM=104331' (sigla=TituloId).
_RE_COMPLEMENTO_TITULO = re.compile(r"=\s*(\d+)\s*$")


def _q2(v: Decimal) -> Decimal:
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


def _competencia(d: date) -> date:
    return date(d.year, d.month, 1)


async def load_receita_streams(
    db, tenant_id: UUID
) -> dict[str, WhBitfinReceitaStream]:
    """Streams ativos: globais primeiro, override do tenant vence."""
    stmt = (
        select(WhBitfinReceitaStream)
        .where(
            WhBitfinReceitaStream.valid_until.is_(None),
            or_(
                WhBitfinReceitaStream.tenant_id == tenant_id,
                WhBitfinReceitaStream.tenant_id.is_(None),
            ),
        )
        .order_by(WhBitfinReceitaStream.tenant_id.is_not(None))
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {r.stream_key: r for r in rows}


def split_mora_liquidacao(
    *,
    total: Decimal,
    valor_liquido: Decimal,
    pct_juros: Decimal | None,
    pct_multa: Decimal | None,
    dias_atraso: int,
) -> tuple[Decimal, Decimal]:
    """Split (juros, multa) do caixa de mora, proporcional aos TEORICOS.

    Teoricos (mesma formula da proc DemonstrativoDeResultados / acruo):
        juros_teor = liquido x pct_juros/100/30 x dias (venc ORIGINAL)
        multa_teor = liquido x pct_multa/100

    O TOTAL e sempre o caixa (pgto - liquido); os teoricos so dao a
    PROPORCAO. Sem percentuais (titulo sem ProcedimentoDeCobranca) ou
    teoricos zerados -> 100% juros. Invariante: juros + multa == total.
    """
    if total <= ZERO:
        return ZERO, ZERO
    pj = pct_juros or ZERO
    pm = pct_multa or ZERO
    dias = max(dias_atraso, 0)
    juros_teor = valor_liquido * pj / Decimal(100) / Decimal(30) * Decimal(dias)
    multa_teor = valor_liquido * pm / Decimal(100)
    base = juros_teor + multa_teor
    if base <= ZERO:
        return _q2(total), ZERO
    juros = _q2(total * juros_teor / base)
    return juros, _q2(total - juros)


def _base_row(
    *,
    tenant_id: UUID,
    stream: WhBitfinReceitaStream,
    data_evento: date,
    valor: Decimal,
    source_id: str,
    src: dict[str, Any],
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "data": data_evento,
        "competencia": _competencia(data_evento),
        "stream_key": stream.stream_key,
        "familia": stream.familia,
        "natureza": stream.natureza,
        "valor": _q2(valor),
        "titulo_id": src.get("titulo_id"),
        "operacao_id": src.get("operacao_id"),
        "recompra_id": src.get("recompra_id"),
        "lancamento_id": src.get("lancamento_id"),
        "documento": src.get("documento"),
        "unidade_administrativa_id": src.get("unidade_administrativa_id"),
        "produto_id": src.get("produto_id"),
        "cedente_entidade_id": src.get("cedente_entidade_id"),
        "cedente_nome": src.get("cedente_nome"),
        "cedente_documento": src.get("cedente_documento"),
        "sacado_nome": src.get("sacado_nome"),
        "sacado_documento": src.get("sacado_documento"),
        "_source_id": source_id,
        "_source_updated_at": src.get("data_evento"),
    }


# ---- Sync: mora na liquidacao (Titulo) -------------------------------------


async def sync_receita_mora_liquidacao(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Titulo pago com atraso acima do liquido -> streams mora_liquidacao_*."""
    async with AsyncSessionLocal() as db:
        streams = await load_receita_streams(db, tenant_id)
    s_juros = streams.get("mora_liquidacao_juros")
    s_multa = streams.get("mora_liquidacao_multa")
    if s_juros is None and s_multa is None:
        return {"table": "wh_receita_operacional", "stream": "mora_liquidacao",
                "rows": 0, "skipped": "streams inativos"}

    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin,
        bitfin.SELECT_RECEITA_MORA_TITULO, (cutoff,),
    )

    mapped: list[dict] = []
    for r in rows:
        total = Decimal(str(r["valor_do_pagamento"])) - Decimal(str(r["valor_liquido"]))
        juros, multa = split_mora_liquidacao(
            total=total,
            valor_liquido=Decimal(str(r["valor_liquido"])),
            pct_juros=(None if r["pct_juros"] is None else Decimal(str(r["pct_juros"]))),
            pct_multa=(None if r["pct_multa"] is None else Decimal(str(r["pct_multa"]))),
            dias_atraso=int(r["dias_atraso"] or 0),
        )
        data_evento = r["data_evento"]
        if s_juros is not None and juros > ZERO:
            mapped.append(_base_row(
                tenant_id=tenant_id, stream=s_juros, data_evento=data_evento,
                valor=juros, source_id=f"titulo:{r['titulo_id']}:juros", src=r,
            ))
        if s_multa is not None and multa > ZERO:
            mapped.append(_base_row(
                tenant_id=tenant_id, stream=s_multa, data_evento=data_evento,
                valor=multa, source_id=f"titulo:{r['titulo_id']}:multa", src=r,
            ))

    count = await _upsert_receitas(tenant_id, mapped)
    return {"table": "wh_receita_operacional", "stream": "mora_liquidacao",
            "rows": count}


# ---- Sync: streams de conta grafica (lancamento-grain) ---------------------


async def sync_receita_grafica(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """Todo stream lancamento-grain do catalogo (mora de prorrogacao/cartorio/
    acerto + tarifas + repasses + financeira) numa unica passada.

    O catalogo dirige: codigos vem do `criterio.codigos` de cada stream;
    `criterio.descricao_eq` desambigua codigos bipolares (031: so 'Correção
    Diária'; o lado 'Rentabilidade de Debênture' e credito e ja cai no filtro
    Valor < 0, mas o guard por descricao fica como cinto de seguranca).
    Lancamento cujo codigo casa com stream mas a descricao NAO casa o filtro
    -> descartado (nao e receita conhecida).
    """
    async with AsyncSessionLocal() as db:
        streams = await load_receita_streams(db, tenant_id)

    lanc_streams = [
        s for s in streams.values()
        if s.fonte_tabela == "ContaCorrenteLancamento" and s.grao == "lancamento"
    ]
    if not lanc_streams:
        return {"table": "wh_receita_operacional", "stream": "grafica",
                "rows": 0, "skipped": "streams inativos"}

    # codigo -> [streams] (mais de um stream pode observar o mesmo codigo —
    # resolucao por descricao_eq; sem filtro = catch-all do codigo).
    por_codigo: dict[str, list[WhBitfinReceitaStream]] = {}
    for s in lanc_streams:
        for cod in s.criterio.get("codigos", []):
            por_codigo.setdefault(cod, []).append(s)

    codes = sorted(por_codigo)
    placeholders = ", ".join("?" for _ in codes)
    sql = bitfin.SELECT_RECEITA_GRAFICA_TEMPLATE.format(codes=placeholders)
    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin, sql, (*codes, cutoff),
    )

    mapped: list[dict] = []
    descartados = 0
    for r in rows:
        candidatos = por_codigo.get(r["codigo"], [])
        stream = None
        for s in candidatos:
            desc_eq = s.criterio.get("descricao_eq")
            if desc_eq is None or (r["descricao"] or "").strip() == desc_eq:
                stream = s
                break
        if stream is None:
            descartados += 1
            continue
        # Receita = debito ao cliente (Valor < 0) -> magnitude.
        valor = -Decimal(str(r["valor"]))
        if valor <= ZERO:
            continue
        src = dict(r)
        m = _RE_COMPLEMENTO_TITULO.search(r.get("complemento_interno") or "")
        if m:
            src["titulo_id"] = int(m.group(1))
        # Descricao do lancamento ('Referente ao Titulo 725749/1') vira
        # documento quando da pra extrair o numero.
        desc = r.get("descricao") or ""
        if desc.lower().startswith("referente ao t"):
            src["documento"] = desc.split()[-1][:40]
        mapped.append(_base_row(
            tenant_id=tenant_id, stream=stream, data_evento=r["data_evento"],
            valor=valor, source_id=f"lanc:{r['lancamento_id']}:{stream.stream_key}",
            src=src,
        ))

    count = await _upsert_receitas(tenant_id, mapped)
    return {"table": "wh_receita_operacional", "stream": "grafica",
            "rows": count, "descartados_filtro_descricao": descartados}


# ---- Sync: recompra (RecompraItem, por titulo) ------------------------------


async def sync_receita_recompra(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """RecompraItem (Efetivada=1) -> streams recompra_juros/multa/desagio."""
    async with AsyncSessionLocal() as db:
        streams = await load_receita_streams(db, tenant_id)

    campos = [
        ("recompra_juros", "valor_de_juros"),
        ("recompra_multa", "valor_de_multa"),
        ("recompra_desagio", "valor_de_desagio"),
    ]
    ativos = [(streams[k], campo) for k, campo in campos if k in streams]
    if not ativos:
        return {"table": "wh_receita_operacional", "stream": "recompra",
                "rows": 0, "skipped": "streams inativos"}

    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin,
        bitfin.SELECT_RECEITA_RECOMPRA, (cutoff,),
    )

    mapped: list[dict] = []
    for r in rows:
        for stream, campo in ativos:
            valor = Decimal(str(r[campo] or 0))
            if valor <= ZERO:
                continue
            mapped.append(_base_row(
                tenant_id=tenant_id, stream=stream, data_evento=r["data_evento"],
                valor=valor,
                source_id=(
                    f"recompra:{r['recompra_id']}:{r['titulo_id']}:{stream.natureza}"
                ),
                src=r,
            ))

    count = await _upsert_receitas(tenant_id, mapped)
    return {"table": "wh_receita_operacional", "stream": "recompra",
            "rows": count}


# ---- Sync: rentabilidade de operacao (retido na fonte) ----------------------


def _match_stream_operacao(
    streams: list[WhBitfinReceitaStream], descricao: str
) -> WhBitfinReceitaStream | None:
    """Resolve stream por descricao: `descricao_eq` exato vence; o stream
    catch-all (`descricao_not_in`) pega o resto que nao esta na lista."""
    for s in streams:
        if s.criterio.get("descricao_eq") == descricao:
            return s
    for s in streams:
        excl = s.criterio.get("descricao_not_in")
        if excl is not None and descricao not in excl:
            return s
    return None


async def sync_receita_operacao(
    tenant_id: UUID, config: BitfinConfig, since: date | None = None
) -> dict[str, Any]:
    """OperacaoRentabilidade (efetivadas, Origem != recompra/homologacao) ->
    streams desagio_operacao / tarifa_operacao / ad_valorem.

    Receita RETIDA do liquido na efetivacao = caixa por construcao.
    Cross-check canonico: Σ desagio_operacao do mes == Σ
    wh_operacao.total_de_juros das efetivadas do mes.
    """
    async with AsyncSessionLocal() as db:
        streams = await load_receita_streams(db, tenant_id)

    op_streams = [
        s for s in streams.values()
        if s.fonte_tabela == "OperacaoRentabilidade" and s.grao == "operacao"
    ]
    if not op_streams:
        return {"table": "wh_receita_operacional", "stream": "operacao",
                "rows": 0, "skipped": "streams inativos"}

    cutoff = since or EPOCH
    rows = await asyncio.to_thread(
        fetch_rows, config, config.database_bitfin,
        bitfin.SELECT_RECEITA_OPERACAO_RENT, (cutoff,),
    )

    mapped: list[dict] = []
    sem_stream = 0
    for r in rows:
        descricao = (r["rentabilidade_descricao"] or "").strip()
        stream = _match_stream_operacao(op_streams, descricao)
        if stream is None:
            sem_stream += 1
            continue
        valor = Decimal(str(r["aplicado"]))
        if valor <= ZERO:
            continue
        src = dict(r)
        src["documento"] = descricao[:40]  # qual tarifa/linha da rentabilidade
        mapped.append(_base_row(
            tenant_id=tenant_id, stream=stream, data_evento=r["data_evento"],
            valor=valor,
            source_id=f"oprent:{r['operacao_id']}:{descricao}",
            src=src,
        ))

    count = await _upsert_receitas(tenant_id, mapped)
    return {"table": "wh_receita_operacional", "stream": "operacao",
            "rows": count, "sem_stream": sem_stream}


# ---- Upsert ------------------------------------------------------------------


async def _upsert_receitas(tenant_id: UUID, mapped: list[dict]) -> int:
    """Adiciona proveniencia e faz o upsert idempotente no fato."""
    # Import tardio: evita ciclo etl.py <-> receitas.py (etl importa as syncs
    # daqui para o SYNC_PIPELINE; aqui so precisamos dos helpers).
    from app.modules.integracoes.adapters.erp.bitfin.etl import (
        _bulk_upsert,
        _provenance,
    )

    if not mapped:
        return 0
    rows = []
    for m in mapped:
        source_id = m.pop("_source_id")
        source_updated_at = m.pop("_source_updated_at")
        # Coluna e timestamptz; data de evento (date) vira meia-noite UTC.
        if isinstance(source_updated_at, date) and not isinstance(
            source_updated_at, datetime
        ):
            source_updated_at = datetime(
                source_updated_at.year,
                source_updated_at.month,
                source_updated_at.day,
                tzinfo=UTC,
            )
        # Hash da ORIGEM de negocio: exclui tenant_id (UUID asyncpg nao e
        # JSON-serializavel no sha256_of_row e nao e payload da fonte).
        hash_payload = {k: v for k, v in m.items() if k != "tenant_id"}
        rows.append(
            {**m, **_provenance(source_id, hash_payload, source_updated_at)}
        )
    async with AsyncSessionLocal() as db:
        return await _bulk_upsert(
            db, ReceitaOperacional, rows, ["tenant_id", "source_id"]
        )
