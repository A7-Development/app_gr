"""Controladoria · Cota Sub — Balancete Patrimonial Diario COSIF.

Computa o balancete sintetico do fundo em D0 e D-1, classificado em
arvore COSIF, e calcula a reconciliacao da Cota Subordinada:

    PL Sub Real (MEC)      = patrimonio da classe Sub em `wh_mec_evolucao_cotas`
                             (medida direta da administradora QiTech — qtde x cota)
    PL Sub Esperado (COSIF) = PL_Total - |Sr_emitidas| - |Mez_emitidas|
                              (derivado do balancete silver, classificacao runtime)
    Residuo                 = Real - Esperado   (!= 0 em geral; testa fechamento)

Real e Esperado vem de fontes **independentes**: MEC e o produto qtde x cota
patrimonial reportado pelo administrador; Esperado e a soma agregada dos silvers
do balancete menos as cotas Sr/Mez classificadas. Divergencias significativas
apontam pra classificacao errada, override pendente, evento nao lancado, ou
divergencia da propria QiTech.

Quando o MEC do dia ainda nao foi publicado (sync `daily_at 08:30`), a comparacao
e marcada como `data_quality.comparable=false` com motivo explicito — a UI ja
trata isso (overlay "Comparacao nao confiavel" no waterfall).

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
class DataQuality:
    """Qualidade do snapshot D-1 vs D0 — detecta comparacoes invalidas.

    Anomalia tipica: `wh_dia_util_qitech` marca uma data como `status='completo'`
    mas alguns dos 7 silvers nao foram ingeridos (ETL parcial). Caso real:
    REALINVEST 30/04 e 11/05/2026 — apenas `wh_posicao_renda_fixa` populada.
    Quando o usuario seleciona D0=04/05, o backend infere D-1=30/04 (snapshot
    parcial), e o ΔPL Cota Sub vira gigante (compara renda_fixa-only com
    snapshot completo de D0).

    Regra `comparable`: True sse nenhum silver tem sinal divergente — ou seja,
    para cada silver, ou ambos os dias tem rows ou ambos nao tem. Quando um
    silver tem dados em D-1 mas nao em D0 (ou inverso), comparacao distorce.

    Ver follow-up [[project_qitech_freshness_followups]].
    """
    silvers_d1: dict[str, int]   # silver_origin -> count de rows em D-1
    silvers_d0: dict[str, int]
    silvers_divergentes: list[str]  # silvers presentes so em um dos dias
    comparable: bool
    reason: str | None = None  # mensagem humano-readable quando !comparable


@dataclass
class CosifRowDiff:
    """Papel individual que sustenta o saldo de uma conta COSIF, comparado
    entre D-1 e D0.

    Devolvido por `compute_cosif_rows()` para o drill-down do
    `CosifDrillSheet`. Mescha foto (composicao em D0) com movimento
    (variacao D-1 -> D0) numa linha so — controller ve em 1 lugar o
    que tem hoje E o que mudou.

    Status (derivado dos valores):
      novo        — existia so em D0  (valor_d_minus_1 == 0)
      removido    — existia so em D-1 (valor_d_zero == 0)
      alterado    — existia em ambos com delta != 0
      inalterado  — existia em ambos com delta == 0
    """
    silver_origin: str
    codigo: str | None
    nome: str
    valor_d_minus_1: Decimal
    valor_d_zero: Decimal
    delta: Decimal
    quantidade_d_minus_1: Decimal | None
    quantidade_d_zero: Decimal | None
    indexador: str | None
    cosif_source: str
    status: str  # 'novo' | 'removido' | 'alterado' | 'inalterado'
    # Contraparte: emitente (renda fixa) ou ativo_instituicao (cota fundo).
    # None nos silvers que nao tem nocao de contraparte (caixa, CPR, etc).
    contraparte: str | None = None


@dataclass
class CosifRowsResponse:
    fundo_id: UUID
    data_d_zero: date
    data_d_minus_1: date
    cosif_codigo: str
    cosif_nome: str
    total_valor_d_minus_1: Decimal
    total_valor_d_zero: Decimal
    total_delta: Decimal
    rows: list[CosifRowDiff]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fundo_id": self.fundo_id,
            "data_d_zero": self.data_d_zero,
            "data_d_minus_1": self.data_d_minus_1,
            "cosif_codigo": self.cosif_codigo,
            "cosif_nome": self.cosif_nome,
            "total_valor_d_minus_1": self.total_valor_d_minus_1,
            "total_valor_d_zero": self.total_valor_d_zero,
            "total_delta": self.total_delta,
            "rows": [asdict(r) for r in self.rows],
        }


@dataclass
class BalanceteResponse:
    fundo_id: UUID
    data_d_zero: date
    data_d_minus_1: date
    nodes: list[CosifNode]  # arvore plana
    classe_breakdown_por_cosif: dict[str, list[ClasseSrMezSubBreakdown]]
    rows_por_cosif: dict[str, list[CosifRowDiff]]  # papel-a-papel por conta analitica
    reconciliacao: Reconciliacao
    cobertura: Cobertura
    data_quality: DataQuality

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
            "rows_por_cosif": {
                k: [asdict(r) for r in v]
                for k, v in self.rows_por_cosif.items()
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
            "data_quality": asdict(self.data_quality),
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
        SELECT codigo, papel AS nome, valor_bruto AS valor, quantidade
        FROM wh_posicao_compromissada
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_posicao_renda_fixa": """
        SELECT codigo, nome_do_papel AS nome, valor_bruto AS valor,
               nome_do_papel, quantidade, indexador, emitente
        FROM wh_posicao_renda_fixa
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_posicao_cota_fundo": """
        SELECT ativo_codigo AS codigo, ativo_nome AS nome, valor_atual AS valor,
               ativo_nome, quantidade, ativo_instituicao
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


