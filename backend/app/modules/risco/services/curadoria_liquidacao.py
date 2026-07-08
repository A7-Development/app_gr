"""Curation listing service — ALL liquidation events, server-side paginated.

Hard handoff rules implemented here:
    - The screen sees EVERY liquidation (canais bancaria + baixa_manual),
      not only model alerts — false negatives must be taggable.
    - Rows are never excluded by score; filters are opt-in.
    - `candidato_lastro` surfaces the cross-signal suggestion (titulo with
      Status=3 'Lastro Inconsistente' that still shows as liquidated) as a
      FLAG — system suggestions are never written as tags.

Pagination is real server-side (§14.6-friendly: `total` is exposed and every
row is reachable by paging — nothing is silently cut).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risco.models import CuradoriaTag, CuradoriaTagValor, DeteccaoModelo

_SITUACAO_LASTRO_INCONSISTENTE = 3  # Titulo.Status=3 no Bitfin (dicionario 2026-07-08)

# ── Multi-select filters (BI chips, 2026-07-08) ─────────────────────────────
# Each code maps to a SQL condition; selected codes are OR-ed. Unknown codes
# are ignored (additive API — never 500 on a stale frontend).
# The `sinal` map MIRRORS `_sinais()` below — change one, change both.
_MARCACAO_SQL: dict[str, str] = {
    "fraude": "tv.tag = 'FRAUDE'",
    "ok": "tv.tag = 'OK'",
    "sem_tag": "(tv.tag IS NULL OR tv.tag = 'NEUTRO')",
    "sugeridas": "t.status = :status_lastro",
    "padrao_critico": "ds.regra_dura IS TRUE",
}
_SINAL_SQL: dict[str, str] = {
    "regra_dura": "ds.regra_dura IS TRUE",
    "baixa_confirmada": "l.evidencia = 'baixa_confirmada'",
    "pago_agencia_cedente": "l.pago_na_agencia_cliente IS TRUE",
    # ds.features e dict[str, float] (deteccao_features) — cast ::float seguro.
    "agencia_conta_cedente": "coalesce((ds.features->>'match_agencia_conta_cedente')::float, 0) > 0",
    "quebra_fingerprint": "coalesce((ds.features->>'quebra_fingerprint')::float, 0) >= 0.5",
    "boleto_nao_esperado": "coalesce((ds.features->>'boleto_nao_esperado_mas_teve')::float, 0) > 0",
    "lastro_inconsistente": "t.status = :status_lastro",
    "fora_praca_sacado": "l.pago_fora_praca_sacado IS TRUE",
    "sem_ocorrencia": "l.evidencia = 'sem_ocorrencia'",
}
# Faixas de risco como exibidas no ScoreBadge do frontend (regra_dura tem
# precedencia sobre o score — as faixas de score EXCLUEM padrao critico).
_RISCO_SQL: dict[str, str] = {
    "padrao_critico": "ds.regra_dura IS TRUE",
    "alto": "(ds.regra_dura IS NOT TRUE AND ds.score >= 0.7)",
    "medio": "(ds.regra_dura IS NOT TRUE AND ds.score >= 0.4 AND ds.score < 0.7)",
    "baixo": "(ds.regra_dura IS NOT TRUE AND ds.score < 0.4)",
    "sem_score": "(ds.regra_dura IS NOT TRUE AND ds.score IS NULL)",
}

_SQL_LISTAGEM = """
WITH tag_vigente AS (
    SELECT DISTINCT ON (ct.liquidacao_id)
        ct.liquidacao_id, ct.tag, ct.nota, ct.created_at, u.name AS autor_nome
    FROM curadoria_tag ct
    LEFT JOIN users u ON u.id = ct.autor
    WHERE ct.tenant_id = :tenant_id AND ct.modelo_id = :modelo_id
    ORDER BY ct.liquidacao_id, ct.created_at DESC
)
SELECT
    l.id AS liquidacao_id,
    l.titulo_id,
    l.canal,
    l.evidencia,
    l.data_evento,
    l.situacao_titulo,
    coalesce(l.valor_pago, l.valor_titulo) AS valor,
    l.local_pagamento,
    l.pago_na_agencia_cliente,
    l.pago_na_praca_cliente,
    l.pago_fora_praca_sacado,
    t.numero AS titulo_numero,
    t.status AS titulo_status,
    o.cedente_nome,
    o.cedente_documento,
    split_part(o.modalidade, '-', 1) AS produto_sigla,
    dp.nome AS produto_nome,
    bv.sacado_nome,
    bv.sacado_documento,
    ds.score,
    ds.fatores,
    ds.features AS score_features,
    ds.regra_dura,
    ds.regra_dura_motivo,
    -- NEUTRO como tag vigente = volta a "sem marcacao" (append-only: a linha
    -- NEUTRO existe e preserva a auditoria, mas a UI a trata como neutro).
    nullif(tv.tag, 'NEUTRO') AS tag_vigente,
    tv.nota AS tag_nota,
    tv.autor_nome AS tag_autor,
    tv.created_at AS tag_em,
    (t.status = :status_lastro) AS candidato_lastro,
    count(*) OVER () AS total
