"""Controladoria · Cota Sub — Balancete Patrimonial Diario COSIF.

Computa o balancete sintetico do fundo em D0 e D-1, classificado em
arvore COSIF, e calcula a reconciliacao da Cota Subordinada:

    PL Cota Sub = SUM_silver_TOTAL - |Cotas Sr emitidas| - |Cotas Mez emitidas|

    Delta PL Cota Sub = Delta_Total - Delta_Sr - Delta_Mez   (residuo deve ser 0)

Substitui a `services/balanco.py::compute_balanco` quando o frontend
migrar para a nova UI. Por enquanto coexistem — a UI atual usa o
antigo, a Fase 1 da PR3 conecta ao novo.

Origem dos dados — APENAS silver canonico (CLAUDE.md §13.2.1).
Classificacao em runtime via `services/cosif/classifier.py`.

Design completo: backend/docs/atribuicao-cota-sub-cosif.md.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.controladoria.services.cosif import (
    CosifResolution,
    classify,
    load_catalog_tree,
    load_overrides,
    load_rules_cache,
)
from app.modules.integracoes.public import dia_util_anterior_qitech


# ─── Tipos de saida ──────────────────────────────────────────────────────────

@dataclass
class CosifNode:
    """No da arvore COSIF — saldo D-1, D0, delta."""
    codigo: str | None  # None = pendente
    nome: str
    natureza: str  # D | C | ?
    nivel: int  # 0 = pendente
    grupo: int  # 1, 4, 6, 8, ou 0 se pendente
    parent_codigo: str | None
    d_minus_1: Decimal
    d_zero: Decimal
    delta: Decimal
    delta_pct: Decimal  # delta / abs(d_minus_1) * 100
    # Counters para auditoria de cobertura.
    rows_classified: int
    cosif_source: str  # 'override' | 'rule' | 'mixed' | 'pendente'


@dataclass
class ClasseSrMezSubBreakdown:
    """Sub-quebra por classe Sr/Mez/Sub dentro de uma conta COSIF."""
    classe: str  # senior | mezanino | subordinado | compensacao | aporte
    d_minus_1: Decimal
    d_zero: Decimal
    delta: Decimal


@dataclass
class Reconciliacao:
    """Equacao da Cota Sub D-1 vs D0."""
    pl_total_d1: Decimal
    pl_total_d0: Decimal
    delta_pl_total: Decimal
    cotas_sr_emitidas_d1: Decimal  # modulo
    cotas_sr_emitidas_d0: Decimal
    delta_cotas_sr: Decimal
    cotas_mez_emitidas_d1: Decimal
    cotas_mez_emitidas_d0: Decimal
    delta_cotas_mez: Decimal
    pl_cota_sub_d1: Decimal
    pl_cota_sub_d0: Decimal
    delta_pl_cota_sub_real: Decimal
    delta_pl_cota_sub_esperado: Decimal  # delta_total - delta_sr - delta_mez
    residuo: Decimal  # real - esperado
    delta_pct_sobre_d1: Decimal  # delta_real / abs(d1) * 100


@dataclass
class Cobertura:
    """Estatistica de classificacao."""
    total_rows: int
    rows_por_source: dict[str, int]  # 'override'|'rule'|'pendente' -> count
    valor_por_source: dict[str, Decimal]
    top_pendentes: list[tuple[str, str, Decimal]]
    # cada tupla: (silver_origin, identificador, valor)


@dataclass
class CosifRow:
    """Row do silver subjacente a uma conta COSIF.

    Devolvido por `compute_cosif_rows()` para o drill-down do
    `CosifDrillSheet` na UI — lista os papeis individuais que sustentam
    o saldo da conta analitica.
    """
    silver_origin: str
    codigo: str | None  # identificador da row no silver (ex.: codigo do papel)
    nome: str
    valor: Decimal
    quantidade: Decimal | None  # so wh_posicao_renda_fixa
    indexador: str | None        # so wh_posicao_renda_fixa
    cosif_source: str            # 'override' | 'rule:<rid>'


@dataclass
class CosifRowsResponse:
    fundo_id: UUID
    data_posicao: date
    cosif_codigo: str
    cosif_nome: str
    total_valor: Decimal
    rows: list[CosifRow]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fundo_id": self.fundo_id,
            "data_posicao": self.data_posicao,
            "cosif_codigo": self.cosif_codigo,
            "cosif_nome": self.cosif_nome,
            "total_valor": self.total_valor,
            "rows": [asdict(r) for r in self.rows],
        }


@dataclass
class BalanceteResponse:
    fundo_id: UUID
    data_d_zero: date
    data_d_minus_1: date
    nodes: list[CosifNode]  # arvore plana
    classe_breakdown_por_cosif: dict[str, list[ClasseSrMezSubBreakdown]]
    reconciliacao: Reconciliacao
    cobertura: Cobertura

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict adequado a Pydantic (BalanceteResponseSchema)."""
        return {
            "fundo_id": self.fundo_id,
            "data_d_zero": self.data_d_zero,
            "data_d_minus_1": self.data_d_minus_1,
            "nodes": [asdict(n) for n in self.nodes],
            "classe_breakdown_por_cosif": {
                k: [asdict(b) for b in v]
                for k, v in self.classe_breakdown_por_cosif.items()
            },
            "reconciliacao": asdict(self.reconciliacao),
            "cobertura": {
                "total_rows": self.cobertura.total_rows,
                "rows_por_source": self.cobertura.rows_por_source,
                "valor_por_source": self.cobertura.valor_por_source,
                "top_pendentes": [
                    {"silver_origin": s, "identificador": i, "valor": v}
                    for (s, i, v) in self.cobertura.top_pendentes
                ],
            },
        }


