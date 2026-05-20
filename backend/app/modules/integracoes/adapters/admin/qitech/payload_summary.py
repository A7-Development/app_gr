"""QiTech raw payload — summarizer (visualization-grade).

Sibling module to `completeness.py`. Onde aquele devolve um veredito
binario (`complete | partial | empty`), este devolve um **sumario
estruturado** dos itens detectados no payload para o usuario julgar
qualidade no tooltip do `QiTechCoverageStrip` no frontend (memoria
`project_qitech_response_semantics.md`, caso 2026-05-19).

Caso motivador: em 2026-05-19 a QiTech publicou `market.mec` com a
carteira Subordinada `patrimonio=0`, `variacaoDiaria=-100` enquanto as
outras duas carteiras vieram normais. O `_assess_mec` aceitou como
`complete` porque as 3 chaves de carteira existiam; a UI rendeu numero
absurdo (Sub "desapareceu") sem aviso. Este modulo expoe a lista das
3 carteiras com flag visual em quem zerou — usuario decide se forca
sync ou ignora.

Filosofia: NAO escala `completeness` automaticamente (decisao 2026-05-20
com Ricardo — opcao "so visualizar"). Quando heuristica de sentinela
bate, marcamos `ItemSummary.suspicious=True` mas o veredicto continua
sendo o que `assess_completeness` decidiu. Escalar partial automatico
fica em `[[project_qitech_partial_refetch]]` Fase B.

Convencao do summary:
- `total_items`: tamanho do array no payload (`relatórios.<tipo>`).
- `expected_items`: quando ha numero conhecido (3 para MEC). `None`
  para tipos sem expectativa fixa.
- `items`: top N (cap em 10) ordenados por `value` desc. Quando
  `total_items > 10`, o frontend infere "+N mais" do delta.
- `suspicious_count`: quantos `items` retornados tem flag.

Para endpoints CSV (`fidc-estoque`, `fidc-custodia/*`) o payload e
metadata do report file (`bytes`, `rows_estimate`, `qitech_job_id`),
nao array. Retornamos summary com `total_items=rows_estimate or 0` e
sem `items`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.integracoes.adapters.admin.qitech.completeness import (
    _cliente_id_principal,
    _is_mezanino_name,
    _is_senior_name,
    _is_sub_jr_name,
    _norm,
)

# Numero maximo de items listados no tooltip — alem disso, frontend
# pode inferir "+N mais" via (total_items - len(items)). Mantemos
# baixo (10) porque o popover do strip e estreito (w-72 = 288px).
_MAX_ITEMS_IN_SUMMARY = 10


@dataclass(frozen=True)
class ItemSummary:
    """Uma linha do sumario (carteira, papel, conta, movimento, etc).

    Generico o suficiente para servir todos os tipos. `value` e `delta_pct`
    sao opcionais — nem todo tipo tem ambos (cpr tem valor mas nao tem
    variacao; mec tem ambos; outros-fundos tem valor mas variacao seria
    sintetica). UI esconde campos None.
    """

    name: str
    value: Decimal | None
    delta_pct: Decimal | None
    suspicious: bool
    suspicious_reason: str | None


@dataclass(frozen=True)
class PayloadSummary:
    """Sumario do payload de um raw QiTech para visualizacao no tooltip."""

    total_items: int
    expected_items: int | None
    suspicious_count: int
    items: list[ItemSummary]


# ─── Helpers ────────────────────────────────────────────────────────────────


def _items(payload: Any, key: str) -> list[dict[str, Any]]:
    """Extrai `payload['relatórios'][key]` tolerando shape ausente."""
    if not isinstance(payload, dict):
        return []
    relatorios = payload.get("relatórios")
    if not isinstance(relatorios, dict):
        return []
    items = relatorios.get(key)
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


def _to_decimal(v: Any) -> Decimal | None:
    """Coerce para Decimal tolerando None/str/float — devolve None se invalido."""
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _truncate(items: list[ItemSummary]) -> list[ItemSummary]:
    """Top N por value desc; items com value=None vao pro final (estavel)."""

    def _sort_key(it: ItemSummary) -> tuple[int, Decimal]:
        # 0 = tem valor; 1 = sem valor (vai pro final). Negativo no abs
        # garante maior valor primeiro.
        if it.value is None:
            return (1, Decimal(0))
        return (0, -abs(it.value))

    return sorted(items, key=_sort_key)[:_MAX_ITEMS_IN_SUMMARY]


def _make_summary(
    *,
    total_items: int,
    expected_items: int | None,
    items: list[ItemSummary],
) -> PayloadSummary:
    truncated = _truncate(items)
    return PayloadSummary(
        total_items=total_items,
        expected_items=expected_items,
        suspicious_count=sum(1 for it in items if it.suspicious),
        items=truncated,
    )


# ─── Summarizers por tipo ───────────────────────────────────────────────────


def _summarize_mec(
    payload: dict[str, Any] | None, ua_nome: str
) -> PayloadSummary:
    """MEC — 3 carteiras esperadas (Sub/Mez/Sen). Sentinela: patrimonio<=0
    AND variacaoDiaria<=-50 (Sub publicada com classe zerada — caso 2026-05-19)."""
    raw_items = _items(payload, "mec")
    items: list[ItemSummary] = []
    for it in raw_items:
        nome = str(it.get("clienteNome") or "")
        patrimonio = _to_decimal(it.get("patrimonio"))
        var_diaria = _to_decimal(it.get("variaçãoDiaria"))

        # Detecta classe (so para enriquecer label, nao influencia suspicious).
        label = nome
        if _is_sub_jr_name(nome, ua_nome):
            label = f"{nome} (Sub)"
        elif _is_mezanino_name(nome):
            label = f"{nome} (Mez)"
        elif _is_senior_name(nome):
            label = f"{nome} (Sen)"

        suspicious = False
        reason: str | None = None
        if (
            patrimonio is not None
            and patrimonio <= 0
            and var_diaria is not None
            and var_diaria <= Decimal("-50")
        ):
            suspicious = True
            reason = "Patrimonio zerado com queda >50% — provavel publicacao parcial"

        items.append(
            ItemSummary(
                name=label,
                value=patrimonio,
                delta_pct=var_diaria,
                suspicious=suspicious,
                suspicious_reason=reason,
            )
        )

    return _make_summary(
        total_items=len(raw_items),
        expected_items=3,
        items=items,
    )


def _summarize_tesouraria(
    payload: dict[str, Any] | None, ua_nome: str
) -> PayloadSummary:
    """Tesouraria — 1 linha por carteira (Sub/Mez/Sen em FIDCs multiclasse).
    Sentinela: ausencia da carteira Subordinada (clienteNome casando com
    ua_nome cru — caso 2026-05-19 com tesouraria de 2 items em vez de 3)."""
    raw_items = _items(payload, "tesouraria")
    items: list[ItemSummary] = []
    for it in raw_items:
        nome = str(it.get("clienteNome") or "")
        valor = _to_decimal(it.get("valor"))
        label = nome
        if _is_sub_jr_name(nome, ua_nome):
            label = f"{nome} (Sub)"
        elif _is_mezanino_name(nome):
            label = f"{nome} (Mez)"
        elif _is_senior_name(nome):
            label = f"{nome} (Sen)"
        items.append(
            ItemSummary(
                name=label,
                value=valor,
                delta_pct=None,
                suspicious=False,
                suspicious_reason=None,
            )
        )

    # Flag agregada: a Sub deveria estar presente; quando o conjunto detectado
    # nao inclui ninguem casando com ua_nome cru, marcamos um pseudo-item
    # "Sub: ausente" como suspicious para o tooltip nao deixar passar batido.
    has_sub = any(
        _is_sub_jr_name(str(it.get("clienteNome") or ""), ua_nome)
        for it in raw_items
    )
    if raw_items and not has_sub:
        items.append(
            ItemSummary(
                name=f"{ua_nome} (Sub)",
                value=None,
                delta_pct=None,
                suspicious=True,
                suspicious_reason=(
                    "Carteira Subordinada ausente neste relatorio — "
                    "provavel publicacao parcial"
                ),
            )
        )

    expected = 3 if raw_items else None
    return _make_summary(
        total_items=len(raw_items),
        expected_items=expected,
        items=items,
    )


def _summarize_conta_corrente(
    payload: dict[str, Any] | None, ua_nome: str
) -> PayloadSummary:
    del ua_nome
    raw_items = _items(payload, "conta-corrente")
    items = [
        ItemSummary(
            name=str(it.get("descrição") or it.get("código") or "—"),
            value=_to_decimal(it.get("valorTotal")),
            delta_pct=None,
            suspicious=False,
            suspicious_reason=None,
        )
        for it in raw_items
    ]
    return _make_summary(
        total_items=len(raw_items),
        expected_items=None,
        items=items,
    )


def _summarize_rf(
    payload: dict[str, Any] | None, ua_nome: str
) -> PayloadSummary:
    """RF — N papeis. Sentinela agregada: nenhum item casando com clienteId
    principal da UA (caso 2026-04-30 / 12-05 — publicacao parcial sem o
    fundo principal)."""
    raw_items = _items(payload, "rf")
    items = [
        ItemSummary(
            name=str(it.get("nomeDoPapel") or it.get("código") or "—"),
            value=_to_decimal(it.get("valorBruto")),
            delta_pct=None,
            suspicious=False,
            suspicious_reason=None,
        )
        for it in raw_items
    ]
    # Pseudo-item de aviso quando nenhum papel casou com o fundo principal.
    principal = _cliente_id_principal(ua_nome)
    has_principal = any(
        _norm(it.get("clienteId") or "") == principal for it in raw_items
    )
    if raw_items and not has_principal:
        items.append(
            ItemSummary(
                name=f"{principal} (papeis principais)",
                value=None,
                delta_pct=None,
                suspicious=True,
                suspicious_reason=(
                    "Nenhum papel casando com o fundo principal — "
                    "provavel publicacao parcial"
                ),
            )
        )
    return _make_summary(
        total_items=len(raw_items),
        expected_items=None,
        items=items,
    )


def _summarize_rf_compromissadas(
    payload: dict[str, Any] | None, ua_nome: str
) -> PayloadSummary:
    del ua_nome
    raw_items = _items(payload, "rf-compromissadas")
    items = [
        ItemSummary(
            name=str(it.get("nomeDoPapel") or it.get("código") or "—"),
            value=_to_decimal(it.get("valorBruto")),
            delta_pct=None,
            suspicious=False,
            suspicious_reason=None,
        )
        for it in raw_items
    ]
    return _make_summary(
        total_items=len(raw_items),
        expected_items=None,
        items=items,
    )


def _summarize_outros_fundos(
    payload: dict[str, Any] | None, ua_nome: str
) -> PayloadSummary:
    del ua_nome
    raw_items = _items(payload, "outros-fundos")
    items = [
        ItemSummary(
            name=str(it.get("fundo") or it.get("código") or "—"),
            value=_to_decimal(it.get("valorAtual")),
            delta_pct=None,
            suspicious=False,
            suspicious_reason=None,
        )
        for it in raw_items
    ]
    return _make_summary(
        total_items=len(raw_items),
        expected_items=None,
        items=items,
    )


def _summarize_outros_ativos(
    payload: dict[str, Any] | None, ua_nome: str
) -> PayloadSummary:
    del ua_nome
    raw_items = _items(payload, "outros-ativos")
    items = [
        ItemSummary(
            name=str(it.get("descrição") or it.get("código") or "—"),
            value=_to_decimal(it.get("valorTotal")),
            delta_pct=None,
            suspicious=False,
            suspicious_reason=None,
        )
        for it in raw_items
    ]
    return _make_summary(
        total_items=len(raw_items),
        expected_items=None,
        items=items,
    )


def _summarize_cpr(
    payload: dict[str, Any] | None, ua_nome: str
) -> PayloadSummary:
    del ua_nome
    raw_items = _items(payload, "cpr")
    items = [
        ItemSummary(
            name=str(it.get("descrição") or "—"),
            value=_to_decimal(it.get("valor")),
            delta_pct=None,
            suspicious=False,
            suspicious_reason=None,
        )
        for it in raw_items
    ]
    return _make_summary(
        total_items=len(raw_items),
        expected_items=None,
        items=items,
    )


def _summarize_csv_report(
    payload: dict[str, Any] | None, ua_nome: str
) -> PayloadSummary:
    """Para endpoints CSV (fidc-estoque, fidc-custodia/*): payload e metadata
    do report file, nao array. Sumario expoe `rows_estimate` como total_items
    e renderiza 1-2 items "informativos" (bytes + job_id) para o tooltip."""
    del ua_nome
    if not isinstance(payload, dict):
        return _make_summary(total_items=0, expected_items=None, items=[])
    rows_estimate = payload.get("rows_estimate")
    bytes_ = payload.get("bytes")
    job_id = payload.get("qitech_job_id")

    items: list[ItemSummary] = []
    if isinstance(bytes_, int) and bytes_ >= 0:
        # Mostra como item "informativo" — value=bytes (em bytes mesmo,
        # frontend pode formatar como KB/MB), sem flag.
        items.append(
            ItemSummary(
                name="Tamanho do arquivo (bytes)",
                value=Decimal(bytes_),
                delta_pct=None,
                suspicious=False,
                suspicious_reason=None,
            )
        )
    if isinstance(job_id, str) and job_id:
        items.append(
            ItemSummary(
                name=f"Job QiTech: {job_id[:8]}…",
                value=None,
                delta_pct=None,
                suspicious=False,
                suspicious_reason=None,
            )
        )

    total = rows_estimate if isinstance(rows_estimate, int) else 0
    return _make_summary(
        total_items=total,
        expected_items=None,
        items=items,
    )


# Map tipo_de_mercado -> summarizer. Tipos ausentes do mapa caem no
# `_default_summarize` (so conta itens, sem semantica).
_SUMMARIZERS = {
    "mec": _summarize_mec,
    "tesouraria": _summarize_tesouraria,
    "conta-corrente": _summarize_conta_corrente,
    "rf": _summarize_rf,
    "rf-compromissadas": _summarize_rf_compromissadas,
    "outros-fundos": _summarize_outros_fundos,
    "outros-ativos": _summarize_outros_ativos,
    "cpr": _summarize_cpr,
    "fidc-estoque": _summarize_csv_report,
    "fidc-custodia/aquisicao-consolidada": _summarize_csv_report,
    "fidc-custodia/liquidados-baixados": _summarize_csv_report,
    "fidc-custodia/movimento-aberto": _summarize_csv_report,
    "fidc-custodia/detalhes-operacoes": _summarize_csv_report,
}


def _default_summarize(
    payload: dict[str, Any] | None, ua_nome: str
) -> PayloadSummary:
    """Sem perfil especifico: conta total de items na primeira lista
    encontrada em `relatórios.<algo>` e devolve sem items. Frontend trata
    como "tipo sem detalhe" e nao mostra o bloco de lista."""
    del ua_nome
    if not isinstance(payload, dict):
        return _make_summary(total_items=0, expected_items=None, items=[])
    relatorios = payload.get("relatórios")
    if not isinstance(relatorios, dict):
        return _make_summary(total_items=0, expected_items=None, items=[])
    for v in relatorios.values():
        if isinstance(v, list):
            return _make_summary(
                total_items=len(v),
                expected_items=None,
                items=[],
            )
    return _make_summary(total_items=0, expected_items=None, items=[])


def summarize_payload(
    *,
    tipo_de_mercado: str,
    payload: dict[str, Any] | None,
    ua_nome: str | None,
    http_status: int | None,
) -> PayloadSummary | None:
    """Sumariza o payload bruto em `PayloadSummary` para visualizacao.

    Args:
        tipo_de_mercado: chave canonica do raw (ex.: 'mec', 'rf').
        payload: body JSON cru da QiTech (pode ser None ou metadata CSV).
        ua_nome: nome cru da UA (ex.: 'REALINVEST FIDC') quando relevante
            para classificar carteiras Sub/Mez/Sen. Opcional.
        http_status: status HTTP do fetch. != 200 → retornamos None
            (nao ha payload util para sumarizar; UI ja sinaliza falha
            via o `status` do dia).

    Returns:
        `PayloadSummary` ou `None` quando o fetch nao trouxe payload
        utilizavel (http != 200, payload corrompido, etc).
    """
    if http_status is not None and http_status != 200:
        return None
    summarizer = _SUMMARIZERS.get(tipo_de_mercado, _default_summarize)
    return summarizer(payload, ua_nome or "")