FROM wh_liquidacao l
JOIN wh_titulo t
    ON t.titulo_id = l.titulo_id AND t.tenant_id = l.tenant_id
LEFT JOIN wh_operacao o
    ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
LEFT JOIN wh_dim_produto dp
    ON dp.tenant_id = l.tenant_id
   AND dp.sigla = split_part(o.modalidade, '-', 1)
LEFT JOIN LATERAL (
    SELECT b.sacado_nome, b.sacado_documento
    FROM wh_boleto_vigente b
    WHERE b.tenant_id = l.tenant_id AND b.numero_documento = t.numero
    LIMIT 1
) bv ON true
LEFT JOIN deteccao_score ds
    ON ds.tenant_id = l.tenant_id
   AND ds.modelo_id = :modelo_id
   AND ds.liquidacao_id = l.id
LEFT JOIN tag_vigente tv ON tv.liquidacao_id = l.id
WHERE l.tenant_id = :tenant_id
  AND l.canal IN ('bancaria', 'baixa_manual')
  {filtros}
ORDER BY ds.regra_dura DESC NULLS LAST, ds.score DESC NULLS LAST,
         l.data_evento DESC
LIMIT :limit OFFSET :offset
"""


async def _modelo_id(db: AsyncSession, nome: str) -> UUID:
    modelo = (
        await db.execute(select(DeteccaoModelo).where(DeteccaoModelo.nome == nome))
    ).scalar_one_or_none()
    if modelo is None:
        raise ValueError(f"Modelo '{nome}' nao existe no catalogo.")
    return modelo.id


async def listar_liquidacoes(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    modelo_nome: str = "liquidacao_boleto",
    page: int = 1,
    page_size: int = 50,
    data_ini: date | None = None,
    data_fim: date | None = None,
    produto_sigla: str | None = None,
    cedente_busca: str | None = None,
    sacado_busca: str | None = None,
    documento_busca: str | None = None,
    situacao_titulo: int | None = None,
    tag: str | None = None,  # 'fraude' | 'ok' | 'sem_tag'
    score_min: float | None = None,
    somente_regra_dura: bool = False,
    somente_sugeridos: bool = False,
    # Multi-select (chips BI) — OR dentro de cada eixo, AND entre eixos.
    produtos: list[str] | None = None,
    situacoes: list[int] | None = None,
    marcacoes: list[str] | None = None,
    sinais_sel: list[str] | None = None,
    riscos: list[str] | None = None,
) -> dict[str, Any]:
    """One page of the curation universe + total (nothing silently cut)."""
    modelo_id = await _modelo_id(db, modelo_nome)

    filtros: list[str] = []
    params: dict[str, Any] = {
        "tenant_id": tenant_id,
        "modelo_id": modelo_id,
        "status_lastro": _SITUACAO_LASTRO_INCONSISTENTE,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    if data_ini is not None:
        filtros.append("AND l.data_evento >= :data_ini")
        params["data_ini"] = data_ini
    if data_fim is not None:
        filtros.append("AND l.data_evento < (:data_fim::date + 1)")
        params["data_fim"] = data_fim
    if produto_sigla:
        filtros.append("AND split_part(o.modalidade, '-', 1) = :produto_sigla")
        params["produto_sigla"] = produto_sigla.upper()
    if cedente_busca:
        digitos = "".join(c for c in cedente_busca if c.isdigit())
        if digitos:
            filtros.append(
                "AND (o.cedente_nome ILIKE :cedente_busca "
                "OR o.cedente_documento LIKE :cedente_busca_doc)"
            )
            params["cedente_busca_doc"] = f"%{digitos}%"
        else:
            filtros.append("AND o.cedente_nome ILIKE :cedente_busca")
        params["cedente_busca"] = f"%{cedente_busca}%"
    if sacado_busca:
        digitos = "".join(c for c in sacado_busca if c.isdigit())
        if digitos:
            filtros.append(
                "AND (bv.sacado_nome ILIKE :sacado_busca "
                "OR bv.sacado_documento LIKE :sacado_busca_doc)"
            )
            params["sacado_busca_doc"] = f"%{digitos}%"
        else:
            filtros.append("AND bv.sacado_nome ILIKE :sacado_busca")
        params["sacado_busca"] = f"%{sacado_busca}%"
    if documento_busca:
        # Numero do documento no sistema (ex.: "4902/1") ou o id do titulo.
        filtros.append(
            "AND (t.numero ILIKE :documento_busca "
            "OR CAST(t.titulo_id AS TEXT) = :documento_exato)"
        )
        params["documento_busca"] = f"%{documento_busca.strip()}%"
        params["documento_exato"] = documento_busca.strip()
    if situacao_titulo is not None:
        filtros.append("AND l.situacao_titulo = :situacao_titulo")
        params["situacao_titulo"] = situacao_titulo
    if tag == "sem_tag":
        # Nunca marcada OU marcada e depois neutralizada — ambas sem veredito.
        filtros.append("AND (tv.tag IS NULL OR tv.tag = 'NEUTRO')")
    elif tag in ("fraude", "ok"):
        filtros.append("AND tv.tag = :tag")
        params["tag"] = tag.upper()
    if score_min is not None:
        filtros.append("AND ds.score >= :score_min")
        params["score_min"] = score_min
    if somente_regra_dura:
        filtros.append("AND ds.regra_dura IS TRUE")
    if somente_sugeridos:
        filtros.append("AND t.status = :status_lastro")

    if produtos:
        keys: list[str] = []
        for i, p in enumerate(produtos):
            params[f"prod_{i}"] = p.upper()
            keys.append(f":prod_{i}")
        filtros.append(f"AND split_part(o.modalidade, '-', 1) IN ({', '.join(keys)})")
    if situacoes:
        keys = []
        for i, s in enumerate(situacoes):
            params[f"sit_{i}"] = s
            keys.append(f":sit_{i}")
        filtros.append(f"AND l.situacao_titulo IN ({', '.join(keys)})")
    for selecionados, mapa in (
        (marcacoes, _MARCACAO_SQL),
        (sinais_sel, _SINAL_SQL),
        (riscos, _RISCO_SQL),
    ):
        if selecionados:
            conds = [mapa[c] for c in selecionados if c in mapa]
            if conds:
                filtros.append("AND (" + " OR ".join(conds) + ")")

    sql = text(_SQL_LISTAGEM.format(filtros="\n  ".join(filtros)))
    rows = (await db.execute(sql, params)).mappings().all()
    total = int(rows[0]["total"]) if rows else 0

    saida = []
    for r in rows:
        d = dict(r)
        d["sinais"] = _sinais(d)
        d.pop("score_features", None)  # interno — a conclusao vira `sinais`
        saida.append(d)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "rows": saida,
    }


def _sinais(row: dict[str, Any]) -> list[str]:
    """Legible system conclusions for one row, most severe first.

    "Qual foi o bad dele" (feedback Ricardo 2026-07-08): the screen must say
    WHY the system looked at this liquidation, independently of a trained
    score. Declared fields always exist; score features enrich when a
    scoring row exists. Codes are translated to pt-BR in the frontend.
    """
    s: list[str] = []
    if row.get("regra_dura"):
        s.append("regra_dura")
    if row.get("evidencia") == "baixa_confirmada":
        s.append("baixa_confirmada")
    if row.get("pago_na_agencia_cliente"):
        s.append("pago_agencia_cedente")
    feats = row.get("score_features") or {}
    if feats.get("match_agencia_conta_cedente"):
        s.append("agencia_conta_cedente")
    if (feats.get("quebra_fingerprint") or 0) >= 0.5:
        s.append("quebra_fingerprint")
    if feats.get("boleto_nao_esperado_mas_teve"):
        s.append("boleto_nao_esperado")
    if row.get("candidato_lastro"):
        s.append("lastro_inconsistente")
    if row.get("pago_fora_praca_sacado"):
        s.append("fora_praca_sacado")
    if row.get("evidencia") == "sem_ocorrencia":
        s.append("sem_ocorrencia")
    return s


async def registrar_tag(
    db: AsyncSession,
    tenant_id: UUID,
    liquidacao_id: UUID,
    *,
    modelo_nome: str = "liquidacao_boleto",
    tag: CuradoriaTagValor,
    nota: str | None,
    autor: UUID,
) -> CuradoriaTag | None:
    """Append one human verdict (never updates, never deletes).

    Returns None when the liquidation does not belong to the tenant —
    cross-tenant tagging must 404, never write (§10).
    """
    modelo_id = await _modelo_id(db, modelo_nome)
    pertence = (
        await db.execute(
            text("SELECT 1 FROM wh_liquidacao WHERE id = :id AND tenant_id = :tenant_id"),
            {"id": liquidacao_id, "tenant_id": tenant_id},
        )
    ).scalar_one_or_none()
    if pertence is None:
        return None
    registro = CuradoriaTag(
        tenant_id=tenant_id,
        modelo_id=modelo_id,
        liquidacao_id=liquidacao_id,
        tag=tag,
        nota=nota,
        autor=autor,
    )
    db.add(registro)
    await db.flush()
    return registro