# ─── Queries de silver ───────────────────────────────────────────────────────

_QUERIES: dict[str, str] = {
    "wh_saldo_conta_corrente": """
        SELECT codigo, descricao AS nome, valor_total AS valor
        FROM wh_saldo_conta_corrente
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_saldo_tesouraria": """
        SELECT NULL AS codigo, descricao AS nome, valor
        FROM wh_saldo_tesouraria
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_posicao_compromissada": """
        SELECT codigo, papel AS nome, valor_bruto AS valor
        FROM wh_posicao_compromissada
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_posicao_renda_fixa": """
        SELECT codigo, nome_do_papel AS nome, valor_bruto AS valor,
               nome_do_papel, quantidade, indexador
        FROM wh_posicao_renda_fixa
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_posicao_cota_fundo": """
        SELECT ativo_codigo AS codigo, ativo_nome AS nome, valor_atual AS valor,
               ativo_nome
        FROM wh_posicao_cota_fundo
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_posicao_outros_ativos": """
        SELECT codigo, descricao AS nome, valor_total AS valor
        FROM wh_posicao_outros_ativos
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_cpr_movimento": """
        SELECT NULL AS codigo, COALESCE(historico_traduzido, descricao) AS nome,
               valor, historico_traduzido, descricao
        FROM wh_cpr_movimento
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
}


@dataclass
class _SilverRow:
    silver_origin: str
    nome: str
    valor: Decimal
    raw: dict[str, Any]


async def _fetch_silver(
    db: AsyncSession, ua_id: UUID, d: date
) -> list[_SilverRow]:
    out: list[_SilverRow] = []
    for origin, sql in _QUERIES.items():
        result = await db.execute(text(sql), {"ua": ua_id, "d": d})
        for row in result.mappings().all():
            r = dict(row)
            valor = Decimal(str(r.get("valor") or 0))
            out.append(_SilverRow(
                silver_origin=origin,
                nome=r.get("nome") or "",
                valor=valor,
                raw=r,
            ))
    return out


# ─── Pipeline principal ──────────────────────────────────────────────────────

