"""Sync state machine — pure logic for endpoint_date_state transitions.

F1.2 do refactor de sync (ver `project_qitech_sync_state_machine` memory).

Este modulo nao toca DB — recebe entrada, devolve saida. Caller (scheduler
em F1.3, job nightly em F1.4) aplica o resultado em SQLAlchemy.

Tres responsabilidades:
1. `derive_state_from_result(http_status, completeness)` — mapeia o resultado
   crudu de uma tentativa de sync pro estado canonico da state machine.
2. `compute_next_attempt(...)` — dado o novo estado + janela de tolerancia
   + calendario, calcula `next_attempt_at` e `backoff_seconds`. Politica de
   backoff por PublicationState:
        ESPERADO        → 30 min
        ATRASADO        →  2 h
        SUSPEITO        → 12 h
        FURO_DEFINITIVO → state vira ABANDONED, next_attempt_at = NULL
3. `transition(...)` — composicao das duas anteriores num so passo. Retorna
   dict com os campos pra atualizar na row.

Tambem expoe `reset_abandoned()` — quando operador clica "Reabrir" na UI,
volta pra not_started, attempts_count=0, next_attempt_at=now.

Convencoes:
- `now` e `today` injetados pelo caller — facilita teste sem freezegun.
- `business_days_set` injetado — manter este modulo puro de DB.
- Todos os tempos em UTC. Caller traduz pra fuso do usuario na UI.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any

from app.modules.integracoes.services.tolerance import (
    PublicationState,
    ToleranceWindow,
    compute_publication_state,
)


class EndpointDateStateValue(StrEnum):
    """Vocabulario de estados da `endpoint_date_state.state`.

    Espelha o CHECK constraint da tabela (migration b4f1a8d2c903). Mudar
    valor aqui exige migration nova ajustando o CHECK.
    """

    NOT_STARTED = "not_started"
    IN_FLIGHT = "in_flight"
    COMPLETE = "complete"
    EMPTY = "empty"
    PARTIAL = "partial"
    NOT_PUBLISHED = "not_published"
    ABANDONED = "abandoned"


# Backoff por estado de tolerancia da publicacao (vendor). Aplica-se aos
# estados nao-terminais que esperam evolucao: NOT_STARTED, EMPTY, PARTIAL,
# NOT_PUBLISHED. ESPERADO = dentro do SLA, retentar rapido pra capturar
# publicacao tao logo apareca. ATRASADO/SUSPEITO espacam progressivamente.
# Decidido em 2026-05-19 (memory project_qitech_sync_state_machine).
_BACKOFF_BY_TOLERANCE_STATE: dict[PublicationState, timedelta] = {
    PublicationState.ESPERADO: timedelta(minutes=30),
    PublicationState.ATRASADO: timedelta(hours=2),
    PublicationState.SUSPEITO: timedelta(hours=12),
    # FURO_DEFINITIVO nao usa backoff — transita pra ABANDONED.
}


# Estados terminais (nao entram na fila do scheduler).
TERMINAL_STATES: frozenset[EndpointDateStateValue] = frozenset(
    {
        EndpointDateStateValue.COMPLETE,  # COMPLETE entra no scheduler so apos TTL
        EndpointDateStateValue.IN_FLIGHT,  # ja sendo processado, nao re-despachar
        EndpointDateStateValue.ABANDONED,
    }
)


# Estados retentaveis (entram na fila quando next_attempt_at <= now).
RETRYABLE_STATES: frozenset[EndpointDateStateValue] = frozenset(
    {
        EndpointDateStateValue.NOT_STARTED,
        EndpointDateStateValue.EMPTY,
        EndpointDateStateValue.PARTIAL,
        EndpointDateStateValue.NOT_PUBLISHED,
    }
)


def derive_state_from_result(
    *,
    http_status: int | None,
    completeness: str | None,
) -> EndpointDateStateValue:
    """Mapeia o resultado bruto de run_sync_endpoint pro estado canonico.

    Convencoes vindas do adapter QiTech (ver
    `app/modules/integracoes/adapters/admin/qitech/completeness.py`):
    - http_status=200 + completeness='complete' → COMPLETE
    - http_status=200 + completeness='partial'  → PARTIAL
    - http_status=200 + completeness='empty'    → EMPTY
    - http_status=200 + completeness=None       → COMPLETE (legacy, sem
      assessment — assumimos OK pra nao gerar regressao visual)
    - http_status != 200                        → NOT_PUBLISHED
    - http_status=None (chamada nem rolou)      → NOT_PUBLISHED (defensivo;
      caller deveria evitar)
    """
    if http_status is not None and 200 <= http_status < 300:
        if completeness == "partial":
            return EndpointDateStateValue.PARTIAL
        if completeness == "empty":
            return EndpointDateStateValue.EMPTY
        return EndpointDateStateValue.COMPLETE
    return EndpointDateStateValue.NOT_PUBLISHED


def _last_business_day_on_or_before(
    target: date, business_days_set: frozenset[date]
) -> date:
    """Helper: para janelas de TTL, ancora em dia util.

    Se `target` ja e dia util, retorna o proprio. Se nao, busca pra tras
    no `business_days_set` ate achar. Fallback (nunca esperado): retorna
    target mesmo se nao for util — caller pode ajustar.
    """
    if target in business_days_set:
        return target
    for d in sorted(business_days_set, reverse=True):
        if d <= target:
            return d
    return target


def _add_business_days(
    start: date, n_business_days: int, business_days_set: frozenset[date]
) -> date:
    """Adiciona N dias uteis a `start` usando o calendario fornecido.

    Convencao: start nao conta. start=Mon, n=1 → Tue (se util). n=0 →
    start.
    """
    if n_business_days <= 0:
        return start
    sorted_bd = sorted(d for d in business_days_set if d > start)
    if len(sorted_bd) >= n_business_days:
        return sorted_bd[n_business_days - 1]
    # Fora do range carregado — fallback aproximativo (caller deveria
    # carregar range suficiente).
    return start + timedelta(days=n_business_days)


def compute_next_attempt(
    *,
    new_state: EndpointDateStateValue,
    data_referencia: date,
    today: date,
    now: datetime,
    business_days_set: frozenset[date],
    window: ToleranceWindow,
    refresh_complete_window_business_days: int,
) -> tuple[datetime | None, int | None, EndpointDateStateValue]:
    """Decide next_attempt_at + backoff_seconds + estado final.

    Pode "promover" o estado:
    - new_state EMPTY/PARTIAL/NOT_PUBLISHED + tolerance FURO_DEFINITIVO →
      ABANDONED (passou give_up_business_days, nao retenta).
    - new_state COMPLETE: agenda re-fetch via TTL (refresh_complete_window)
      pra detectar republicacao do vendor.

    Returns:
        (next_attempt_at, backoff_seconds, final_state).
        next_attempt_at = None apenas quando final_state = ABANDONED.
        backoff_seconds = None quando nao se aplica (ABANDONED ou COMPLETE
        com TTL fixo).
    """
    # COMPLETE: agenda re-fetch via TTL (substitui job legado refresh_complete).
    # next_attempt_at = data_referencia + TTL dias uteis. Se ja passou (caso
    # row antiga), agenda pra now + 1h (proxima janela).
    if new_state == EndpointDateStateValue.COMPLETE:
        if refresh_complete_window_business_days <= 0:
            # TTL desabilitado — nao re-tenta. next_attempt_at NULL e legitimo
            # aqui (estado nao-terminal sem prox attempt = "esperando manual
            # trigger" ou "esquecido"). Caller pode setar.
            return (None, None, EndpointDateStateValue.COMPLETE)
        ttl_target = _add_business_days(
            data_referencia,
            refresh_complete_window_business_days,
            business_days_set,
        )
        # Combina com 09:00 SP-ish (12:00 UTC) — bate com o tick do nightly
        # e evita re-fetch no meio da madrugada do vendor.
        next_dt = datetime.combine(
            ttl_target,
            datetime.min.time().replace(hour=12),
            tzinfo=UTC,
        )
        if next_dt <= now:
            next_dt = now + timedelta(hours=1)
        return (next_dt, None, EndpointDateStateValue.COMPLETE)

    # Estados retentaveis (EMPTY/PARTIAL/NOT_PUBLISHED/NOT_STARTED).
    if new_state in RETRYABLE_STATES:
        tolerance_state = compute_publication_state(
            reference_date=data_referencia,
            today=today,
            business_days_set=business_days_set,
            window=window,
        )
        if tolerance_state == PublicationState.FURO_DEFINITIVO:
            return (None, None, EndpointDateStateValue.ABANDONED)
        backoff = _BACKOFF_BY_TOLERANCE_STATE[tolerance_state]
        return (
            now + backoff,
            int(backoff.total_seconds()),
            new_state,
        )

    # ABANDONED ou IN_FLIGHT — caller nao deveria chamar com esses, mas
    # defensivo: ABANDONED mantem terminal; IN_FLIGHT cai pra NOT_STARTED
    # com next=now (lock liberado, re-fila imediato).
    if new_state == EndpointDateStateValue.ABANDONED:
        return (None, None, EndpointDateStateValue.ABANDONED)
    # IN_FLIGHT defensivo
    return (now, None, EndpointDateStateValue.NOT_STARTED)


def transition(
    *,
    data_referencia: date,
    today: date,
    now: datetime,
    business_days_set: frozenset[date],
    window: ToleranceWindow,
    refresh_complete_window_business_days: int,
    http_status: int | None,
    completeness: str | None,
    previous_attempts_count: int,
) -> dict[str, Any]:
    """Composicao: derive_state_from_result + compute_next_attempt.

    Recebe resultado bruto de uma tentativa + contexto, devolve dict com
    os campos atualizaveis na row de endpoint_date_state. Caller faz o
    UPDATE.

    Returns dict com chaves:
        state, next_attempt_at, last_attempt_at, last_http_status,
        last_completeness, backoff_seconds, attempts_count.
    """
    new_state = derive_state_from_result(
        http_status=http_status, completeness=completeness
    )
    next_attempt_at, backoff_seconds, final_state = compute_next_attempt(
        new_state=new_state,
        data_referencia=data_referencia,
        today=today,
        now=now,
        business_days_set=business_days_set,
        window=window,
        refresh_complete_window_business_days=refresh_complete_window_business_days,
    )
    return {
        "state": final_state.value,
        "next_attempt_at": next_attempt_at,
        "last_attempt_at": now,
        "last_http_status": http_status,
        "last_completeness": completeness,
        "backoff_seconds": backoff_seconds,
        "attempts_count": previous_attempts_count + 1,
    }


def reset_abandoned(*, now: datetime) -> dict[str, Any]:
    """Reset manual via UI — volta pra NOT_STARTED, fila imediato.

    Trilha em `decision_log` e responsabilidade do caller (rota HTTP que
    invoca este service). Aqui so devolve o dict de UPDATE — service nao
    sabe quem clicou nem porque.

    Returns dict com state, next_attempt_at, attempts_count, backoff_seconds
    pra UPDATE. last_* sao preservados (operador quer ver o ultimo erro
    mesmo apos reset).
    """
    return {
        "state": EndpointDateStateValue.NOT_STARTED.value,
        "next_attempt_at": now,
        "attempts_count": 0,
        "backoff_seconds": None,
    }


__all__ = [
    "RETRYABLE_STATES",
    "TERMINAL_STATES",
    "EndpointDateStateValue",
    "compute_next_attempt",
    "derive_state_from_result",
    "reset_abandoned",
    "transition",
]
