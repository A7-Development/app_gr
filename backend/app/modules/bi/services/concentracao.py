"""BI -> L2 Concentracao — service.

Calcula, para a Realinvest:
    financeiro = SUM(valor_presente) por cedente/sacado (wh_estoque_recebivel)
    %PL        = financeiro / PL_total_do_fundo
    PL_total   = SUM(patrimonio das classes) do MEC (wh_mec_evolucao_cotas)

Le APENAS silver (CLAUDE.md §13.2.1). Snapshot na ultima data disponivel +
serie historica diaria (uma window query cobre todas as datas).

So Realinvest por enquanto: a UA e fixa; o CNPJ (fundo_doc) e resolvido da
UA em runtime (fonte unica, sem hardcode de doc). A7 Credit tera logica
propria depois.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bi.schemas.common import Provenance
from app.modules.bi.schemas.concentracao import (
    ConcentracaoData,
    ConcentracaoItem,
    ConcentracaoTabela,
    ConcentracaoUA,
    HistoricoPonto,
)

# Realinvest FIDC — UA fixa (unico fundo suportado por enquanto).
_REALINVEST_UA_ID = UUID("6170ce55-b566-42ba-a3e7-5ea8dde56b64")
_TOP_N = 10
# Janela movel do historico (granularidade diaria, ~13 meses) — o estoque tem
# Janela do historico (filtro). Trailing a partir da data de posicao.
_JANELA_DIAS: dict[str, int] = {
    "6m": 185,
    "12m": 370,
    "24m": 740,
    "tudo": 100_000,
}
# Quantas datas recentes oferecer no filtro Posicao (lista do chip).
_DATAS_LIMIT = 90


async def _resolve_fundo_doc(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID
) -> str | None:
    """UA -> CNPJ digits-only (= fundo_doc do estoque). None se sem CNPJ."""
    row = (
        await db.execute(
            text(
                "SELECT cnpj FROM cadastros_unidade_administrativa "
                "WHERE id = :ua AND tenant_id = :t"
            ).bindparams(ua=ua_id, t=tenant_id)
        )
    ).first()
    return row.cnpj if row else None


async def _uas_do_tenant(
    db: AsyncSession, *, tenant_id: UUID
) -> list[ConcentracaoUA]:
    """Todas as UAs (fundos) do tenant — popula o filtro UA."""
    rows = (
        await db.execute(
            text(
                "SELECT id, nome FROM cadastros_unidade_administrativa "
                "WHERE tenant_id = :t ORDER BY nome"
            ).bindparams(t=tenant_id)
        )
    ).all()
    return [ConcentracaoUA(id=str(r.id), nome=r.nome) for r in rows]


async def _datas_disponiveis(
    db: AsyncSession, *, tenant_id: UUID, fundo_doc: str, limit: int
) -> list[date]:
    """Datas de carteira disponiveis (mais recentes primeiro)."""
    rows = (
        await db.execute(
            text(
                "SELECT DISTINCT data_referencia AS d FROM wh_estoque_recebivel "
                "WHERE tenant_id = :t AND fundo_doc = :f "
                "ORDER BY data_referencia DESC LIMIT :lim"
            ).bindparams(t=tenant_id, f=fundo_doc, lim=limit)
        )
    ).all()
    return [r.d for r in rows]


async def _pl_total(
    db: AsyncSession, *, tenant_id: UUID, ua_id: UUID, data_posicao: date
) -> tuple[float, date | None]:
    """PL total (soma das classes MEC) + a data MEC efetiva usada.

    Tenta a data exata; se nao houver, faz fallback pra ultima posicao MEC
    <= data. Retorna (pl, data_do_pl) — data_do_pl pode diferir de data_posicao.
    """
    row = (
        await db.execute(
            text(
                "SELECT COALESCE(SUM(patrimonio), 0) AS pl "
                "FROM wh_mec_evolucao_cotas "
                "WHERE tenant_id = :t AND unidade_administrativa_id = :ua "
                "  AND data_posicao = :d"
            ).bindparams(t=tenant_id, ua=ua_id, d=data_posicao)
        )
    ).one()
    if row.pl and float(row.pl) > 0:
        return float(row.pl), data_posicao
    # Fallback: ultima posicao MEC <= data (MEC pode nao ter a mesma data exata).
    row2 = (
        await db.execute(
            text(
                "SELECT data_posicao AS d, SUM(patrimonio) AS pl "
                "FROM wh_mec_evolucao_cotas "
                "WHERE tenant_id = :t AND unidade_administrativa_id = :ua "
                "  AND data_posicao <= :d "
                "GROUP BY data_posicao ORDER BY data_posicao DESC LIMIT 1"
            ).bindparams(t=tenant_id, ua=ua_id, d=data_posicao)
        )
    ).first()
    if row2 and row2.pl:
        return float(row2.pl), row2.d
    return 0.0, None


async def _top_tabela(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data_referencia: date,
    chave_col: str,
    nome_col: str,
    pl_total: float,
) -> ConcentracaoTabela:
    """Top-N por valor_presente, com nome + %PL + linha '10 maiores'."""
    rows = (
        await db.execute(
            text(
                f"SELECT {chave_col} AS doc, MAX({nome_col}) AS nome, "
                "  SUM(valor_presente) AS vp "
                "FROM wh_estoque_recebivel "
                "WHERE tenant_id = :t AND fundo_doc = :f "
                "  AND data_referencia = :d "
                f"GROUP BY {chave_col} "
                "ORDER BY vp DESC LIMIT :n"
            ).bindparams(t=tenant_id, f=fundo_doc, d=data_referencia, n=_TOP_N)
        )
    ).all()

    itens: list[ConcentracaoItem] = []
    total = 0.0
    for i, r in enumerate(rows, start=1):
        vp = float(r.vp or 0)
        total += vp
        itens.append(
            ConcentracaoItem(
                rank=i,
                nome=r.nome or r.doc or "—",
                documento=r.doc or "",
                financeiro=vp,
                pct_pl=(vp / pl_total * 100) if pl_total > 0 else 0.0,
            )
        )

    # Carteira inteira (todos os titulos) + nº de chaves distintas, pra
    # derivar a cauda "Outros" = total - top10 (reconcilia §14.6).
    tot = (
        await db.execute(
            text(
                "SELECT COALESCE(SUM(valor_presente), 0) AS vp, "
                f"COUNT(DISTINCT {chave_col}) AS n "
                "FROM wh_estoque_recebivel "
                "WHERE tenant_id = :t AND fundo_doc = :f AND data_referencia = :d"
            ).bindparams(t=tenant_id, f=fundo_doc, d=data_referencia)
        )
    ).one()
    carteira_total = float(tot.vp or 0)
    n_chaves = int(tot.n or 0)
    outros_financeiro = max(carteira_total - total, 0.0)
    outros_qtd = max(n_chaves - len(itens), 0)

    return ConcentracaoTabela(
        itens=itens,
        total_financeiro=total,
        total_pct_pl=(total / pl_total * 100) if pl_total > 0 else 0.0,
        outros_qtd=outros_qtd,
        outros_financeiro=outros_financeiro,
        outros_pct_pl=(outros_financeiro / pl_total * 100) if pl_total > 0 else 0.0,
    )


async def _historico(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    ua_id: UUID,
    chave_col: str,
    since: date,
    ate: date,
) -> list[HistoricoPonto]:
    """Serie diaria: % do maior e % dos 10 maiores sobre o PL, por data.

    Uma window query cobre o intervalo [since, ate]: agrupa por (data, chave),
    ranqueia desc por VP, e soma rn=1 (maior) e rn<=10 (top10). Junta com o PL
    diario do MEC (so datas com PL > 0 entram).
    """
    rows = (
        await db.execute(
            text(
                "WITH per_chave AS ( "
                f"  SELECT data_referencia, {chave_col} AS chave, "
                "         SUM(valor_presente) AS vp, "
                "         ROW_NUMBER() OVER ( "
                f"           PARTITION BY data_referencia "
                "           ORDER BY SUM(valor_presente) DESC) AS rn "
                "  FROM wh_estoque_recebivel "
                "  WHERE tenant_id = :t AND fundo_doc = :f "
                "    AND data_referencia >= :since "
                "    AND data_referencia <= :ate "
                f"  GROUP BY data_referencia, {chave_col} "
                "), "
                "agg AS ( "
                "  SELECT data_referencia AS d, "
                "         SUM(vp) FILTER (WHERE rn = 1) AS maior, "
                "         SUM(vp) FILTER (WHERE rn <= :n) AS top10 "
                "  FROM per_chave GROUP BY data_referencia "
                "), "
                "pl AS ( "
                "  SELECT data_posicao AS d, SUM(patrimonio) AS pl "
                "  FROM wh_mec_evolucao_cotas "
                "  WHERE tenant_id = :t AND unidade_administrativa_id = :ua "
                "  GROUP BY data_posicao "
                ") "
                "SELECT agg.d AS d, "
                "       agg.maior / NULLIF(pl.pl, 0) * 100 AS maior_pct, "
                "       agg.top10 / NULLIF(pl.pl, 0) * 100 AS top10_pct "
                "FROM agg JOIN pl ON pl.d = agg.d "
                "WHERE pl.pl > 0 "
                "ORDER BY agg.d"
            ).bindparams(
                t=tenant_id, f=fundo_doc, ua=ua_id, n=_TOP_N, since=since, ate=ate
            )
        )
    ).all()
    return [
        HistoricoPonto(
            data=r.d,
            maior_pct=float(r.maior_pct or 0),
            top10_pct=float(r.top10_pct or 0),
        )
        for r in rows
    ]


def _empty(
    data_posicao: date | None,
    datas_disponiveis: list[date] | None = None,
    *,
    ua: ConcentracaoUA | None = None,
    uas: list[ConcentracaoUA] | None = None,
    suportado: bool = True,
) -> tuple[ConcentracaoData, Provenance]:
    vazio = ConcentracaoTabela(
        itens=[],
        total_financeiro=0.0,
        total_pct_pl=0.0,
        outros_qtd=0,
        outros_financeiro=0.0,
        outros_pct_pl=0.0,
    )
    data = ConcentracaoData(
        ua=ua,
        uas=uas or [],
        suportado=suportado,
        data_posicao=data_posicao or date.today(),
        pl_total=0.0,
        pl_data=None,
        pl_origem="MEC",
        datas_disponiveis=datas_disponiveis or [],
        cedentes=vazio,
        sacados=vazio,
        historico_cedentes=[],
        historico_sacados=[],
    )
    prov = Provenance(
        source_type="derived",
        source_ids=["qitech:fidc-estoque", "admin:mec"],
        ingested_by_version="bi_concentracao_v1",
        row_count=0,
    )
    return data, prov


async def get_concentracao(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID | None = None,
    data: date | None = None,
    janela: str = "12m",
) -> tuple[ConcentracaoData, Provenance]:
    """Bundle de concentracao (snapshot + historico diario).

    `ua_id` = fundo (default Realinvest, o unico suportado por enquanto; outras
    UAs retornam `suportado=False` — A7 Credit tera logica propria). `data` =
    posicao (default = ultima). `janela` = intervalo do historico. Filtros
    aplicam a TODOS os agregados (§7.2).
    """
    uas = await _uas_do_tenant(db, tenant_id=tenant_id)
    target_ua = ua_id or _REALINVEST_UA_ID
    ua_atual = next((u for u in uas if u.id == str(target_ua)), None)

    # So Realinvest tem logica de concentracao por ora. Outras UAs -> vazio +
    # suportado=False (frontend mostra nota), evita numero errado (§14).
    if target_ua != _REALINVEST_UA_ID:
        return _empty(None, uas=uas, ua=ua_atual, suportado=False)

    fundo_doc = await _resolve_fundo_doc(
        db, tenant_id=tenant_id, ua_id=_REALINVEST_UA_ID
    )
    if not fundo_doc:
        return _empty(None, uas=uas, ua=ua_atual)

    datas = await _datas_disponiveis(
        db, tenant_id=tenant_id, fundo_doc=fundo_doc, limit=_DATAS_LIMIT
    )
    if not datas:
        return _empty(None, uas=uas, ua=ua_atual)

    # Posicao escolhida (valida) ou a ultima disponivel (datas[0] = max).
    data_posicao = data if (data is not None and data <= datas[0]) else datas[0]

    pl_total, pl_data = await _pl_total(
        db, tenant_id=tenant_id, ua_id=_REALINVEST_UA_ID, data_posicao=data_posicao
    )

    cedentes = await _top_tabela(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_referencia=data_posicao,
        chave_col="cedente_doc",
        nome_col="cedente_nome",
        pl_total=pl_total,
    )
    sacados = await _top_tabela(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_referencia=data_posicao,
        chave_col="sacado_doc",
        nome_col="sacado_nome",
        pl_total=pl_total,
    )
    janela_dias = _JANELA_DIAS.get(janela, _JANELA_DIAS["12m"])
    since = data_posicao - timedelta(days=janela_dias)
    historico_cedentes = await _historico(
        db, tenant_id=tenant_id, fundo_doc=fundo_doc,
        ua_id=_REALINVEST_UA_ID, chave_col="cedente_doc",
        since=since, ate=data_posicao,
    )
    historico_sacados = await _historico(
        db, tenant_id=tenant_id, fundo_doc=fundo_doc,
        ua_id=_REALINVEST_UA_ID, chave_col="sacado_doc",
        since=since, ate=data_posicao,
    )

    data_out = ConcentracaoData(
        ua=ua_atual,
        uas=uas,
        suportado=True,
        data_posicao=data_posicao,
        pl_total=pl_total,
        pl_data=pl_data,
        pl_origem="MEC",
        datas_disponiveis=datas,
        cedentes=cedentes,
        sacados=sacados,
        historico_cedentes=historico_cedentes,
        historico_sacados=historico_sacados,
    )
    prov = Provenance(
        source_type="derived",
        source_ids=["qitech:fidc-estoque", "admin:mec"],
        ingested_by_version="bi_concentracao_v1",
        trust_level="high",
        row_count=len(cedentes.itens) + len(sacados.itens),
    )
    return data_out, prov