async def compute_balancete_diario(
    db: AsyncSession,
    tenant_id: UUID,
    fundo_id: UUID,
    data_d_zero: date,
    data_d_minus_1: date | None = None,
) -> BalanceteResponse:
    """Computa o balancete diario completo do fundo.

    Se `data_d_minus_1` for None, usa `dia_util_anterior_qitech` para
    inferir D-1 a partir da `wh_dia_util_qitech` (CLAUDE.md §11.6, mesmo
    criterio do Calendar da UI).
    """
    if data_d_minus_1 is None:
        data_d_minus_1 = await dia_util_anterior_qitech(
            db, tenant_id, fundo_id, data_d_zero
        )

    # 1. Carrega cache de regras + overrides do fundo
    rules_cache = await load_rules_cache(db)
    overrides = await load_overrides(db, tenant_id, fundo_id)
    catalog = await load_catalog_tree(db)

    # 2. Le silver D-1 e D0
    rows_d1 = await _fetch_silver(db, fundo_id, data_d_minus_1)
    rows_d0 = await _fetch_silver(db, fundo_id, data_d_zero)

    # 3. Classifica cada row + agrega por (cosif, classe)
    analytic_d1, sources_d1, breakdown_d1 = _classify_and_aggregate(
        rows_d1, rules_cache, overrides
    )
    analytic_d0, sources_d0, breakdown_d0 = _classify_and_aggregate(
        rows_d0, rules_cache, overrides
    )

    # 4. Propaga saldos para ancestrais via parent_codigo
    saldos_d1 = _propagate_to_parents(analytic_d1, catalog)
    saldos_d0 = _propagate_to_parents(analytic_d0, catalog)

    # 5. Monta arvore de nodes (uniao de keys D-1 + D0).
    # None (pendente) ordenado para o final via fallback.
    all_codigos = sorted(
        set(saldos_d1) | set(saldos_d0),
        key=lambda c: (c is None, c or ""),
    )
    nodes: list[CosifNode] = []
    for cod in all_codigos:
        info = catalog.get(cod) if cod else None
        nome = info.nome if info else "(nao classificado)"
        natureza = info.natureza if info else "?"
        nivel = info.nivel if info else 0
        grupo = info.grupo if info else 0
        parent = info.parent_codigo if info else None
        d1 = saldos_d1.get(cod, Decimal(0))
        d0 = saldos_d0.get(cod, Decimal(0))
        delta = d0 - d1
        delta_pct = (delta / abs(d1) * 100) if d1 else Decimal(0)
        nodes.append(CosifNode(
            codigo=cod, nome=nome, natureza=natureza, nivel=nivel,
            grupo=grupo, parent_codigo=parent,
            d_minus_1=d1, d_zero=d0,
            delta=delta, delta_pct=delta_pct,
            rows_classified=0, cosif_source="",
        ))

    # 6. Classe breakdown (Sr/Mez/Sub/Aporte/Compensacao) por cosif
    classe_breakdown = _build_classe_breakdown(breakdown_d1, breakdown_d0)

    # 7. Reconciliacao Cota Sub
    pl_total_d1 = sum((r.valor for r in rows_d1), Decimal(0))
    pl_total_d0 = sum((r.valor for r in rows_d0), Decimal(0))
    sr_d1 = _sum_cotas_emitidas(rows_d1, rules_cache, overrides, "senior")
    sr_d0 = _sum_cotas_emitidas(rows_d0, rules_cache, overrides, "senior")
    mez_d1 = _sum_cotas_emitidas(rows_d1, rules_cache, overrides, "mezanino")
    mez_d0 = _sum_cotas_emitidas(rows_d0, rules_cache, overrides, "mezanino")
    pl_sub_d1 = pl_total_d1 - sr_d1 - mez_d1
    pl_sub_d0 = pl_total_d0 - sr_d0 - mez_d0
    delta_pl_total = pl_total_d0 - pl_total_d1
    delta_sr = sr_d0 - sr_d1
    delta_mez = mez_d0 - mez_d1
    delta_real = pl_sub_d0 - pl_sub_d1
    delta_esp = delta_pl_total - delta_sr - delta_mez
    residuo = delta_real - delta_esp
    pct = (delta_real / abs(pl_sub_d1) * 100) if pl_sub_d1 else Decimal(0)
    reconciliacao = Reconciliacao(
        pl_total_d1=pl_total_d1, pl_total_d0=pl_total_d0,
        delta_pl_total=delta_pl_total,
        cotas_sr_emitidas_d1=sr_d1, cotas_sr_emitidas_d0=sr_d0,
        delta_cotas_sr=delta_sr,
        cotas_mez_emitidas_d1=mez_d1, cotas_mez_emitidas_d0=mez_d0,
        delta_cotas_mez=delta_mez,
        pl_cota_sub_d1=pl_sub_d1, pl_cota_sub_d0=pl_sub_d0,
        delta_pl_cota_sub_real=delta_real,
        delta_pl_cota_sub_esperado=delta_esp,
        residuo=residuo,
        delta_pct_sobre_d1=pct,
    )

    # 8. Cobertura (foco no D0 — relatorio atual)
    cob = _build_cobertura(rows_d0, rules_cache, overrides)

    return BalanceteResponse(
        fundo_id=fundo_id,
        data_d_zero=data_d_zero,
        data_d_minus_1=data_d_minus_1,
        nodes=nodes,
        classe_breakdown_por_cosif=classe_breakdown,
        reconciliacao=reconciliacao,
        cobertura=cob,
    )