# Heuristica de identificacao da classe Sub no MEC: o relatorio
# `market.mec` da QiTech quebra o fundo por classe via `carteira_cliente_nome`.
# As classes Sr/Mez carregam os tokens "SENIOR"/"MEZANINO" no nome; a Sub e o
# residual (no Realinvest e literalmente "REALINVEST FIDC", sem sufixo). Se
# aparecer outro fundo com nomenclatura distinta, evoluir pra mapeamento
# explicito (fundo_id -> carteira_cliente_id da Sub).
_SQL_PL_SUB_MEC = """
    SELECT COALESCE(SUM(patrimonio), 0) AS pl_sub,
           COUNT(*) AS classes_sub
    FROM wh_mec_evolucao_cotas
    WHERE unidade_administrativa_id = :ua
      AND data_posicao = :d
      AND carteira_cliente_nome !~* '\\m(senior|mezanino)\\M'
"""


async def _fetch_pl_sub_mec(
    db: AsyncSession, ua_id: UUID, d: date,
) -> Decimal | None:
    """Le o PL da classe Subordinada direto do MEC (medida independente).

    Retorna None quando o MEC do dia ainda nao foi ingerido para esse fundo —
    caller marca a reconciliacao como `comparable=false`.

    Levanta `RuntimeError` se mais de 1 classe nao-Sr/Mez aparecer (sinal
    de fundo com nomenclatura fora do padrao Realinvest; vale revisar a
    heuristica ou mapear explicitamente).
    """
    result = await db.execute(text(_SQL_PL_SUB_MEC), {"ua": ua_id, "d": d})
    row = result.mappings().one()
    count = int(row["classes_sub"] or 0)
    if count == 0:
        return None
    if count > 1:
        raise RuntimeError(
            f"MEC retornou {count} classes nao-Sr/Mez em {d.isoformat()} para "
            f"unidade_administrativa_id={ua_id}. Heuristica de identificacao "
            f"da Sub e ambigua — revisar nomes em wh_mec_evolucao_cotas."
        )
    return Decimal(str(row["pl_sub"]))


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
    # Esperado (derivado do balancete) = ΔPL_Total - ΔSr_emitidas - ΔMez_emitidas.
    # Real (direto do MEC)             = ΔPatrimonio da classe Sub via wh_mec_evolucao_cotas.
    pl_total_d1 = sum((r.valor for r in rows_d1), Decimal(0))
    pl_total_d0 = sum((r.valor for r in rows_d0), Decimal(0))
    sr_d1 = _sum_cotas_emitidas(rows_d1, rules_cache, overrides, "senior")
    sr_d0 = _sum_cotas_emitidas(rows_d0, rules_cache, overrides, "senior")
    mez_d1 = _sum_cotas_emitidas(rows_d1, rules_cache, overrides, "mezanino")
    mez_d0 = _sum_cotas_emitidas(rows_d0, rules_cache, overrides, "mezanino")
    delta_pl_total = pl_total_d0 - pl_total_d1
    delta_sr = sr_d0 - sr_d1
    delta_mez = mez_d0 - mez_d1
    delta_esp = delta_pl_total - delta_sr - delta_mez

    mec_sub_d1 = await _fetch_pl_sub_mec(db, fundo_id, data_d_minus_1)
    mec_sub_d0 = await _fetch_pl_sub_mec(db, fundo_id, data_d_zero)
    # Fallback p/ derivacao do balancete quando MEC ausente — usuario ve um
    # numero (em vez de zerado), mas a UI marca como nao-confiavel via
    # data_quality (passo 9). residuo nesse fallback fica matematicamente zero.
    pl_sub_d1 = mec_sub_d1 if mec_sub_d1 is not None else pl_total_d1 - sr_d1 - mez_d1
    pl_sub_d0 = mec_sub_d0 if mec_sub_d0 is not None else pl_total_d0 - sr_d0 - mez_d0
    delta_real = pl_sub_d0 - pl_sub_d1
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

    # 9. Data quality — detecta D-1/D0 com snapshot parcial (ETL incompleto)
    # OU MEC ausente em alguma das datas (impede reconciliacao independente).
    data_quality = _build_data_quality(
        rows_d1, rows_d0, data_d_minus_1, data_d_zero,
        mec_sub_d1=mec_sub_d1, mec_sub_d0=mec_sub_d0,
    )

    # 10. Rows papel-a-papel por conta analitica (drill na tabela)
    rows_por_cosif = _build_rows_diff_por_codigo(
        rows_d1, rows_d0, rules_cache, overrides
    )

    return BalanceteResponse(
        fundo_id=fundo_id,
        data_d_zero=data_d_zero,
        data_d_minus_1=data_d_minus_1,
        nodes=nodes,
        classe_breakdown_por_cosif=classe_breakdown,
        rows_por_cosif=rows_por_cosif,
        reconciliacao=reconciliacao,
        cobertura=cob,
        data_quality=data_quality,
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


def _build_rows_diff_por_codigo(
    rows_d1: list[_SilverRow],
    rows_d0: list[_SilverRow],
    rules_cache,
    overrides,
) -> dict[str, list[CosifRowDiff]]:
    """Diff papel-a-papel agrupado por cosif_codigo analitico.

    Para CADA conta analitica (folha COSIF que recebeu silver), monta a lista
    de papeis (silver rows) que sustentam o saldo, com status novo/removido/
    alterado/inalterado entre D-1 e D0. Mesma logica do `compute_cosif_rows()`
    mas processando todas as contas de uma vez — evita N+1 quando a UI quer
    drill em todas as folhas.

    Rows pendentes (res.cosif=None) sao ignoradas — bucket pendente nao tem
    composicao expandivel.
    """
    def _key(r: _SilverRow) -> tuple[str, str]:
        codigo = r.raw.get("codigo")
        if codigo:
            return (r.silver_origin, str(codigo))
        return (r.silver_origin, f"@{r.nome}")

    # cosif -> chave -> {"d1": SilverRow?, "d0": SilverRow?, "source": str}
    by_cosif: dict[str, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)

    for r in rows_d1:
        res = classify(r.silver_origin, r.raw, rules_cache, overrides)
        if res.cosif is None:
            continue
        key = _key(r)
        slot = by_cosif[res.cosif].setdefault(key, {})
        slot["d1"] = r
        slot["source"] = res.source

    for r in rows_d0:
        res = classify(r.silver_origin, r.raw, rules_cache, overrides)
        if res.cosif is None:
            continue
        key = _key(r)
        slot = by_cosif[res.cosif].setdefault(key, {})
        slot["d0"] = r
        slot["source"] = res.source  # D0 wins (papel "atual")

    out: dict[str, list[CosifRowDiff]] = {}
    for cosif, items in by_cosif.items():
        rows_out: list[CosifRowDiff] = []
        for _, slot in items.items():
            r_d1: _SilverRow | None = slot.get("d1")
            r_d0: _SilverRow | None = slot.get("d0")
            ref = r_d0 or r_d1
            if ref is None:
                continue

            valor_d1 = r_d1.valor if r_d1 else Decimal(0)
            valor_d0 = r_d0.valor if r_d0 else Decimal(0)
            delta = valor_d0 - valor_d1

            if r_d1 is None:
                status = "novo"
            elif r_d0 is None:
                status = "removido"
            elif delta == 0:
                status = "inalterado"
            else:
                status = "alterado"

            qtde_d1 = r_d1.raw.get("quantidade") if r_d1 else None
            qtde_d0 = r_d0.raw.get("quantidade") if r_d0 else None
            indexador = ref.raw.get("indexador")
            # Contraparte: campo varia por silver. emitente em renda fixa,
            # ativo_instituicao em cota_fundo. Demais silvers nao tem.
            contraparte = (
                ref.raw.get("emitente")
                or ref.raw.get("ativo_instituicao")
            )

            rows_out.append(CosifRowDiff(
                silver_origin=ref.silver_origin,
                codigo=ref.raw.get("codigo"),
                nome=ref.nome,
                valor_d_minus_1=valor_d1,
                valor_d_zero=valor_d0,
                delta=delta,
                quantidade_d_minus_1=(
                    Decimal(str(qtde_d1)) if qtde_d1 is not None else None
                ),
                quantidade_d_zero=(
                    Decimal(str(qtde_d0)) if qtde_d0 is not None else None
                ),
                indexador=indexador,
                cosif_source=slot["source"],
                status=status,
                contraparte=contraparte,
            ))

        rows_out.sort(key=lambda x: (abs(x.delta), abs(x.valor_d_zero)), reverse=True)
        out[cosif] = rows_out

    return out


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


# ─── Data quality ────────────────────────────────────────────────────────────


_SILVER_HUMAN_LABEL: dict[str, str] = {
    "wh_saldo_conta_corrente":    "conta corrente",
    "wh_saldo_tesouraria":        "tesouraria",
    "wh_posicao_compromissada":   "compromissadas",
    "wh_posicao_renda_fixa":      "renda fixa",
    "wh_posicao_cota_fundo":      "cotas de fundo",
    "wh_posicao_outros_ativos":   "outros ativos (PDD)",
    "wh_cpr_movimento":           "CPR",
}


def _build_data_quality(
    rows_d1: list[_SilverRow],
    rows_d0: list[_SilverRow],
    data_d_minus_1: date,
    data_d_zero: date,
    *,
    mec_sub_d1: Decimal | None = None,
    mec_sub_d0: Decimal | None = None,
) -> DataQuality:
    """Detecta snapshot parcial em D-1 ou D0 comparando presenca de silvers,
    e MEC ausente em alguma das datas (impede reconciliacao independente).

    Conta rows por silver_origin em ambos os dias. Marca como `divergente`
    qualquer silver que tem rows em um dia mas nao no outro — sintoma de
    ETL incompleto.

    Tambem checa se `wh_mec_evolucao_cotas` foi publicada para ambos os dias.
    Sem MEC, o `delta_pl_cota_sub_real` cai no fallback derivado do balancete
    (matematicamente identico ao Esperado) e a comparacao perde sentido.

    `comparable` = True quando NENHUM silver e divergente E MEC presente em
    ambos os dias. Robusto contra fundos que naturalmente nao tem
    `wh_saldo_tesouraria` ou `wh_posicao_compromissada`, por exemplo.
    """
    silvers_d1: dict[str, int] = {origin: 0 for origin in _QUERIES}
    silvers_d0: dict[str, int] = {origin: 0 for origin in _QUERIES}
    for r in rows_d1:
        silvers_d1[r.silver_origin] = silvers_d1.get(r.silver_origin, 0) + 1
    for r in rows_d0:
        silvers_d0[r.silver_origin] = silvers_d0.get(r.silver_origin, 0) + 1

    divergentes: list[str] = []
    for origin in _QUERIES:
        has_d1 = silvers_d1.get(origin, 0) > 0
        has_d0 = silvers_d0.get(origin, 0) > 0
        if has_d1 != has_d0:
            divergentes.append(origin)

    # MEC ausente vira "divergencia" sintetica — flagrado fora do dict de
    # silvers (que e exclusivo do balancete COSIF), mas merge no reason.
    mec_missing: list[date] = []
    if mec_sub_d1 is None:
        mec_missing.append(data_d_minus_1)
    if mec_sub_d0 is None:
        mec_missing.append(data_d_zero)

    if not divergentes and not mec_missing:
        return DataQuality(
            silvers_d1=silvers_d1,
            silvers_d0=silvers_d0,
            silvers_divergentes=[],
            comparable=True,
            reason=None,
        )

    motivos: list[str] = []

    if divergentes:
        # Determina qual dia esta parcial — o que tem menos silvers populados.
        populados_d1 = sum(1 for v in silvers_d1.values() if v > 0)
        populados_d0 = sum(1 for v in silvers_d0.values() if v > 0)
        dia_parcial = data_d_minus_1 if populados_d1 < populados_d0 else data_d_zero
        dia_label = "D-1" if dia_parcial == data_d_minus_1 else "D0"
        silvers_faltando_humanos = [
            _SILVER_HUMAN_LABEL.get(s, s) for s in divergentes
        ]
        motivos.append(
            f"{dia_label} ({dia_parcial.strftime('%d/%m/%Y')}) com snapshot parcial "
            f"— faltam dados de: {', '.join(silvers_faltando_humanos)}"
        )

    if mec_missing:
        datas_humanas = ", ".join(d.strftime("%d/%m/%Y") for d in mec_missing)
        motivos.append(
            f"MEC nao publicado para: {datas_humanas} — reconciliacao da "
            f"Cota Sub cai no fallback derivado do balancete (residuo zerado "
            f"por construcao)"
        )

    reason = ". ".join(motivos) + ". Comparacao pode estar distorcida."

    return DataQuality(
        silvers_d1=silvers_d1,
        silvers_d0=silvers_d0,
        silvers_divergentes=divergentes,
        comparable=False,
        reason=reason,
    )


# ─── Drill-down por conta COSIF ─────────────────────────────────────────────


async def compute_cosif_rows(
    db: AsyncSession,
    tenant_id: UUID,
    fundo_id: UUID,
    data_d_zero: date,
    cosif_codigo: str,
    data_d_minus_1: date | None = None,
) -> CosifRowsResponse:
    """Compara papeis (rows do silver) que sustentam uma conta COSIF entre D-1 e D0.

    Usado pelo `CosifDrillSheet`. Mescha composicao (foto em D0) com analise
    da variacao (movimento D-1 -> D0). Cada papel vira 1 row com status:
    novo / removido / alterado / inalterado.

    Aceita conta analitica (folha) ou sintetica (agrega descendentes).
    Resolve via cascata override -> rule do classifier — mesma logica do
    `compute_balancete_diario`. Se `data_d_minus_1` nao for passado, infere
    via `dia_util_anterior_qitech` (mesma fonte de verdade do Calendar).

    Multi-tenant: query do silver filtra por `unidade_administrativa_id`
    (= fundo_id); tenant_id reservado para futura validacao de subscription.
    """
    if data_d_minus_1 is None:
        data_d_minus_1 = await dia_util_anterior_qitech(
            db, tenant_id, fundo_id, data_d_zero
        )

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

    rows_d1 = await _fetch_silver(db, fundo_id, data_d_minus_1)
    rows_d0 = await _fetch_silver(db, fundo_id, data_d_zero)

    # Index por (silver_origin, codigo) filtrando so quem cai no cosif solicitado.
    # codigo None vira chave artificial baseada em nome para wh_cpr_movimento etc.
    def _key(r: _SilverRow) -> tuple[str, str]:
        codigo = r.raw.get("codigo")
        if codigo:
            return (r.silver_origin, str(codigo))
        # Sem codigo: usa nome como chave (caso de wh_cpr_movimento)
        return (r.silver_origin, f"@{r.nome}")

    d1_map: dict[tuple[str, str], _SilverRow] = {}
    d0_map: dict[tuple[str, str], _SilverRow] = {}
    for r in rows_d1:
        res = classify(r.silver_origin, r.raw, rules_cache, overrides)
        if res.cosif in accepted:
            d1_map[_key(r)] = r
    for r in rows_d0:
        res = classify(r.silver_origin, r.raw, rules_cache, overrides)
        if res.cosif in accepted:
            d0_map[_key(r)] = r

    all_keys = set(d1_map) | set(d0_map)
    out: list[CosifRowDiff] = []
    for key in all_keys:
        r_d1 = d1_map.get(key)
        r_d0 = d0_map.get(key)

        # Pega referencia (preferencia D0 — papel "atual"; fallback D-1 quando
        # o papel saiu da carteira).
        ref = r_d0 or r_d1
        if ref is None:
            continue  # impossivel, mas calma o type checker

        valor_d1 = r_d1.valor if r_d1 else Decimal(0)
        valor_d0 = r_d0.valor if r_d0 else Decimal(0)
        delta = valor_d0 - valor_d1

        if r_d1 is None:
            status = "novo"
        elif r_d0 is None:
            status = "removido"
        elif delta == 0:
            status = "inalterado"
        else:
            status = "alterado"

        qtde_d1 = r_d1.raw.get("quantidade") if r_d1 else None
        qtde_d0 = r_d0.raw.get("quantidade") if r_d0 else None
        indexador = (r_d0 or r_d1).raw.get("indexador") if (r_d0 or r_d1) else None
        contraparte = ref.raw.get("emitente") or ref.raw.get("ativo_instituicao")

        # cosif_source vem do D0 (papel atual); fallback D-1
        res = classify(ref.silver_origin, ref.raw, rules_cache, overrides)

        out.append(CosifRowDiff(
            silver_origin=ref.silver_origin,
            codigo=ref.raw.get("codigo"),
            nome=ref.nome,
            valor_d_minus_1=valor_d1,
            valor_d_zero=valor_d0,
            delta=delta,
            quantidade_d_minus_1=Decimal(str(qtde_d1)) if qtde_d1 is not None else None,
            quantidade_d_zero=Decimal(str(qtde_d0)) if qtde_d0 is not None else None,
            indexador=indexador,
            cosif_source=res.source,
            status=status,
            contraparte=contraparte,
        ))

    # Ordena: primeiro por |delta| desc (mais material movimento), depois por
    # |valor_d_zero| desc — papel grande sem variacao continua importante.
    out.sort(key=lambda x: (abs(x.delta), abs(x.valor_d_zero)), reverse=True)

    total_d1 = sum((r.valor_d_minus_1 for r in out), Decimal(0))
    total_d0 = sum((r.valor_d_zero for r in out), Decimal(0))
    total_delta = total_d0 - total_d1

    return CosifRowsResponse(
        fundo_id=fundo_id,
        data_d_zero=data_d_zero,
        data_d_minus_1=data_d_minus_1,
        cosif_codigo=cosif_codigo,
        cosif_nome=info.nome,
        total_valor_d_minus_1=total_d1,
        total_valor_d_zero=total_d0,
        total_delta=total_delta,
        rows=out,
    )
