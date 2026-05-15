"""Publication tolerance state — classifies how late a missing endpoint is.

Camada paralela ao `CoverageStatus` em `services/coverage.py`. Enquanto o
CoverageStatus responde "que tipo de evento aconteceu nesse dia?" (OK /
PARTIAL / NOT_PUBLISHED / GAP / PENDING / WEEKEND / HOLIDAY / ...), o
`PublicationState` responde "quao atrasado esta esse dia em relacao ao
SLA esperado?".

Os dois sao ortogonais:

- OK / PARTIAL / WEEKEND / HOLIDAY / BEFORE_FIRST_SYNC / UNSUPPORTED →
  `PublicationState` nao se aplica (None na resposta).
- GAP / NOT_PUBLISHED / PENDING → `PublicationState` classifica em
  ESPERADO / ATRASADO / SUSPEITO / FURO_DEFINITIVO em funcao de quantos
  dias uteis ANBIMA se passaram entre a data de referencia e hoje, e dos
  limites configurados no `EndpointSpec` (ou override do tenant em
  `TenantSourceEndpointConfig`).

Estados:
    ESPERADO        — business_days_since_reference <= expected_lag
                      (ainda dentro do SLA, sem alarde)
    ATRASADO        — expected_lag < days <= tolerance
                      (atrasado mas ainda no aceitavel — operador nao precisa
                      agir; reconciler tenta com mais frequencia)
    SUSPEITO        — tolerance < days <= give_up
                      (provavel problema — destaque na UI, reconciler tenta
                      menos frequente, alerta operacional)
    FURO_DEFINITIVO — days > give_up
                      (operador decide se quer reabrir; reconciler nao
                      tenta mais sozinho)

Funcao pura sem dependencia de DB. Recebe valores ja resolvidos
(`expected`/`tolerance`/`give_up` efetivos = override ou catalog default).
Caller faz a resolucao.

Conta de dias uteis: usa calendario ANBIMA (`wh_dim_dia_util`). Caller
passa o conjunto de datas uteis disponiveis para o range — funcao apenas
conta quantos dias uteis ha estritamente entre `reference_date` (exclusivo)
e `today` (exclusivo). Mantem o service puro/testavel sem tocar no banco.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class PublicationState(StrEnum):
    ESPERADO = "esperado"
    ATRASADO = "atrasado"
    SUSPEITO = "suspeito"
    FURO_DEFINITIVO = "furo_definitivo"


@dataclass(frozen=True)
class ToleranceWindow:
    """Janela efetiva de tolerancia para um endpoint+tenant.

    Resultado da composicao override-do-tenant + default-do-catalogo. Sempre
    completa (zero NULL apos resolucao) — invariante a ser respeitada pelo
    caller.
    """

    expected_lag_business_days: int
    tolerance_business_days: int
    give_up_business_days: int

    def __post_init__(self) -> None:
        if self.expected_lag_business_days < 0:
            raise ValueError(
                f"expected_lag must be >= 0, got {self.expected_lag_business_days}"
            )
        if self.tolerance_business_days < self.expected_lag_business_days:
            raise ValueError(
                f"tolerance ({self.tolerance_business_days}) < expected "
                f"({self.expected_lag_business_days})"
            )
        if self.give_up_business_days < self.tolerance_business_days:
            raise ValueError(
                f"give_up ({self.give_up_business_days}) < tolerance "
                f"({self.tolerance_business_days})"
            )


def resolve_tolerance_window(
    *,
    expected_lag_override: int | None,
    tolerance_override: int | None,
    give_up_override: int | None,
    default_expected_lag: int,
    default_tolerance: int,
    default_give_up: int,
) -> ToleranceWindow:
    """Combina override do tenant + default do catalogo, campo a campo.

    NULL em qualquer override = "segue default daquele campo". Combinacao
    mista e legitima (ex.: tenant customiza so `give_up`, herda `expected` e
    `tolerance` do catalogo).

    Re-valida a monotonicidade do resultado final — a combinacao mista pode
    em tese violar (ex.: override de tolerance=5 com default give_up=3). Se
    invariante quebra, levanta ValueError; caller responde com 400 para a
    API que tentou salvar a combinacao.
    """
    return ToleranceWindow(
        expected_lag_business_days=(
            expected_lag_override
            if expected_lag_override is not None
            else default_expected_lag
        ),
        tolerance_business_days=(
            tolerance_override
            if tolerance_override is not None
            else default_tolerance
        ),
        give_up_business_days=(
            give_up_override
            if give_up_override is not None
            else default_give_up
        ),
    )


def count_business_days_between(
    *,
    reference_date: date,
    today: date,
    business_days_set: frozenset[date],
) -> int:
    """Conta dias uteis ANBIMA estritamente entre reference_date e today.

    Convencao: a contagem nao inclui `reference_date` nem `today`. Reflete a
    semantica "publicado em D+N dias uteis APOS a data de referencia". Se o
    relatorio refere-se ao dia 14 e estamos no dia 15 e ambos sao uteis,
    business_days_since = 1 (dia 15 conta como 1 dia util passado).

    Esse modelo combina bem com expected_lag=0 (mesmo dia) e expected_lag=1
    (D+1 util).

    Args:
        reference_date: data de referencia do relatorio.
        today: data corrente.
        business_days_set: conjunto de datas uteis ANBIMA no range. Caller
            carrega de `wh_dim_dia_util` antes de chamar (mantem essa
            funcao pura).

    Returns:
        Quantidade de dias uteis estritamente entre reference_date e today.
        Zero se today <= reference_date. Nunca negativo.
    """
    if today <= reference_date:
        return 0
    # Conta uteis em (reference_date, today] — usa reference_date+1..today.
    # Esse intervalo de dias considera "hoje conta" se for util. Combina com
    # expected_lag=0 (today=reference_date+1, 1 dia util passou se today e
    # util, 0 se today e fim-de-semana — coerente).
    return sum(
        1
        for d in business_days_set
        if reference_date < d <= today
    )


def compute_publication_state(
    *,
    reference_date: date,
    today: date,
    business_days_set: frozenset[date],
    window: ToleranceWindow,
) -> PublicationState:
    """Classifica em ESPERADO/ATRASADO/SUSPEITO/FURO_DEFINITIVO.

    Fronteiras inclusivas/exclusivas escolhidas para serem intuitivas no
    operador:
        days <= expected            → ESPERADO  (no SLA)
        expected < days <= tolerance → ATRASADO  (atrasado, ainda aceitavel)
        tolerance < days <= give_up  → SUSPEITO  (provavel problema)
        days > give_up               → FURO_DEFINITIVO (desistir)

    Coverage chama esta funcao apenas para dias onde o evento e GAP /
    NOT_PUBLISHED / PENDING. Para OK/PARTIAL/WEEKEND/HOLIDAY/etc o estado
    nao se aplica e nao deve ser exibido na UI.

    Args:
        reference_date: data de referencia do relatorio.
        today: data corrente (caller injeta — facilita teste).
        business_days_set: dias uteis ANBIMA no range [reference_date, today].
        window: janela efetiva (override do tenant + defaults do catalogo).

    Returns:
        Um valor de `PublicationState`.
    """
    days = count_business_days_between(
        reference_date=reference_date,
        today=today,
        business_days_set=business_days_set,
    )
    if days <= window.expected_lag_business_days:
        return PublicationState.ESPERADO
    if days <= window.tolerance_business_days:
        return PublicationState.ATRASADO
    if days <= window.give_up_business_days:
        return PublicationState.SUSPEITO
    return PublicationState.FURO_DEFINITIVO


__all__ = [
    "PublicationState",
    "ToleranceWindow",
    "compute_publication_state",
    "count_business_days_between",
    "resolve_tolerance_window",
]
