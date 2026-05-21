"""HTTP endpoints operacionais cross-source de integracoes.

Diferenca para `routers/sources.py`: este router cobre views **agregadas**
do operador, sem foco em uma fonte especifica. Hoje tem:

- `GET /integracoes/operacao/runs` — historico cross-source (decision_log
  filtrado por todos os adapters de integracao, com filtros por fonte,
  janela de tempo, status e quem disparou).

PR 4 (2026-05-21): nasceu junto com a pagina `/integracoes/operacao/historico`
no frontend. O endpoint `/sources/{source_type}/runs` (por fonte) continua
existindo — este e visao consolidada (ex.: ver todas as falhas das ultimas
24h em qualquer adapter).

Todos exigem `require_module(Module.INTEGRACOES, Permission.ADMIN)`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission, SourceType
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.integracoes.services.sync_runner import RULE_NAME_BY_SOURCE
from app.shared.audit_log.decision_log import DecisionLog, DecisionType

router = APIRouter(prefix="/operacao", tags=["integracoes:operacao"])

_Guard = Depends(require_module(Module.INTEGRACOES, Permission.ADMIN))

# Reverse-map para anotar `source_type` em cada RunEntry — o decision_log
# guarda apenas `rule_or_model` (ex.: "qitech_adapter"), e a UI precisa do
# source_type para chip de fonte + filtro + drill-down.
_RULE_TO_SOURCE: dict[str, SourceType] = {
    rule: src for src, rule in RULE_NAME_BY_SOURCE.items()
}


class CrossSourceRunEntry(BaseModel):
    """Entrada do decision_log com `source_type` derivado do `rule_or_model`."""

    id: UUID
    occurred_at: datetime
    source_type: SourceType
    rule_or_model: str
    rule_or_model_version: str | None
    triggered_by: str
    explanation: str | None
    output: dict[str, Any] | None


@router.get("/runs", response_model=list[CrossSourceRunEntry])
async def list_cross_source_runs(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    # Multi-source: ?source_type=erp:bitfin&source_type=admin:qitech
    source_type: Annotated[list[SourceType] | None, Query()] = None,
    # Janela de tempo (inclusiva). `since` interpretado a 00:00 UTC do dia,
    # `until` a 23:59:59 UTC — ja basta pro caso de uso "auditoria do dia".
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
    # Filtro de status. ok = `output.errors` ausente/vazio; error = nao vazio.
    # Resolvido em Python (decision_log.output e JSONB; subscript com type-
    # safety SQLAlchemy embaralha entre versoes — pra 200 rows o filtro em
    # Python e barato e legivel).
    status: Annotated[Literal["ok", "error"] | None, Query()] = None,
    # Filtro de `triggered_by` (LIKE prefixo — ex.: "user:" / "system:" /
    # "system:scheduler").
    triggered_by: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    _: None = _Guard,
) -> list[CrossSourceRunEntry]:
    """Historico cross-source — decision_log filtrado por todos os adapters
    de integracao registrados em RULE_NAME_BY_SOURCE.

    `limit` aplica-se ANTES do filtro de status (que e pos-query); na
    pratica, se status=error reduz muito, peca limit maior. Documentado
    explicitamente para nao surpreender quem chama.
    """
    # Restringe ao conjunto de fontes filtradas ou a todas as conhecidas.
    if source_type:
        rules = [
            RULE_NAME_BY_SOURCE[st]
            for st in source_type
            if st in RULE_NAME_BY_SOURCE
        ]
    else:
        rules = list(RULE_NAME_BY_SOURCE.values())

    if not rules:
        return []

    stmt = (
        select(DecisionLog)
        .where(
            DecisionLog.tenant_id == principal.tenant_id,
            DecisionLog.decision_type == DecisionType.SYNC,
            DecisionLog.rule_or_model.in_(rules),
        )
        .order_by(desc(DecisionLog.occurred_at))
        .limit(limit)
    )

    if since is not None:
        stmt = stmt.where(
            DecisionLog.occurred_at >= datetime.combine(since, time.min, UTC)
        )
    if until is not None:
        stmt = stmt.where(
            DecisionLog.occurred_at <= datetime.combine(until, time.max, UTC)
        )
    if triggered_by:
        stmt = stmt.where(DecisionLog.triggered_by.like(f"{triggered_by}%"))

    rows = list((await db.execute(stmt)).scalars().all())

    def _has_errors(output: dict[str, Any] | None) -> bool:
        if not output:
            return False
        errs = output.get("errors")
        return bool(errs) if isinstance(errs, list) else False

    if status == "ok":
        rows = [r for r in rows if not _has_errors(r.output)]
    elif status == "error":
        rows = [r for r in rows if _has_errors(r.output)]

    out: list[CrossSourceRunEntry] = []
    for r in rows:
        src = _RULE_TO_SOURCE.get(r.rule_or_model or "")
        if src is None:
            continue
        out.append(
            CrossSourceRunEntry(
                id=r.id,
                occurred_at=r.occurred_at,
                source_type=src,
                rule_or_model=r.rule_or_model or "",
                rule_or_model_version=r.rule_or_model_version,
                triggered_by=r.triggered_by,
                explanation=r.explanation,
                output=r.output,
            )
        )
    return out
