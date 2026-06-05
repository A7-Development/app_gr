"""Deterministic analytics over a homologated revenue declaration.

Pure functions — no DB, no LLM, no network. They take the homologated
monthly revenue series (the analyst-approved extraction) and produce the
auditable analytical pack the `revenue_analyst` agent reasons over:
trend, seasonality, peaks/valleys (outliers), year-over-year, data
quality, plus the document-level attestation signals (signed? recent?
issuer matches?).

Design (CLAUDE.md §14, esteira de credito): the AGENT does not compute
numbers — it reads these deterministic facts and judges which ones draw
attention (expected vs anomalous). Keeping the math here keeps every
number CVM-auditable and reusable (the read-tool, the future canonical
silver materialization, and the UI can all share it).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

# Outlier régua — mesma da camada de checks de sanidade do DocumentWorkspace
# (frontend), pra o número na tela bater com o número que o agente recebe.
_OUTLIER_HIGH = 2.5  # > 2.5x a média mensal
_OUTLIER_LOW = 0.4   # < 0.4x a média mensal

# Sazonalidade só é estatisticamente separável da tendência com >= 2 ciclos
# anuais. Abaixo disso reportamos "perfil mensal" e marcamos confiavel=False.
_SEASONALITY_MIN_MONTHS = 24

# Picos/vales de perfil mensal (relativo à média) — bandas informativas.
_PROFILE_HIGH = 1.20  # 20% acima da média
_PROFILE_LOW = 0.80   # 20% abaixo da média

# Documento "recente" — declaração mais velha que isto começa a defasar.
# Sinal informativo (o agente pondera), não regra dura.
_RECENTE_MAX_MESES = 6

# Tolerância da reconciliação soma-dos-meses vs total declarado.
_SOMA_TOL_BRL = 0.01


@dataclass(frozen=True)
class MonthPoint:
    """Um ponto homologado da série (mês competência + receita bruta)."""

    mes: str  # "YYYY-MM"
    receita_bruta: float


@dataclass(frozen=True)
class RevenueAnalytics:
    """Pacote analítico determinístico sobre a série de faturamento."""

    serie: list[dict[str, Any]]
    agregados: dict[str, Any]
    tendencia: dict[str, Any]
    sazonalidade: dict[str, Any]
    outliers: list[dict[str, Any]]
    yoy: dict[str, Any] | None
    qualidade: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Parsing / normalização ──────────────────────────────────────────────


def _parse_series(monthly: Any) -> list[MonthPoint]:
    """Normaliza `extracted_fields.monthly` -> série ordenada por competência.

    Aceita o shape `[{"month": "YYYY-MM", "value": <num>}]` (extração) e
    descarta linhas sem mês válido. Ordena cronologicamente.
    """
    if not isinstance(monthly, list):
        return []
    out: list[MonthPoint] = []
    for row in monthly:
        if not isinstance(row, dict):
            continue
        mes = str(row.get("month") or row.get("mes") or "").strip()
        if not _is_year_month(mes):
            continue
        raw_val = row.get("value", row.get("receita_bruta", 0))
        try:
            val = float(raw_val)
        except (TypeError, ValueError):
            val = 0.0
        out.append(MonthPoint(mes=mes, receita_bruta=val))
    out.sort(key=lambda p: p.mes)
    return out


def _is_year_month(s: str) -> bool:
    if len(s) != 7 or s[4] != "-":
        return False
    y, m = s[:4], s[5:]
    return y.isdigit() and m.isdigit() and 1 <= int(m) <= 12


def _month_index(mes: str) -> int:
    """'YYYY-MM' -> índice absoluto de mês (year*12 + month-1), p/ detectar gaps.

    Base-0 no mês (jan=0) pra o decode ser exato: year=idx//12, month=idx%12+1.
    """
    return int(mes[:4]) * 12 + (int(mes[5:]) - 1)


def _round2(n: float) -> float:
    return round(n + 0.0, 2)


# ─── Cálculos determinísticos ────────────────────────────────────────────


def _aggregates(points: list[MonthPoint]) -> dict[str, Any]:
    values = [p.receita_bruta for p in points]
    total = sum(values)
    media = total / len(points) if points else 0.0
    maior = max(points, key=lambda p: p.receita_bruta)
    menor = min(points, key=lambda p: p.receita_bruta)
    return {
        "total": _round2(total),
        "media": _round2(media),
        "mes_maior": {"mes": maior.mes, "valor": _round2(maior.receita_bruta)},
        "mes_menor": {"mes": menor.mes, "valor": _round2(menor.receita_bruta)},
        "n_meses": len(points),
    }


def _linear_fit(values: list[float]) -> tuple[float, float]:
    """Mínimos quadrados sobre x=0..n-1. Retorna (slope, intercept)."""
    n = len(values)
    if n < 2:
        return 0.0, (values[0] if values else 0.0)
    xs = range(n)
    sx = sum(xs)
    sy = sum(values)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, values, strict=True))
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0, sy / n
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return slope, intercept


def _trend(points: list[MonthPoint], media: float) -> dict[str, Any]:
    values = [p.receita_bruta for p in points]
    slope, _intercept = _linear_fit(values)
    n = len(values)
    # Variação total implícita pela reta, relativa à média — robusto a escala.
    variacao_total_rel = (slope * (n - 1) / media) if media else 0.0
    if variacao_total_rel > 0.10:
        direcao = "crescente"
    elif variacao_total_rel < -0.10:
        direcao = "decrescente"
    else:
        direcao = "estavel"
    mag = abs(variacao_total_rel)
    intensidade = "forte" if mag >= 0.30 else "moderada" if mag >= 0.10 else "leve"
    return {
        "direcao": direcao,
        "intensidade": intensidade,
        "slope_mensal": _round2(slope),
        "variacao_periodo_pct": _round2(variacao_total_rel * 100),
        # Crescimento anualizado aproximado (slope*12 como % da média).
        "crescimento_anualizado_pct": _round2((slope * 12 / media * 100) if media else 0.0),
    }


def _seasonality(points: list[MonthPoint], media: float) -> dict[str, Any]:
    """Perfil mensal relativo à média + picos/vales.

    Com < 24 meses não há ciclos suficientes pra separar sazonalidade de
    tendência — reportamos o perfil mês-a-mês (value/média) e marcamos
    `confiavel=False` pra o agente saber que é leitura fraca.
    """
    confiavel = len(points) >= _SEASONALITY_MIN_MONTHS
    perfil: list[dict[str, Any]] = []
    picos: list[str] = []
    vales: list[str] = []
    for p in points:
        indice = (p.receita_bruta / media) if media else 0.0
        perfil.append({"mes": p.mes, "indice": _round2(indice)})
        if indice >= _PROFILE_HIGH:
            picos.append(p.mes)
        elif indice <= _PROFILE_LOW:
            vales.append(p.mes)
    return {
        "confiavel": confiavel,
        "nota": (
            "Série com >= 24 meses — sazonalidade separável da tendência."
            if confiavel
            else "Série curta (< 24 meses) — perfil mensal relativo à média, "
            "não sazonalidade confirmada."
        ),
        "perfil_mensal": perfil,
        "picos": picos,
        "vales": vales,
    }


def _outliers(points: list[MonthPoint], media: float) -> list[dict[str, Any]]:
    if media <= 0:
        return []
    out: list[dict[str, Any]] = []
    for p in points:
        ratio = p.receita_bruta / media
        if ratio >= _OUTLIER_HIGH or ratio <= _OUTLIER_LOW:
            out.append(
                {
                    "mes": p.mes,
                    "valor": _round2(p.receita_bruta),
                    "x_media": _round2(ratio),
                    "tipo": "pico" if ratio >= _OUTLIER_HIGH else "vale",
                }
            )
    return out


def _yoy(points: list[MonthPoint]) -> dict[str, Any] | None:
    """Year-over-year por mês-calendário, quando há 2 anos do mesmo mês."""
    by_cal: dict[str, list[MonthPoint]] = {}
    for p in points:
        by_cal.setdefault(p.mes[5:], []).append(p)
    deltas: list[dict[str, Any]] = []
    for cal_month, pts in by_cal.items():
        if len(pts) < 2:
            continue
        pts_sorted = sorted(pts, key=lambda p: p.mes)
        earlier, later = pts_sorted[0], pts_sorted[-1]
        if earlier.receita_bruta <= 0:
            continue
        var = later.receita_bruta / earlier.receita_bruta - 1.0
        deltas.append(
            {
                "mes_calendario": cal_month,
                "de": earlier.mes,
                "para": later.mes,
                "variacao_pct": _round2(var * 100),
            }
        )
    if not deltas:
        return None
    media_yoy = sum(d["variacao_pct"] for d in deltas) / len(deltas)
    return {"por_mes": deltas, "media_pct": _round2(media_yoy)}


def _qualidade(points: list[MonthPoint], declared_total: float | None) -> dict[str, Any]:
    soma = sum(p.receita_bruta for p in points)
    soma_confere = (
        declared_total is None or abs(soma - declared_total) < _SOMA_TOL_BRL
    )
    # Gaps na sequência de competências entre o primeiro e o último mês.
    meses_faltantes: list[str] = []
    if len(points) >= 2:
        idx_present = {_month_index(p.mes) for p in points}
        start, end = _month_index(points[0].mes), _month_index(points[-1].mes)
        for idx in range(start, end + 1):
            if idx not in idx_present:
                meses_faltantes.append(f"{idx // 12:04d}-{idx % 12 + 1:02d}")
    meses_zerados = [p.mes for p in points if p.receita_bruta <= 0]
    return {
        "n_meses": len(points),
        "soma_meses": _round2(soma),
        "total_declarado": (_round2(declared_total) if declared_total is not None else None),
        "soma_confere": soma_confere,
        "meses_faltantes": meses_faltantes,
        "meses_zerados": meses_zerados,
    }


def analyze_revenue_series(
    monthly: Any,
    *,
    declared_total: float | None = None,
) -> RevenueAnalytics:
    """Computa o pacote analítico determinístico da série de faturamento.

    Args:
        monthly: `extracted_fields.monthly` homologado —
            `[{"month": "YYYY-MM", "value": <num>}, ...]`.
        declared_total: total declarado (`extracted_fields.revenue`) para
            reconciliar com a soma dos meses. None = não reconcilia.

    Returns:
        `RevenueAnalytics` com série, agregados, tendência, sazonalidade,
        outliers, yoy (ou None) e qualidade. Série vazia -> pacote vazio
        coerente (o agente vê "sem dados").
    """
    points = _parse_series(monthly)
    if not points:
        return RevenueAnalytics(
            serie=[],
            agregados={"total": 0.0, "media": 0.0, "n_meses": 0},
            tendencia={"direcao": "indefinida", "intensidade": "indefinida"},
            sazonalidade={"confiavel": False, "perfil_mensal": [], "picos": [], "vales": []},
            outliers=[],
            yoy=None,
            qualidade={
                "n_meses": 0,
                "soma_meses": 0.0,
                "total_declarado": (
                    _round2(declared_total) if declared_total is not None else None
                ),
                "soma_confere": declared_total is None,
                "meses_faltantes": [],
                "meses_zerados": [],
            },
        )

    agregados = _aggregates(points)
    media = agregados["media"]
    return RevenueAnalytics(
        serie=[{"mes": p.mes, "receita_bruta": _round2(p.receita_bruta)} for p in points],
        agregados=agregados,
        tendencia=_trend(points, media),
        sazonalidade=_seasonality(points, media),
        outliers=_outliers(points, media),
        yoy=_yoy(points),
        qualidade=_qualidade(points, declared_total),
    )


# ─── Sinais de atestação (document-level) ────────────────────────────────


def _digits(s: Any) -> str:
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def _months_between(d1: date, d2: date) -> int:
    """Meses cheios de d1 até d2 (>= 0 quando d2 >= d1)."""
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def attestation_signals(
    documento: Any,
    *,
    target_cnpj: str | None,
    ref_date: date,
) -> dict[str, Any]:
    """Surfa os sinais determinísticos de atestação do documento.

    NÃO julga — só expõe os fatos pro agente ponderar (assinado? recente?
    emitente confere?). `documento` é o bloco `extracted_fields.documento`
    produzido pela extração enriquecida (data, emitente, assinado,
    signatarios, observacoes...). Ausente/parcial -> campos None/False
    (conservador).
    """
    doc = documento if isinstance(documento, dict) else {}

    assinado = bool(doc.get("assinado"))
    signatarios = doc.get("signatarios")
    signatarios = signatarios if isinstance(signatarios, list) else []
    observacoes = doc.get("observacoes")
    observacoes = [str(o) for o in observacoes] if isinstance(observacoes, list) else []

    # Idade do documento a partir de data_documento (ISO "YYYY-MM-DD...").
    idade_meses: int | None = None
    recente: bool | None = None
    data_doc_raw = str(doc.get("data_documento") or "").strip()
    if len(data_doc_raw) >= 10 and data_doc_raw[4] == "-" and data_doc_raw[7] == "-":
        try:
            d = date.fromisoformat(data_doc_raw[:10])
            idade_meses = max(0, _months_between(d, ref_date))
            recente = idade_meses <= _RECENTE_MAX_MESES
        except ValueError:
            idade_meses = None

    # Emitente confere com o alvo? Só decide quando há CNPJ do emitente.
    emitente = doc.get("emitente") if isinstance(doc.get("emitente"), dict) else {}
    emitente_cnpj = _digits(emitente.get("cnpj"))
    alvo_cnpj = _digits(target_cnpj)
    if emitente_cnpj and alvo_cnpj:
        emitente_confere: bool | None = emitente_cnpj == alvo_cnpj
    else:
        emitente_confere = None

    return {
        "data_documento": data_doc_raw or None,
        "idade_meses": idade_meses,
        "recente": recente,
        "assinado": assinado,
        "signatarios": signatarios,
        "qtd_signatarios": len(signatarios),
        "emitente": {
            "nome": emitente.get("nome"),
            "cnpj": emitente_cnpj or None,
            "tipo": emitente.get("tipo"),
        },
        "emitente_confere": emitente_confere,
        "observacoes": observacoes,
        "tem_ressalva": len(observacoes) > 0,
        "papel_timbrado": doc.get("papel_timbrado"),
    }