# ─── Helpers internos ────────────────────────────────────────────────────────

def _classify_and_aggregate(
    rows: list[_SilverRow],
    rules_cache, overrides,
) -> tuple[
    dict[str | None, Decimal],          # cosif analitico -> saldo
    dict[str | None, list[str]],         # cosif analitico -> sources
    dict[str | None, dict[str, Decimal]],  # cosif -> classe -> saldo
]:
    """Classifica cada row e agrega saldos por cosif analitico + classe."""
    analytic: dict[str | None, Decimal] = defaultdict(lambda: Decimal(0))
    sources: dict[str | None, list[str]] = defaultdict(list)
    breakdown: dict[str | None, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal(0))
    )
    for r in rows:
        res = classify(r.silver_origin, r.raw, rules_cache, overrides)
        analytic[res.cosif] += r.valor
        sources[res.cosif].append(res.source.split(":")[0])
        if res.classe_sr_mez_sub:
            breakdown[res.cosif][res.classe_sr_mez_sub] += r.valor
    return analytic, sources, breakdown


def _propagate_to_parents(
    analytic: dict[str | None, Decimal],
    catalog,
) -> dict[str | None, Decimal]:
    """Cada saldo analitico soma para todos os ancestrais via parent."""
    out: dict[str | None, Decimal] = defaultdict(lambda: Decimal(0))
    for cosif, valor in analytic.items():
        cur = cosif
        while cur is not None:
            out[cur] += valor
            info = catalog.get(cur)
            if info is None:
                break
            cur = info.parent_codigo
        if cosif is None:
            # Pendente — propaga para None (bucket especial).
            out[None] += valor
    return out


def _build_classe_breakdown(
    breakdown_d1: dict[str | None, dict[str, Decimal]],
    breakdown_d0: dict[str | None, dict[str, Decimal]],
) -> dict[str, list[ClasseSrMezSubBreakdown]]:
    """Une breakdown D-1 + D0 por (cosif, classe) e calcula delta."""
    out: dict[str, list[ClasseSrMezSubBreakdown]] = {}
    cosifs = set(breakdown_d1) | set(breakdown_d0)
    for cosif in cosifs:
        if cosif is None:
            continue  # sem cosif (pendente) — nao expor breakdown
        classes = set(breakdown_d1.get(cosif, {})) | set(
            breakdown_d0.get(cosif, {})
        )
        items = []
        for classe in sorted(classes):
            d1 = breakdown_d1.get(cosif, {}).get(classe, Decimal(0))
            d0 = breakdown_d0.get(cosif, {}).get(classe, Decimal(0))
            items.append(ClasseSrMezSubBreakdown(
                classe=classe,
                d_minus_1=d1, d_zero=d0,
                delta=d0 - d1,
            ))
        if items:
            out[cosif] = items
    return out


def _sum_cotas_emitidas(
    rows: list[_SilverRow], rules_cache, overrides, classe: str,
) -> Decimal:
    """Soma |valor| das cotas emitidas (qtde<0 em wh_posicao_renda_fixa) da classe."""
    total = Decimal(0)
    for r in rows:
        if r.silver_origin != "wh_posicao_renda_fixa":
            continue
        res = classify(r.silver_origin, r.raw, rules_cache, overrides)
        if res.classe_sr_mez_sub == classe:
            total += abs(r.valor)
    return total


def _build_cobertura(rows, rules_cache, overrides) -> Cobertura:
    counts: dict[str, int] = defaultdict(int)
    valor_por_source: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    pendentes: list[tuple[str, str, Decimal]] = []
    for r in rows:
        res = classify(r.silver_origin, r.raw, rules_cache, overrides)
        src = res.source.split(":")[0]
        counts[src] += 1
        valor_por_source[src] += abs(r.valor)
        if src == "pendente":
            ident = r.raw.get("codigo") or r.nome
            pendentes.append((r.silver_origin, str(ident), r.valor))
    pendentes.sort(key=lambda x: abs(x[2]), reverse=True)
    return Cobertura(
        total_rows=len(rows),
        rows_por_source=dict(counts),
        valor_por_source=dict(valor_por_source),
        top_pendentes=pendentes[:10],
    )


# ─── Drill-down por conta COSIF ─────────────────────────────────────────────


async def compute_cosif_rows(
    db: AsyncSession,
    tenant_id: UUID,
    fundo_id: UUID,
    data_posicao: date,
    cosif_codigo: str,
) -> CosifRowsResponse:
    """Lista as rows do silver que sustentam o saldo de uma conta COSIF.

    Usado pelo `CosifDrillSheet` na UI quando o usuario clica numa conta
    analitica para ver os papeis individuais (ex.: clicar em
    `1.3.1.15.30.001` mostra "739704 ITAU SOBERANO REF SI").

    Aceita tanto conta analitica (folha) quanto sintetica (agrega todos
    os descendentes). Resolve pela cascata override -> rule do classifier
    em runtime — mesma logica de `compute_balancete_diario`.

    Multi-tenant: query do silver ja filtra por `unidade_administrativa_id`
    (= fundo_id); tenant_id reservado para futura validacao de subscription.
    """
    rules_cache = await load_rules_cache(db)
    overrides = await load_overrides(db, tenant_id, fundo_id)
    catalog = await load_catalog_tree(db)

    info = catalog.get(cosif_codigo)
    if info is None:
        raise ValueError(
            f"COSIF '{cosif_codigo}' nao existe no catalogo."
        )

    # Conjunto de codigos aceitos: o solicitado + todos os descendentes
    # (para o caso de o usuario clicar numa conta sintetica).
    accepted: set[str] = {cosif_codigo}
    for cod, node in catalog.items():
        cur = node.parent_codigo
        while cur is not None:
            if cur == cosif_codigo:
                accepted.add(cod)
                break
            parent = catalog.get(cur)
            if parent is None:
                break
            cur = parent.parent_codigo

    rows = await _fetch_silver(db, fundo_id, data_posicao)

    out: list[CosifRow] = []
    total = Decimal(0)
    for r in rows:
        res = classify(r.silver_origin, r.raw, rules_cache, overrides)
        if res.cosif not in accepted:
            continue
        qtde = r.raw.get("quantidade")
        indexador = r.raw.get("indexador")
        out.append(CosifRow(
            silver_origin=r.silver_origin,
            codigo=r.raw.get("codigo"),
            nome=r.nome,
            valor=r.valor,
            quantidade=Decimal(str(qtde)) if qtde is not None else None,
            indexador=indexador,
            cosif_source=res.source,
        ))
        total += r.valor

    # Ordena por |valor| desc — mais material primeiro.
    out.sort(key=lambda x: abs(x.valor), reverse=True)

    return CosifRowsResponse(
        fundo_id=fundo_id,
        data_posicao=data_posicao,
        cosif_codigo=cosif_codigo,
        cosif_nome=info.nome,
        total_valor=total,
        rows=out,
    )
